#!/usr/bin/env bash
# ShellGleam remote installer. Published by scripts/build_site.py.
set -euo pipefail

main() {
    if [[ ${1:-} == --help || ${1:-} == -h ]]; then
        cat <<'HELP'
ShellGleam — a brighter first look at your Linux server.
Usage: curl -fsSL https://meghdadfadaee.github.io/shell-gleam/setup.sh | bash -s -- [options]

Setup options: install (default), uninstall, status, --dry-run, --wizard,
              --title NAME, --address IP, --config FILE, --no-color, --ascii
Downloads and verifies a versioned package before requesting sudo.
Persistent project: /opt/shell-gleam. Live config: /etc/server-status/config.json.
HELP
        return
    fi
    local base_url=${SHELL_GLEAM_BASE_URL:-@@SITE_URL@@}
    local expected='@@SHA256@@'
    local artifact='@@ARCHIVE@@'
    local work_dir
    case "$base_url" in
        https://*) ;;
        http://127.0.0.1:*|http://localhost:*) ;;
        *) echo 'ShellGleam: download URL must use HTTPS (loopback HTTP is allowed for local testing).' >&2; return 1 ;;
    esac
    for dependency in curl python3 bash; do
        command -v "$dependency" >/dev/null || { echo "ShellGleam: install $dependency first." >&2; return 1; }
    done
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else "ShellGleam requires Python 3.9+")'
    work_dir=$(mktemp -d "${TMPDIR:-/tmp}/shell-gleam.XXXXXXXX")
    shell_gleam_temp_dir=$work_dir
    trap '[[ -z ${shell_gleam_temp_dir:-} ]] || rm -rf -- "$shell_gleam_temp_dir"' EXIT
    echo 'ShellGleam: downloading the verified setup package…'
    curl --fail --silent --show-error --location --retry 2 --connect-timeout 15 --max-time 120 \
        --proto '=https,http' --proto-redir '=https' "$base_url/$artifact" -o "$work_dir/package.tar.gz"
    python3 - "$work_dir/package.tar.gz" "$expected" "$work_dir" <<'PY'
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
archive, expected, directory = sys.argv[1:]
if hashlib.sha256(Path(archive).read_bytes()).hexdigest() != expected:
    sys.exit('ShellGleam: checksum mismatch; nothing installed.')
root = Path(directory)
with tarfile.open(archive, 'r:gz') as package:
    members = package.getmembers()
    if len(members) > 1000 or sum(m.size for m in members) > 20 * 1024 * 1024:
        sys.exit('ShellGleam: unexpected package size.')
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or '..' in path.parts or not path.parts
                or path.parts[0] != 'shell-gleam' or not (member.isfile() or member.isdir())):
            sys.exit('ShellGleam: unsafe package member; nothing installed.')
    for member in members:
        target = root / member.name
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.extractfile(member) as source, target.open('wb') as destination:
                shutil.copyfileobj(source, destination)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
print('ShellGleam: SHA-256 verified.')
PY
    local dry_run=false wizard=false
    for argument in "$@"; do
        [[ $argument != --dry-run && $argument != status ]] || dry_run=true
        [[ $argument != --wizard ]] || wizard=true
    done
    local -a elevation=()
    if [[ $(id -u) != 0 ]]; then
        command -v sudo >/dev/null || { echo 'ShellGleam: run as root or install sudo.' >&2; return 1; }
        elevation=(sudo)
    fi
    # Absolute --config paths remain valid after changing the project directory.
    # The argument array is forwarded unchanged; never evaluate user arguments.
    if $wizard && ! { : </dev/tty; } 2>/dev/null; then
        echo 'ShellGleam: --wizard requires an interactive terminal.' >&2
        return 1
    fi
    if $dry_run; then
        if $wizard; then
            "${elevation[@]}" bash "$work_dir/shell-gleam/setup.sh" "$@" </dev/tty
        else
            "${elevation[@]}" bash "$work_dir/shell-gleam/setup.sh" "$@"
        fi
    else
        local run='set -e; payload=$1; shift; mkdir -p /opt/shell-gleam; cp -R "$payload"/. /opt/shell-gleam/; exec bash /opt/shell-gleam/setup.sh "$@"'
        if $wizard; then
            "${elevation[@]}" bash -c "$run" shell-gleam "$work_dir/shell-gleam" "$@" </dev/tty
        else
            "${elevation[@]}" bash -c "$run" shell-gleam "$work_dir/shell-gleam" "$@"
        fi
    fi
}
main "$@"
