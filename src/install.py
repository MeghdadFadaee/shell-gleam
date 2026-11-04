#!/usr/bin/env python3
"""Install a system-wide Ubuntu/Debian MOTD with transactional backup/restore."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
HOOK = '/etc/update-motd.d/00-server-status'
BINARY = '/usr/local/bin/server-status'
CONFIG = '/etc/server-status/config.json'
STATE = '/var/lib/server-status'
SUFFIX = '~server-status-disabled'
PAM_FILES = ('/etc/pam.d/sshd', '/etc/pam.d/login')
PAM_LINE = 'session optional pam_exec.so stdout type=open_session quiet /etc/update-motd.d/00-server-status'
PAM_PATTERN = re.compile(r'^session[^\n]*pam_motd\.so[^\n]*motd=/run/motd\.dynamic[^\n]*$', re.MULTILINE)
WRAPPER = '''#!/bin/sh
# Managed by server-status. PAM invokes this for all users.
# Keep login working even if probes, disks or configuration fail.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
export PYTHONIOENCODING=utf-8
if ! /usr/bin/timeout --kill-after=1 6 /usr/bin/python3 -I /usr/local/bin/server-status 2>/dev/null; then
    printf '\\n  Server status unavailable; run server-status to diagnose.\\n\\n'
fi
exit 0
'''


def renderer():
    spec = importlib.util.spec_from_file_location('server_status', PROJECT / 'src/server_status.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.server-status-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Installation:
    def __init__(self, root):
        self.root = root
        self.state = self.path(STATE)
        self.manifest = self.state / 'manifest.json'

    def path(self, absolute):
        return self.root / absolute.lstrip('/')

    def snapshot(self, names, folder):
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        records = {}
        for i, name in enumerate(names):
            path = self.path(name)
            if path.is_symlink():
                records[name] = {'kind': 'symlink', 'target': os.readlink(path), 'uid': path.lstat().st_uid, 'gid': path.lstat().st_gid}
            elif path.exists():
                if not path.is_file():
                    raise ValueError(f'refusing to replace non-file: {name}')
                backup = folder / str(i)
                shutil.copy2(path, backup)
                info = path.stat()
                records[name] = {'kind': 'file', 'backup': str(backup.relative_to(self.state)), 'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
            else:
                records[name] = {'kind': 'absent'}
        return records

    def restore(self, records):
        for name, record in records.items():
            path = self.path(name)
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.exists():
                raise ValueError(f'refusing to overwrite directory during restore: {name}')
            if record['kind'] != 'absent':
                path.parent.mkdir(parents=True, exist_ok=True)
                if record['kind'] == 'symlink':
                    path.symlink_to(record['target'])
                    os.lchown(path, record['uid'], record['gid'])
                else:
                    shutil.copy2(self.state / record['backup'], path)
                    os.chmod(path, record['mode'])
                    os.chown(path, record['uid'], record['gid'])

    def hooks(self):
        directory = self.path('/etc/update-motd.d')
        if shutil.which('run-parts'):
            selected = subprocess.run(['run-parts', '--lsbsysinit', '--test', str(directory)], capture_output=True, text=True, check=True, timeout=5)
            return sorted('/etc/update-motd.d/' + Path(line).name for line in selected.stdout.splitlines() if Path(line).name != Path(HOOK).name)
        return sorted('/etc/update-motd.d/' + p.name for p in directory.iterdir()
                      if p.name != Path(HOOK).name and re.fullmatch(r'[A-Za-z0-9_-]+', p.name)
                      and (p.is_file() or p.is_symlink()) and os.access(p, os.X_OK))

    def install(self, cfg, dry_run):
        hooks = self.hooks()
        names = [BINARY, CONFIG, HOOK, '/etc/motd', '/run/motd.dynamic', *PAM_FILES]
        for name in hooks:
            if self.path(name + SUFFIX).exists() or self.path(name + SUFFIX).is_symlink():
                raise ValueError('disabled-hook name collision: ' + name + SUFFIX)
            names.extend([name, name + SUFFIX])
        print('Install system-wide banner; disable ' + str(len(hooks)) + ' Ubuntu MOTD hooks.')
        print('Configuration: ' + str(self.path(CONFIG)))
        if dry_run:
            print('Dry run: no files changed.')
            return
        existing = json.loads(self.manifest.read_text()) if self.manifest.exists() else {}
        transaction = Path(tempfile.mkdtemp(prefix='backup-', dir=self.state))
        before = self.snapshot(names, transaction)
        baseline = dict(existing)
        for name, record in before.items():
            baseline.setdefault(name, record)
        try:
            for name in hooks:
                os.replace(self.path(name), self.path(name + SUFFIX))
            atomic(self.path(BINARY), (PROJECT / 'src/server_status.py').read_bytes(), 0o755)
            atomic(self.path(CONFIG), (json.dumps(cfg, indent=2, ensure_ascii=False) + '\n').encode())
            atomic(self.path(HOOK), WRAPPER.encode(), 0o755)
            for name in PAM_FILES:
                pam = self.path(name)
                content = pam.read_text()
                if PAM_LINE not in content:
                    updated, count = PAM_PATTERN.subn(PAM_LINE, content)
                    if count != 1:
                        raise ValueError('expected one dynamic MOTD session entry in ' + name)
                    atomic(pam, updated.encode(), stat.S_IMODE(pam.stat().st_mode))
            # Empty rather than remove a symlink: restore() has the original target.
            atomic(self.path('/etc/motd'), b'')
            if self.root == Path('/'):
                selected = subprocess.run(['/usr/bin/run-parts', '--lsbsysinit', '--test', '/etc/update-motd.d'], capture_output=True, text=True, check=True, timeout=5)
                if selected.stdout.splitlines() != [HOOK]:
                    raise ValueError('unexpected executable MOTD hooks: ' + selected.stdout)
                refresh = subprocess.run(['/usr/bin/timeout', '--kill-after=1', '8', '/usr/bin/python3', '-I', BINARY], capture_output=True, timeout=10)
                if refresh.returncode:
                    raise ValueError('initial rendering failed: ' + refresh.stderr.decode(errors='replace'))
                atomic(self.path('/run/motd.dynamic'), refresh.stdout)
            atomic(self.manifest, (json.dumps(baseline, indent=2) + '\n').encode(), 0o600)
        except BaseException:
            self.restore(before)
            raise
        print('Installed. Existing config preserved unless --config or customization flags were supplied.')
        print('Undo: sudo ./setup.sh uninstall')

    def uninstall(self, dry_run):
        if not self.manifest.exists():
            print('No managed installation found.')
            return
        original = json.loads(self.manifest.read_text())
        print('Restore ' + str(len(original)) + ' paths from the original installation backup.')
        if dry_run:
            print('Dry run: no files changed.')
            return
        transaction = Path(tempfile.mkdtemp(prefix='uninstall-', dir=self.state))
        before = self.snapshot(list(original), transaction)
        try:
            self.restore(original)
            self.manifest.rename(self.state / 'last-uninstall.json')
        except BaseException:
            self.restore(before)
            raise
        print('Original login messages restored. Backups retained in ' + str(self.state))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'uninstall', 'status'), nargs='?', default='install')
    parser.add_argument('--config', type=Path, help='JSON configuration; validated before changes')
    parser.add_argument('--title', help='display name (default: hostname)')
    parser.add_argument('--address', help='display address (default: auto)')
    parser.add_argument('--no-color', action='store_true')
    parser.add_argument('--ascii', action='store_true')
    parser.add_argument('--wizard', action='store_true', help='interactive title, address, services and disk customization')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--root', type=Path, default=Path('/'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    installation = Installation(args.root.resolve())
    if args.action == 'status':
        print('Installed' if installation.manifest.exists() else 'Not installed')
        print('Backup directory: ' + str(installation.state))
        return 0
    if installation.root == Path('/'):
        if any(not Path(p).exists() for p in ('/usr/bin/python3', '/usr/bin/timeout', '/usr/bin/run-parts')):
            raise ValueError('requires python3, GNU coreutils timeout and Debian run-parts')
        if args.action == 'install':
            for pam in ('sshd', 'login'):
                content = Path('/etc/pam.d/' + pam).read_text()
                if PAM_LINE not in content and not any('pam_motd.so' in line and not line.lstrip().startswith('#') and 'noupdate' not in line and 'motd=/run/motd.dynamic' in line for line in content.splitlines()):
                    raise ValueError('requires existing dynamic pam_motd configuration in /etc/pam.d/' + pam)
            if not list(Path('/usr/lib').glob('**/security/pam_exec.so')) and not Path('/lib/security/pam_exec.so').exists():
                raise ValueError('requires the standard pam_exec.so session module')
            check = subprocess.run(['/usr/sbin/sshd', '-T'], capture_output=True, text=True, timeout=5)
            if check.returncode or 'usepam yes' not in check.stdout or 'printmotd no' not in check.stdout:
                raise ValueError('SSH must already have UsePAM yes and PrintMotd no; only MOTD session-display lines are managed')
    if args.action == 'install':
        source = args.config or (installation.path(CONFIG) if installation.path(CONFIG).exists() else PROJECT / 'config/default.json')
        if not source.is_file():
            raise ValueError('configuration file not found: ' + str(source))
        cfg = renderer().config(source)
        if args.title is not None:
            cfg['title'] = args.title
        if args.address is not None:
            cfg['address'] = args.address
        if args.no_color:
            cfg['color'] = False
        if args.ascii:
            cfg['ascii'] = True
        if args.wizard:
            cfg['title'] = input(f'Display title [{cfg["title"] or "automatic hostname"}]: ').strip() or cfg['title']
            cfg['address'] = input(f'IP address [{cfg["address"]}]: ').strip() or cfg['address']
            units = input('Service units, comma separated (blank: keep current; none: no services): ').strip()
            if units:
                cfg['services'] = [] if units == 'none' else [{'unit': unit.strip(), 'label': unit.strip().removesuffix('.service'), 'required': True} for unit in units.split(',')]
            disks = input('Disk paths, comma separated (blank: keep current): ').strip()
            if disks:
                cfg['disks'] = [d.strip() for d in disks.split(',')]
        # Validate CLI/wizard values before touching the system.
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / 'config.json'
            candidate.write_text(json.dumps(cfg))
            cfg = renderer().config(candidate)
    if args.dry_run:
        if args.action == 'install':
            installation.install(cfg, True)
        else:
            installation.uninstall(True)
        return 0
    if os.geteuid() != 0:
        raise ValueError('run installation/uninstallation with sudo (or use --dry-run)')
    installation.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(installation.state, 0o700)
    with (installation.state / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'install':
            installation.install(cfg, False)
        else:
            installation.uninstall(False)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print('setup: ' + str(exc), file=sys.stderr)
        sys.exit(1)
