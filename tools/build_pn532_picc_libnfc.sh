#!/usr/bin/env bash
# Build an isolated, reversible PN532-only libnfc target-mode experiment.
# Never replace apt's libnfc6 or run as root.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run as the Petrel service user, not root." >&2
    exit 1
fi
for tool in git python3 autoreconf make gcc pkg-config; do
    command -v "$tool" >/dev/null || {
        echo "Missing build tool: $tool (see docs/user-guide.md)" >&2
        exit 1
    }
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
ROOT="$DATA_HOME/Petrel"
TARGET="$ROOT/libnfc-pn532-picc"
mkdir -p "$ROOT"
WORK="$(mktemp -d "$ROOT/.pn532-picc-build.XXXXXXXX")"
BACKUP=""
cleanup() {
    if [ -n "$BACKUP" ] && [ -d "$BACKUP" ]; then
        if [ -d "$TARGET" ]; then
            rm -rf "$BACKUP"
        else
            mv "$BACKUP" "$TARGET"
        fi
    fi
    rm -rf "$WORK"
}
trap cleanup EXIT

# Pin the exact upstream 1.8.0 commit, not an unverified moving branch.
git clone --quiet --depth 1 --branch libnfc-1.8.0 --single-branch \
    https://github.com/nfc-tools/libnfc.git "$WORK/libnfc"
HEAD="$(git -C "$WORK/libnfc" rev-parse HEAD)"
if [ "$HEAD" != "f02ff51449240102c27a97173dc495e8e7789046" ]; then
    echo "Unexpected libnfc source commit: $HEAD" >&2
    exit 1
fi
python3 "$SCRIPT_DIR/nfc_pn532_picc_patch.py" \
    "$WORK/libnfc/libnfc/chips/pn53x.c"
cd "$WORK/libnfc"
autoreconf -vis
./configure --prefix="$WORK/staged" --libdir="$WORK/staged/lib" \
    --sysconfdir=/etc --with-drivers=all --disable-static
make -j2
make install
test -f "$WORK/staged/lib/libnfc.so.6.0.0" || {
    echo "The expected libnfc.so.6 shared library was not built" >&2
    exit 1
}
# The marker prevents Petrel from selecting a partial or failed build.
printf 'libnfc-1.8.0 PN532 Type4 PICC-only mode=0x04\n' \
    > "$WORK/staged/.petrel-pn532-picc"
if [ -d "$TARGET" ]; then
    BACKUP="$WORK/old-install"
    mv "$TARGET" "$BACKUP"
fi
mv "$WORK/staged" "$TARGET"
echo "PN532 PICC-only libnfc installed: $TARGET/lib/libnfc.so.6"
echo "Restart Petrel.service to load it; to revert, remove $TARGET and restart."
