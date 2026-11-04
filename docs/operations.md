# Operations and implementation

## System-wide login

The installer writes a root-owned renderer at `/usr/local/bin/server-status`,
JSON settings at `/etc/server-status/config.json` and a bounded shell wrapper at
`/etc/update-motd.d/00-server-status`.

It replaces only the dynamic MOTD session-display entry in `/etc/pam.d/sshd`
and `/etc/pam.d/login` with optional `pam_exec.so stdout type=open_session`.
Every session receives independent output, avoiding the shared dynamic MOTD
cache race during concurrent logins. Authentication and authorization rules and
SSH daemon settings are unchanged. The second static MOTD entry remains intact;
`/etc/motd` is emptied with its original content backed up. No daemon restart is
needed. SSH's normal `Last login` line remains.

Standard executable MOTD scripts are renamed with `~server-status-disabled`.
The installer checks `run-parts --lsbsysinit --test /etc/update-motd.d` to ensure
only the managed hook remains selected. The tilde matters: ordinary run-parts
and PAM's LSB mode accept different filenames. Renaming in place preserves
relative symlinks and avoids changing a linked package-owned file's mode.

## Bounded probes

External probes run concurrently with configurable individual timeouts. The
wrapper adds a six-second overall timeout and one-second kill grace period.
It shows an unavailable notice on failure and returns success to PAM. Kernel
uninterruptible I/O cannot be forcibly timed out by normal userspace tools.
Python runs with `-I`, the command PATH is fixed, and text control characters
are removed. Only root should be able to modify installed code and settings.

Login does not access the network, run apt, or install dependencies. Package
updates come from Ubuntu's existing update-notifier cache; missing or old data
is unknown/stale. `/run/reboot-required` is an OS hint, not an independent audit.
Docker queries the local socket regardless of caller Docker context; containers
without healthchecks are not labeled healthy. A manual preview runs with the
caller's permissions and may show Docker unavailable without sudo.

## Backup, reinstall, uninstall

Original content, mode, ownership and symlink targets are recorded once per path
in `/var/lib/server-status/manifest.json`; the directory is root-only. Each
operation also snapshots its current touched files for exception rollback.
`flock` serializes installation changes; replacement writes are atomic per file.

Reinstall preserves current settings unless overrides are supplied. It also
disables new package MOTD hooks. After package upgrades, rerun setup if stock
messages or PAM display entries reappear.

Uninstall restores pre-install content, including both PAM files, and retains
backups. Save later manual edits you want to keep before uninstalling. File
replacement and exception rollback are not a multi-file power-loss transaction.
After SIGKILL or power loss, inspect the newest backup folder and manifest before
proceeding. VM snapshots provide a stronger recovery boundary.

## Troubleshooting

Check `server-status --check`, `sudo server-status`, `sudo sshd -T`, executable
hook permissions and the two PAM session-display entries. User MOTD opt-outs,
non-login shells, `su`/`sudo`, and SSH command/SFTP sessions do not necessarily
show a login message. Noninteractive SSH command output should remain clean.

Extra messages may come from `/etc/motd.d`, `/run/motd.d`, `/usr/lib/motd.d`, user
shell files or SSH `Banner`; those sources are not removed. Fixed-width Unicode
output depends on your terminal font. Select ASCII mode and a smaller width for
limited terminals.

## Remote bootstrap

GitHub Pages serves a generated Bash bootstrap and a versioned archive whose
SHA-256 is embedded in that script. Download and verification happen before
sudo and installation. The extractor rejects links, traversal paths and large
unexpected archives. The package is built from an explicit file allowlist;
local dotfiles, deployment notes, credentials and arbitrary files cannot enter
it by a recursive copy. Checksums detect mismatches and corruption, not a
compromised publisher. The website makes no requests to visitors' servers.

The verified source is retained in `/opt/shell-gleam` for future uninstall. Dry
runs execute from the temporary package without copying it into `/opt`.
Temporary downloads are removed on exit. For local integration tests only,
`SHELL_GLEAM_BASE_URL=http://127.0.0.1:PORT` can point to a local build.
