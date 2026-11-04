# Configuration

Live file: `/etc/server-status/config.json`. Validate with `server-status --check`;
preview with `sudo server-status --no-color`. Changes appear on the next login.

`config/default.json` lists every setting. For an alternate file use
`sudo ./setup.sh install --config /absolute/path/config.json`. A supplied file
overlays built-in defaults, rather than merging with existing settings. Unknown
keys and invalid types are rejected before installation. `--wizard` prompts for
a title, address, services and disks; remote wizard setup reads `/dev/tty`.

| Key | Default / accepted values |
| --- | --- |
| `title` | Empty: automatic uppercase short hostname |
| `address` | `auto`: first IPv4 from `hostname -I`; override for multiple interfaces |
| `width` | `72`; integer 52–120, interior columns |
| `color` | `true`; manual previews honor `NO_COLOR` |
| `ascii` | `false`; use plain ASCII borders, bars and symbols |
| `sections` | `["system", "runtime", "health"]`; reorder or omit |
| `services` | Nginx and Docker, optional; up to 16 `{unit,label,required}` objects |
| `disks` | `["/"]`; 1–8 absolute filesystem paths |
| `docker` | `true`; query the local Unix socket if CLI is installed |
| `command_timeout` | `1.0`; 0.1–2 seconds per concurrent subprocess |
| `memory_warning`, `memory_critical` | `75`, `90` percent |
| `disk_warning`, `disk_critical` | `75`, `90` percent |
| `load_warning`, `load_critical` | `0.7`, `1.0` load per CPU |
| `updates_max_age_hours` | `48`; age limit for Ubuntu update-notifier data |
| `footer` | Empty; optional message |

Resource thresholds, failed units, inactive installed services, required missing
services, unknown/stale updates and unhealthy containers affect the summary.
Checks still affect the summary when their display section is hidden.
Missing optional services are neutral. A systemd active state is not an
application readiness check; configure the actual unit for your workload.

Example database configuration:

```json
{
  "title": "DATABASE",
  "services": [
    {"unit": "postgresql.service", "label": "PostgreSQL", "required": true},
    {"unit": "ssh.service", "label": "SSH", "required": true}
  ],
  "disks": ["/", "/var/lib/postgresql"],
  "docker": false,
  "disk_warning": 70,
  "disk_critical": 85
}
```

The PostgreSQL umbrella service may be active when a cluster is down; select
its specific cluster unit if needed. Settings and rendered container names are
visible to login users. Do not place secrets in the configuration.
