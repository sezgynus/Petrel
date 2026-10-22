#!/usr/bin/env bash
# Build controlled PN532 libnfc target variants from the SAME pinned source.
# 04: PICC-only; 05: upstream; diag: native trace; modedet: bit-2 experiment.
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

MODE="${1:-04}"
case "$MODE" in
    04|05|diag|modedet) ;;
    *) echo "Usage: $0 [04|05|diag|modedet]" >&2; exit 2 ;;
esac
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
ROOT="$DATA_HOME/Petrel"
case "$MODE" in
    04) TARGET="$ROOT/libnfc-pn532-picc" ;;
    05) TARGET="$ROOT/libnfc-pn532-mode05" ;;
    diag) TARGET="$ROOT/libnfc-pn532-diagnostics" ;;
    modedet) TARGET="$ROOT/libnfc-pn532-modedet" ;;
esac
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
if [ "$MODE" = diag ]; then
    python3 "$SCRIPT_DIR/nfc_pn532_diag_patch.py" \
        "$WORK/libnfc/libnfc/chips/pn53x.c"
elif [ "$MODE" = modedet ]; then
    python3 "$SCRIPT_DIR/nfc_pn532_picc_patch.py" --mode 04 \
        "$WORK/libnfc/libnfc/chips/pn53x.c"
    python3 "$SCRIPT_DIR/nfc_pn532_modedet_patch.py" \
        "$WORK/libnfc/libnfc/chips/pn53x.c"
else
    python3 "$SCRIPT_DIR/nfc_pn532_picc_patch.py" --mode "$MODE" \
        "$WORK/libnfc/libnfc/chips/pn53x.c"
fi
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
if [ "$MODE" = diag ]; then
    printf 'libnfc-1.8.0 PN532 target diagnostics mode=0x05 v1\n' \
        > "$WORK/staged/.petrel-nfc-diagnostics"
elif [ "$MODE" = modedet ]; then
    printf 'libnfc-1.8.0 PN532 ModeDetOff mode=0x04 bit=0x04 v1\n' \
        > "$WORK/staged/.petrel-nfc-modedet"
else
    printf 'libnfc-1.8.0 PN532 Type4 test mode=0x%s\n' "$MODE" \
        > "$WORK/staged/.petrel-pn532-picc"
fi
if [ -d "$TARGET" ]; then
    BACKUP="$WORK/old-install"
    mv "$TARGET" "$BACKUP"
fi
mv "$WORK/staged" "$TARGET"
echo "PN532 $MODE library installed: $TARGET/lib/libnfc.so.6"
if [ "$MODE" = diag ]; then
    echo "Choose profile A or B, then python3 tools/nfc_target_diag.py enable."
elif [ "$MODE" = modedet ]; then
    echo "Choose profile C, then python3 tools/nfc_target_modedet.py enable."
else
    echo "Use python3 tools/nfc_target_ab.py select A|B|C|D then restart Petrel.service."
fi
echo "Restart Petrel.service to load the selected library."
