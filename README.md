<div align="center">

# ✦ ShellGleam

**A brighter first look at your Linux server.**

A beautiful, configurable login dashboard for Ubuntu and Debian.
System metrics, services, containers, and health checks — before your first command.

[Website & installer](https://meghdadfadaee.github.io/shell-gleam/) · [Configuration](docs/configuration.md) · [Operations](docs/operations.md) · [MIT license](LICENSE)

</div>

```text
  ╭────────────────────────────────────────────────────────────────────────╮
  │ ◆ ORBIT                                                      ● HEALTHY │
  │   Ubuntu 24.04 LTS  ·  192.0.2.10                                      │
  ├─ SYSTEM ───────────────────────────────────────────────────────────────┤
  │                                                                        │
  │   ↑ Uptime  12d 4h      ≋ Load average  0.24 (8 cores)                  │
  │   Memory  ████░░░░░░░░░░░░░░  23% · 3.7 / 16.0 GiB                    │
  │   Disk /  ██████░░░░░░░░░░░░  34% · 68.0 / 200.0 GiB                   │
  │                                                                        │
  ├─ RUNTIME ──────────────────────────────────────────────────────────────┤
  │   ●  Nginx is online                                                   │
  │   ●  Docker is online                                                  │
  │      4 containers running · 4 healthchecked                             │
  ├─ HEALTH ───────────────────────────────────────────────────────────────┤
  │   ✓  No failed systemd units                                           │
  │   ✓  Packages current (cached)                                         │
  │   ✓  No reboot needed                                                  │
  ╰────────────────────────────────────────────────────────────────────────╯
```

*Illustrative output. Hostnames, addresses and metrics above are fictional.*

## Install in one command

```bash
curl -fsSL https://meghdadfadaee.github.io/shell-gleam/setup.sh | bash
```

The bootstrap downloads a versioned package, verifies its embedded SHA-256,
and requests `sudo` if needed. It retains setup at `/opt/shell-gleam`.

Pass options after `bash -s --`:

```bash
curl -fsSL https://meghdadfadaee.github.io/shell-gleam/setup.sh | bash -s -- install --title ORBIT
curl -fsSL https://meghdadfadaee.github.io/shell-gleam/setup.sh | bash -s -- install --wizard
curl -fsSL https://meghdadfadaee.github.io/shell-gleam/setup.sh | bash -s -- install --dry-run
```

Prefer to inspect first? Download the generated script, read it, then execute:

```bash
curl -fsSLo shell-gleam-setup.sh https://meghdadfadaee.github.io/shell-gleam/setup.sh
less shell-gleam-setup.sh
bash shell-gleam-setup.sh install --wizard
```

For automation, enable `set -o pipefail` in your calling Bash shell to propagate
curl failures through the pipeline. The checksum detects payload corruption or a
script/package mismatch; it is not an independent signature of the publisher.

## What you get

- **A useful first glance:** uptime, CPU load, memory and disk bars.
- **Runtime visibility:** configurable systemd services and local Docker state.
- **Honest health checks:** failed units, cached update age, reboot and firmware notices.
  Containers without healthchecks are never described as healthy.
- **All login users:** optional PAM session display, independent rendering for concurrent logins.
- **Your style:** JSON configuration, Unicode or ASCII, colors, sections and thresholds.
- **Reversible setup:** original backups, rollback on handled errors, uninstall and reinstall support.
- **Small footprint:** Python's standard library; no network requests during login.

## Requirements

Ubuntu/Debian with Python **3.9+**, systemd, GNU `timeout`, Debian `run-parts`,
OpenSSH server and the standard `pam_motd`/`pam_exec` modules. SSH must already use
`UsePAM yes` and `PrintMotd no`. Both `/etc/pam.d/sshd` and `/etc/pam.d/login`
must have the normal dynamic MOTD entry. Preflight checks reject unsupported
setups before making system changes. Other distributions are not supported yet.
The bootstrap also needs Bash and curl; it does not install packages.

## Install from source

```bash
git clone https://github.com/meghdadfadaee/shell-gleam.git
cd shell-gleam
sudo ./setup.sh install --wizard
```

Or copy this directory to the server. `./deploy.sh root@your-server` copies it
to `/opt/shell-gleam` over SSH and installs it; set `SSH_CONFIG` if needed.

## Make it yours

```bash
sudoedit /etc/server-status/config.json
server-status --check
sudo server-status --no-color
```

The repository is named `shell-gleam`; the installed preview command and settings
path remain `server-status`. Configuration changes apply on the next login.
See [all options and examples](docs/configuration.md).

```json
{
  "title": "ORBIT",
  "services": [{"unit": "nginx.service", "label": "Nginx", "required": true}],
  "disks": ["/", "/srv"],
  "docker": false,
  "disk_warning": 70,
  "disk_critical": 85,
  "footer": "Welcome aboard."
}
```

A supplied config overlays built-in defaults. Reinstalling without overrides
preserves the server's existing config. Missing optional services are neutral;
missing required services and unavailable probes raise ATTENTION.

## Undo

```bash
sudo /opt/shell-gleam/setup.sh uninstall --dry-run
sudo /opt/shell-gleam/setup.sh uninstall
```

If installed from a checkout, run `sudo ./setup.sh uninstall` there instead.
Backups remain root-only in `/var/lib/server-status`. Uninstall restores original
PAM display entries, stock hooks and static/dynamic messages. [Details and limitations](docs/operations.md).

## Website and releases

The [website](https://meghdadfadaee.github.io/shell-gleam/) provides an interactive
dashboard preview, command builder and remote installer. GitHub Actions tests
changes and publishes the site and a checksum-verified setup package from `main`.

For release maintenance, custom domains and forks, see the
[publishing guide](docs/publishing.md).

## Development

```bash
python3 -m unittest discover -s tests -v
python3 src/server_status.py --config config/default.json --no-color
python3 scripts/build_site.py
python3 -m http.server 8000 --directory _site
```

Open `http://localhost:8000`. The site has no package manager, framework,
external fonts, trackers or third-party runtime assets. See [CONTRIBUTING.md](CONTRIBUTING.md).

MIT licensed. Demo content uses fictional hostnames and documentation-only IP addresses.
