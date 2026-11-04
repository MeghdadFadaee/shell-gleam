#!/usr/bin/python3
"""A bounded, dependency-free system status MOTD for Linux."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import unicodedata

DEFAULTS = {
    'title': '', 'address': 'auto', 'width': 72, 'color': True, 'ascii': False,
    'sections': ['system', 'runtime', 'health'],
    'services': [{'unit': 'nginx.service', 'label': 'Nginx', 'required': False},
                 {'unit': 'docker.service', 'label': 'Docker', 'required': False}],
    'disks': ['/'], 'docker': True, 'command_timeout': 1.0,
    'memory_warning': 75, 'memory_critical': 90, 'disk_warning': 75,
    'disk_critical': 90, 'load_warning': .7, 'load_critical': 1.,
    'updates_max_age_hours': 48, 'footer': '',
}
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def clean(value):
    return ''.join(c for c in str(value) if unicodedata.category(c)[0] != 'C')


def cells(value):
    return sum(0 if unicodedata.combining(c) else
               2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1
               for c in ANSI.sub('', value))


def clip(value, width):
    result = ''
    for char in clean(value):
        if cells(result + char) > width:
            break
        result += char
    return result


def config(path):
    cfg = dict(DEFAULTS)
    if path and Path(path).exists():
        overrides = json.loads(Path(path).read_text())
        if not isinstance(overrides, dict):
            raise ValueError('configuration must be a JSON object')
        unknown = set(overrides) - set(DEFAULTS)
        if unknown:
            raise ValueError('unknown settings: ' + ', '.join(sorted(unknown)))
        cfg.update(overrides)
    for key in ('title', 'address', 'footer'):
        if not isinstance(cfg[key], str):
            raise ValueError(key + ' must be a string')
    for key in ('color', 'ascii', 'docker'):
        if type(cfg[key]) is not bool:
            raise ValueError(key + ' must be true or false')
    if type(cfg['width']) is not int or not 52 <= cfg['width'] <= 120:
        raise ValueError('width must be an integer from 52 to 120')
    for key in ('command_timeout', 'updates_max_age_hours', 'memory_warning',
                'memory_critical', 'disk_warning', 'disk_critical', 'load_warning', 'load_critical'):
        if type(cfg[key]) not in (int, float) or not 0 < cfg[key] < float('inf'):
            raise ValueError(key + ' must be a positive finite number')
    if not .1 <= cfg['command_timeout'] <= 2:
        raise ValueError('command_timeout must be between 0.1 and 2 seconds')
    for metric in ('memory', 'disk', 'load'):
        if cfg[metric + '_warning'] >= cfg[metric + '_critical']:
            raise ValueError(metric + ': warning must be below critical')
    for metric in ('memory', 'disk'):
        if cfg[metric + '_critical'] > 100:
            raise ValueError(metric + '_critical must be at most 100')
    if not isinstance(cfg['sections'], list) or any(s not in ('system', 'runtime', 'health') for s in cfg['sections']):
        raise ValueError('sections must contain system, runtime or health')
    if not isinstance(cfg['disks'], list) or not 1 <= len(cfg['disks']) <= 8 or any(not isinstance(d, str) or not d.startswith('/') for d in cfg['disks']):
        raise ValueError('disks must contain 1-8 absolute paths')
    if not isinstance(cfg['services'], list) or len(cfg['services']) > 16:
        raise ValueError('services must be a list of at most 16 entries')
    for service in cfg['services']:
        if not isinstance(service, dict) or set(service) - {'unit', 'label', 'required'}:
            raise ValueError('each service accepts unit, label and required')
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_@.:-]*', service.get('unit', '')):
            raise ValueError('invalid service unit')
        if not isinstance(service.get('label', ''), str) or type(service.get('required', False)) is not bool:
            raise ValueError('invalid service label or required flag')
    return cfg


def command(args, timeout):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, 'LC_ALL': 'C', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return -1, ''


def read(path):
    try:
        return Path(path).read_text()
    except OSError:
        return ''


def update_status(path, max_age, now=None):
    source = Path(path)
    try:
        age = (time.time() if now is None else now) - source.stat().st_mtime
        text = source.read_text()
    except OSError:
        return 'Package updates unknown (no cached data)', True
    match = re.search(r'(?m)^\s*(\d+)\s+(?:updates? (?:can be applied|available)|packages? can be updated)', text)
    if not match:
        return 'Package updates unknown (unrecognized cache)', True
    count = int(match[1])
    if age > max_age * 3600:
        return f'Package cache stale ({count} updates last reported)', True
    return (f'{count} package updates available' if count else 'Packages current (cached)'), bool(count)


def docker_status(result):
    code, output = result
    if code:
        return 'Container status unavailable', True
    rows = [r.split('|', 2) for r in output.splitlines() if len(r.split('|', 2)) == 3]
    running = sum(r[1] == 'running' for r in rows)
    unhealthy = sum('(unhealthy)' in r[2] for r in rows)
    starting = sum('(health: starting)' in r[2] for r in rows)
    healthy = sum('(healthy)' in r[2] for r in rows)
    failed = sum(r[1] in ('dead', 'restarting') or (r[1] == 'exited' and not r[2].startswith('Exited (0)')) for r in rows)
    text = f'{running} containers running'
    if unhealthy or failed or starting:
        text += f' · {unhealthy} unhealthy · {failed} failed · {starting} starting'
    elif running:
        text += f' · {healthy} healthchecked' if healthy else ' · no healthchecks'
    return text, bool(unhealthy or failed or starting)


def collect(cfg):
    jobs = {'failed': ['systemctl', '--failed', '--no-legend', '--plain', '--no-pager'],
            'ip': ['hostname', '-I']}
    for i, service in enumerate(cfg['services']):
        jobs[f'service{i}'] = ['systemctl', 'show', service['unit'], '--property=LoadState,ActiveState', '--no-pager']
    if cfg['docker'] and shutil.which('docker'):
        # Pin the local daemon: never inherit a user's remote Docker context.
        jobs['docker'] = ['docker', '--host', 'unix:///var/run/docker.sock', 'ps', '-a', '--format', '{{.Names}}|{{.State}}|{{.Status}}']
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {k: executor.submit(command, args, cfg['command_timeout']) for k, args in jobs.items()}
        results = {k: future.result() for k, future in futures.items()}
    return results


def render(cfg, results):
    rows = []
    attention = False
    def add(section, text, level='normal'):
        nonlocal attention
        rows.append((section, clean(text), level))
        attention |= level in ('warning', 'critical')
    def level(value, metric):
        return 'critical' if value >= cfg[metric + '_critical'] else 'warning' if value >= cfg[metric + '_warning'] else 'good'
    try:
        seconds = int(float(read('/proc/uptime').split()[0]))
        uptime = f'{seconds // 86400}d {seconds % 86400 // 3600}h' if seconds >= 86400 else f'{seconds // 3600}h {seconds % 3600 // 60}m'
        load = float(read('/proc/loadavg').split()[0])
        cores = os.cpu_count() or 1
        add('system', f'↑ Uptime  {uptime}      ≋ Load average  {load:.2f} ({cores} cores)', level(load / cores, 'load'))
        memory = {k: int(v.split()[0]) for k, v in (line.split(':', 1) for line in read('/proc/meminfo').splitlines())}
        total = memory['MemTotal']; used = total - memory['MemAvailable']
        percent = used / total * 100
        add('system', f'Memory  {bar(percent, cfg)}  {percent:.0f}% · {used / 1048576:.1f} / {total / 1048576:.1f} GiB', level(percent, 'memory'))
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        add('system', 'System metrics unavailable', 'warning')
    for disk in cfg['disks']:
        try:
            usage = shutil.disk_usage(disk)
            stat = os.statvfs(disk)
            # Match df: percentage uses space available to non-root, excluding reserved blocks.
            denominator = usage.used + stat.f_bavail * stat.f_frsize
            percent = usage.used / denominator * 100 if denominator else 0
            add('system', f'Disk {disk}  {bar(percent, cfg)}  {percent:.0f}% · {usage.used / 1073741824:.1f} / {usage.total / 1073741824:.1f} GiB', level(percent, 'disk'))
        except OSError:
            add('system', f'Disk {disk}: unavailable', 'warning')
    for i, service in enumerate(cfg['services']):
        code, output = results[f'service{i}']
        properties = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        label = service.get('label') or service['unit']
        if code or properties.get('LoadState') in (None, 'not-found'):
            missing = properties.get('LoadState') == 'not-found'
            add('runtime', f'●  {label}: {"not installed" if missing else "status unavailable"}', 'warning' if service.get('required') or not missing else 'normal')
        elif properties.get('ActiveState') == 'active':
            add('runtime', f'●  {label} is online', 'good')
        else:
            add('runtime', f'●  {label} is {properties.get("ActiveState", "unknown")}', 'warning')
    if cfg['docker']:
        if 'docker' in results:
            text, warning = docker_status(results['docker'])
            add('runtime', '   ' + text, 'warning' if warning else 'good')
        else:
            add('runtime', '   Docker CLI not installed')
    code, output = results['failed']
    if code:
        add('health', '⚠  Failed services: status unavailable', 'warning')
    else:
        failed = [line.split()[0] for line in output.splitlines() if line.strip()]
        add('health', f'⚠  {len(failed)} units failed · ' + ', '.join(failed[:3]) if failed else '✓  No failed systemd units', 'warning' if failed else 'good')
    updates, warning = update_status('/var/lib/update-notifier/updates-available', cfg['updates_max_age_hours'])
    add('health', ('↑  ' if warning else '✓  ') + updates, 'warning' if warning else 'good')
    reboot = Path('/run/reboot-required').exists()
    add('health', '↻  Reboot required' if reboot else '✓  No reboot needed', 'warning' if reboot else 'good')
    firmware = read('/run/motd.d/85-fwupd')
    match = re.search(r'(\d+) devices? have a firmware upgrade available', firmware)
    if match and int(match[1]):
        add('health', f'↑  {match[1]} firmware upgrades available', 'warning')
    os_name = 'Linux'
    for line in read('/etc/os-release').splitlines():
        if line.startswith('PRETTY_NAME='):
            os_name = line.split('=', 1)[1].strip('"')
    ip = cfg['address']
    if ip == 'auto':
        addresses = results['ip'][1].split()
        ip = next((a for a in addresses if ':' not in a), addresses[0] if addresses else 'address unavailable')
    title = cfg['title'] or socket.gethostname().split('.')[0].upper()
    return box(cfg, title, os_name + '  ·  ' + ip, rows, attention)


def bar(percent, cfg):
    filled = max(0, min(18, int(percent * 18 / 100 + .5)))
    return ('#' if cfg['ascii'] else '█') * filled + ('-' if cfg['ascii'] else '░') * (18 - filled)


def box(cfg, title, subtitle, rows, attention):
    width = cfg['width']
    color = cfg['color'] and 'NO_COLOR' not in os.environ
    colors = {'normal': '', 'good': '\033[32m', 'warning': '\033[33m', 'critical': '\033[31m', 'border': '\033[36m'}
    def paint(text, kind):
        return colors[kind] + text + '\033[0m' if color and colors[kind] else text
    ascii_mode = cfg['ascii']
    h, v = ('-', '|') if ascii_mode else ('─', '│')
    tl, tr, bl, br, ml, mr = ('+',) * 6 if ascii_mode else ('╭', '╮', '╰', '╯', '├', '┤')
    def plain(text):
        if ascii_mode:
            for a, b in {'◆': '*', '●': '*', '↑': '^', '≋': '~', '✓': '+', '⚠': '!', '↻': '*', '·': '/'}.items():
                text = text.replace(a, b)
            text = text.encode('ascii', 'replace').decode()
        return clean(text)
    def line(text='', kind='normal'):
        text = clip(plain(text), width - 2)
        return '  ' + paint(v, 'border') + ' ' + paint(text, kind) + ' ' * (width - 1 - cells(text)) + paint(v, 'border')
    status = ('● ATTENTION' if attention else '● HEALTHY')
    left = clip(plain('◆ ' + title), width - cells(plain(status)) - 4)
    header = left + ' ' * (width - 2 - cells(left) - cells(plain(status))) + status
    output = ['', '  ' + paint(tl + h * width + tr, 'border'), line(header, 'warning' if attention else 'good'), line('  ' + subtitle)]
    for section in cfg['sections']:
        label = h + ' ' + section.upper() + ' '
        output.append('  ' + paint(ml + label + h * (width - cells(label)) + mr, 'border'))
        output.append(line())
        for row_section, text, kind in rows:
            if row_section == section:
                output.append(line('  ' + text, kind))
        output.append(line())
    if cfg['footer']:
        output.append(line(cfg['footer']))
    output.extend(['  ' + paint(bl + h * width + br, 'border'), ''])
    return '\n'.join(output) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='/etc/server-status/config.json')
    parser.add_argument('--check', action='store_true', help='validate configuration without running probes')
    parser.add_argument('--no-color', action='store_true')
    args = parser.parse_args()
    try:
        cfg = config(args.config)
        if args.no_color:
            cfg['color'] = False
        if args.check:
            print('Configuration valid')
            return 0
        print(render(cfg, collect(cfg)), end='')
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print('server-status: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
