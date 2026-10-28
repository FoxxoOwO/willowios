#!/bin/bash
# One command from a finished xnu run to a boot image that carries the GL shim:
#
#   tools/mkglboot.sh xnu-latest <out.img> ["extra boot-args"]
#
# Fetches the kernel of that run, packs libtopaz-gl/libtopaz-inject/libOSMesa from scratch/gpu
# (gh release download gpu-latest --dir scratch/gpu) into the device tree, writes the payload and
# wraps it in shim/out/shim-boot.img. Flash-and-boot it with:
#
#   fastboot boot out.img
set -e
cd "$(cd "$(dirname "$0")/.." && pwd)"
RUN=${1:?usage: mkglboot.sh <xnu run id> <out.img> [extra boot-args]}
OUT=${2:?usage: mkglboot.sh <xnu run id> <out.img> [extra boot-args]}
shift 2
EXTRA="$*"

python3 tools/fetch_kernel.py --release "$RUN"

for f in libtopaz-gl.dylib libtopaz-inject.dylib libOSMesa.8.dylib; do
	[ -f scratch/gpu/$f ] || { echo "mkglboot.sh: scratch/gpu/$f is missing (gh release download gpu-latest --dir scratch/gpu)" >&2; exit 1; }
done
python3 tools/mkblobs.py scratch/blobs.bin scratch/gpu/libtopaz-gl.dylib \
	scratch/gpu/libtopaz-inject.dylib scratch/gpu/libOSMesa.8.dylib
python3 tools/mkadt.py scratch/adt-blobs.adt --blobs scratch/blobs.bin

# sweet_blobs.c installs into the first writable of /private/var/tmp, /private/var, /tmp, /, so the
# injector has to be named where it will land; the boot log says where it went.
CL="debug=0xc serial=3 cpus=2 keepsyms=1 startup_debug=1 -v -enable_kprintf_spam rd=ufsroot0 \
unentitled_ios_sim_launch=1 ignition_level=1 launchd_unsecure_cache=1 wdt_test=no_user_checkin \
wdt=-1 ufsrw=1 rootrw=1 sweetfb_hz=60 sweetfb_noconsole=1 sweetfb_stayon=1 \
topaz_inject=/private/var/tmp/libtopaz-inject.dylib,backboardd gl=force $EXTRA"

python3 tools/mkpayload.py xnu/out/kernel.development.sweet scratch/adt-blobs.adt \
	xnu/out/payload-gl.bin --cmdline "$CL"
python3 tools/pack_evox_boot.py shim/out/shim-boot.img "$OUT" --payload xnu/out/payload-gl.bin
ls -l "$OUT"