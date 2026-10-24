#!/bin/bash
# Build the willow bare-metal shim and wrap it in an Android Boot Image v2
# (header_version = 2, page_size = 4096, DTB = dtb/willow/dtb = rom-8.dtb).
set -euo pipefail
cd "$(dirname "$0")"
CC=${CC:-aarch64-linux-gnu-gcc}
OBJCOPY=${OBJCOPY:-aarch64-linux-gnu-objcopy}
READELF=${READELF:-aarch64-linux-gnu-readelf}
NM=${NM:-aarch64-linux-gnu-nm}
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"
mkdir -p out
for f in start.S shim.c console.c mmu.c fdt.c loader.c ufs.c; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
done
abs=$($READELF -r out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
	out/start.o out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o -o out/shim.elf
$OBJCOPY -O binary out/shim.elf out/Image
size=$((16#$($NM out/shim.elf | awk '$3=="_end"{print $1}')))
python3 -c "import sys; open(sys.argv[1],'r+b').truncate(int(sys.argv[2]))" out/Image "$size"

if [ -n "${1:-}" ]; then
	python3 -c '
import os, struct, sys
img_path, pay_path = sys.argv[1], sys.argv[2]
with open(img_path, "rb") as f:
    img = f.read()
with open(pay_path, "rb") as f:
    pay = f.read()
aligned = (len(img) + 0xfff) & ~0xfff
out = bytearray(img.ljust(aligned, b"\x00") + pay)
struct.pack_into("<Q", out, 16, len(out))
with open(img_path, "wb") as f:
    f.write(out)
' out/Image "$1"
fi

python3 ../tools/mkbootimg_willow.py -k out/Image -d ../dtb/willow/dtb -o out/shim-boot.img
gcc -O1 -Wall -o out/host_test console.c host_test.c && ./out/host_test
ls -l out/Image out/shim-boot.img
