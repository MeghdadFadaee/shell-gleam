#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 1 || $1 == -* ]]; then
    echo "Usage: [SSH_CONFIG=path] $0 root@server" >&2
    exit 2
fi
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ssh_args=()
if [[ -n ${SSH_CONFIG:-} ]]; then
    ssh_args+=(-F "$SSH_CONFIG")
fi
tar -C "$project_dir" --exclude='__pycache__' -czf - setup.sh deploy.sh README.md src config tests docs reference |
    ssh "${ssh_args[@]}" "$1" 'mkdir -p /opt/shell-gleam && tar -xzf - -C /opt/shell-gleam && cd /opt/shell-gleam && ./setup.sh install'
