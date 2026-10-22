#!/usr/bin/env bash
set -euo pipefail
umask 077

INSTALL_USER="${SUDO_USER:-$USER}"
INSTALL_HOME="$(getent passwd "$INSTALL_USER" | cut -d: -f6)"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Keep dependency/bootstrap files owned by the installed account, even via sudo.
if [[ "$EUID" == 0 && "$INSTALL_USER" != root ]]; then
    exec sudo -u "$INSTALL_USER" env -u SUDO_USER -u SUDO_UID -u SUDO_GID "$REPO_DIR/configure.sh" "$@"
fi

PYTHON="$INSTALL_HOME/petrel-env/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    CONFIG_VENV="$INSTALL_HOME/.config/Petrel/config-env"
    if [[ ! -x "$CONFIG_VENV/bin/python" ]]; then
        python3 -m venv "$CONFIG_VENV"
    fi
    PYTHON="$CONFIG_VENV/bin/python"
fi
if ! "$PYTHON" -c 'import kconfiglib, menuconfig' >/dev/null 2>&1; then
    "$PYTHON" -m pip install -r "$REPO_DIR/requirements-config.txt"
fi
exec "$PYTHON" "$REPO_DIR/tools/configure.py" \
    --repo "$REPO_DIR" --home "$INSTALL_HOME" --user "$INSTALL_USER" "$@"
