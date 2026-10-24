#!/bin/bash
# Build Enxerto (the bootloader + USB fastboot environment) for Xiaomi Redmi Note 8T (willow).
#   BOARD=willow (default) boot.img v2 with dtb/willow/dtb (rom-8.dtb, msm-id 0x18a 0x10000)
#   BOARD=topaz            boot.img v4
#   BOARD=sweet            boot.img v2
#   BOARD=beryllium        boot.img v1
# Usage: [BOARD=..] [DTB=..] ./build.sh [payload.bin]
set -euo pipefail
cd "$(dirname "$0")"
BOARD=${BOARD:-willow}
if [ -z "${CROSS:-}" ]; then
	if command -v aarch64-linux-gnu-gcc >/dev/null; then CROSS=aarch64-linux-gnu-; else CROSS=aarch64-elf-; fi
fi
CC=${CROSS}gcc
OBJCOPY=${CROSS}objcopy
READELF=${CROSS}readelf
NM=${CROSS}nm
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -mgeneral-regs-only -mstrict-align -fno-stack-protector -fno-tree-loop-distribute-patterns -Wall -Wextra"
[ "${BOOTLOG:-0}" = 0 ] || CFLAGS="$CFLAGS -DBOOTUI_LOG=1"
[ "${CHARGER:-1}" != 0 ] || CFLAGS="$CFLAGS -DENXERTO_CHARGER=0"
[ -z "${BOOTPAUSE:-}" ] || CFLAGS="$CFLAGS -DBOOT_PAUSE_MS=${BOOTPAUSE}"
case $BOARD in
willow)		DTB=${DTB:-../dtb/willow/dtb}; CFLAGS="$CFLAGS -DBOARD_WILLOW" ;;
topaz)		DTB=${DTB:-../dtb/willow/dtb}; CFLAGS="$CFLAGS -DBOARD_TOPAZ" ;;
sweet)		DTB=${DTB:-../dtb/boot_unpacked/dtb}; CFLAGS="$CFLAGS -DBOARD_SWEET" ;;
beryllium)	DTB=${DTB:-../dtb/beryllium/dtb}; CFLAGS="$CFLAGS -DBOARD_BERYLLIUM" ;;
*)		echo "error: unknown BOARD=$BOARD" >&2; exit 1 ;;
esac
[ -f "$DTB" ] || { echo "error: $DTB missing" >&2; exit 1; }
mkdir -p out
CMDLINE="console=null"
case ${BERGAMOTA:-} in
1) CMDLINE="$CMDLINE bergamota.fastboot=1" ;;
0) CMDLINE="$CMDLINE bergamota.fastboot=0" ;;
esac
SRCS="start.S enxerto.c console.c bootui.c fbui.c mmu.c fdt.c loader.c ufs.c inflate.c usb_dwc3.c usb_power.c fastboot.c sparse.c storage.c blake2b.c bergamota.c pmic.c charge.c charge_mode.c charger.c"
OBJS=""
for f in $SRCS; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
	OBJS="$OBJS out/${f%.*}.o"
done
abs=$($READELF -r ${OBJS//out\/start.o/} | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS -static -T enxerto.ld -Wl,--build-id=none -Wl,--no-warn-rwx-segments -Wl,-N \
	$OBJS -o out/enxerto.elf -lgcc
$OBJCOPY -O binary out/enxerto.elf out/Image
size=$($NM out/enxerto.elf | awk '$3=="_end"{print $1}')
python3 -c "import sys; open(sys.argv[1],'r+b').truncate(int(sys.argv[2],16))" out/Image "$size"

if [ "$BOARD" = willow ]; then
	if [ -n "${1:-}" ]; then
		python3 ../tools/mkbootimg_willow.py -k out/Image -r "$1" -d "$DTB" -c "$CMDLINE" -o out/enxerto-boot.img
	else
		python3 ../tools/mkbootimg_willow.py -k out/Image -d "$DTB" -c "$CMDLINE" -o out/enxerto-boot.img
	fi
	python3 ../tools/mkbootimg_willow.py -k out/Image -d "$DTB" -c "console=null bergamota.fastboot=1" -o out/bergamota-fastboot.img
	cp out/bergamota-fastboot.img out/bergamota-flash.img
fi
mkdir -p out/preview
cc -O1 -Wall -DBOARD_WILLOW -o out/host_test console.c bootui.c fbui.c charge.c host_test.c && ./out/host_test
cc -O1 -Wall -Wextra -o out/fastboot_test fastboot.c sparse.c storage.c blake2b.c fastboot_test.c && ./out/fastboot_test
ls -lh out/Image out/enxerto-boot.img
