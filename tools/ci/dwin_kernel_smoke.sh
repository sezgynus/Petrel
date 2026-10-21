#!/bin/bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/../.." && pwd)"
headers_dir="$(find /usr/src -maxdepth 1 -type d -name 'linux-headers-*-amd64' | sort -V | tail -n 1)"
: "${headers_dir:?No packaged kernel headers found}"
make -C "$repo_dir/kernel/dwin_uart" KDIR="$headers_dir"
kernel_version="${headers_dir##*/linux-headers-}"
kernel_image="/boot/vmlinuz-$kernel_version"
test_dir="$(mktemp -d)"
trap 'rm -rf "$test_dir"' EXIT
mkdir -p "$test_dir/root"/{bin,dev,proc,sys}
cp /bin/busybox "$test_dir/root/bin/busybox"
cp "$repo_dir/kernel/dwin_uart/dwin_uart.ko" "$test_dir/root/"
gcc -static -O2 -Wall -Wextra -Werror "$repo_dir/tools/ci/dwin_tty_smoke.c" -o "$test_dir/root/smoke"
cat > "$test_dir/root/init" <<'INIT'
#!/bin/busybox sh
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sysfs /sys
/bin/busybox mount -t devtmpfs devtmpfs /dev
for pass in 1 2; do
    /bin/busybox insmod /dwin_uart.ko || /bin/busybox poweroff -f
    /smoke || /bin/busybox poweroff -f
    /bin/busybox rmmod dwin_uart || /bin/busybox poweroff -f
    for path in /sys/class/tty/ttyDWIN0 /sys/devices/dwin-uart /sys/bus/dwin /dev/ttyDWIN0 /dev/dwin-uart-backend; do
        if [ -e "$path" ]; then
            echo "DWIN_UNLOAD_FAILED: $path remains"
            /bin/busybox poweroff -f
        fi
    done
done
echo DWIN_LIFECYCLE_PASS
/bin/busybox poweroff -f
INIT
chmod +x "$test_dir/root/init"
(cd "$test_dir/root" && find . -print0 | cpio --null -o --format=newc 2>/dev/null | gzip -1 > "$test_dir/initramfs.gz")
timeout 90 qemu-system-x86_64 -m 256 -nographic -no-reboot \
    -kernel "$kernel_image" -initrd "$test_dir/initramfs.gz" \
    -append 'console=ttyS0 panic=-1 quiet' > "$test_dir/console.log" 2>&1 || {
    cat "$test_dir/console.log"
    exit 1
}
cat "$test_dir/console.log"
grep -q 'DWIN_SMOKE_PASS' "$test_dir/console.log"
grep -q 'DWIN_IDENTITY_PASS hardware_uart petrel_uart' "$test_dir/console.log"
grep -q 'DWIN_LIFECYCLE_PASS' "$test_dir/console.log"
