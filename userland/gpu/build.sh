#!/bin/bash
# The OpenGL ES library that stands behind EAGLContext in the window server (/topaz/lib/libtopaz-gl.dylib),
# and the library that puts it there (/topaz/lib/libtopaz-inject.dylib), for iOS 16.7.16 (20H392) arm64.
#
#   MESA=<dir> userland/gpu/build.sh <outdir>
#
# MESA is the directory userland/mesa/mk-mesa-mac.sh leaves its work in: libOSMesa.8.dylib (what
# draws), gl.xml (the Khronos registry, for the prototypes) and exported-gl.txt (the gl* functions
# the library has, one a line). The table of functions handed to CoreAnimation (src/eagl_slots.txt)
# is turned into obj/eagl_gen.h by userland/mkeagl.py from those three and src/eagl.c.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
USERLAND=$(dirname "$HERE")
OUT=${1:?usage: MESA=<mesa out> build.sh <outdir>}
MESA=${MESA:?set MESA to the directory mk-mesa-mac.sh wrote (libOSMesa.8.dylib, gl.xml, exported-gl.txt)}
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
CC=$(xcrun --sdk iphoneos -f clang)
T=(-target arm64-apple-ios16.0 -isysroot "$SDK" -O2 -fno-omit-frame-pointer)
mkdir -p "$OUT" "$HERE/obj"

for f in libOSMesa.8.dylib gl.xml exported-gl.txt; do
	[ -f "$MESA/$f" ] || { echo "build.sh: $MESA/$f is missing ($f)" >&2; exit 1; }
done

python3 "$USERLAND/mkeagl.py" "$HERE/src/eagl_slots.txt" "$MESA/gl.xml" "$MESA/exported-gl.txt" \
	"$HERE/eagl.c" > "$HERE/obj/eagl_gen.h"

"$CC" "${T[@]}" -dynamiclib -install_name /topaz/lib/libtopaz-gl.dylib \
	-I"$HERE/obj" -I"$HERE" \
	-framework CoreFoundation -framework IOKit -framework IOSurface -lobjc \
	"$MESA/libOSMesa.8.dylib" \
	-o "$OUT/libtopaz-gl.dylib" "$HERE/eagl.c" "$HERE/gl_osmesa.c"

"$CC" "${T[@]}" -dynamiclib -install_name /topaz/lib/libtopaz-inject.dylib \
	-framework CoreFoundation -framework IOKit -lobjc \
	-o "$OUT/libtopaz-inject.dylib" "$HERE/topaz_inject.c"

cp "$MESA/libOSMesa.8.dylib" "$OUT/"
# The three travel together, wherever the kernel installs them (/private/var/tmp when the root is
# written from the payload, /topaz/lib when patch-rootfs puts them there): @loader_path, not an
# absolute path, and an rpath so libOSMesa finds libdrm (redwood-drm) next to it.
if command -v install_name_tool >/dev/null; then
	install_name_tool -add_rpath @loader_path "$OUT/libOSMesa.8.dylib" 2>/dev/null || true
	install_name_tool -change /topaz/lib/libOSMesa.8.dylib @loader_path/libOSMesa.8.dylib \
		"$OUT/libtopaz-gl.dylib"
	install_name_tool -add_rpath @loader_path "$OUT/libtopaz-gl.dylib" 2>/dev/null || true
fi
# ad-hoc signature: AMFI here is the kernel's stand-in, but dyld wants a valid code directory
for f in "$OUT"/*.dylib; do
	codesign -f -s - "$f" >/dev/null 2>&1 || echo "build.sh: $f is unsigned" >&2
done
ls -l "$OUT"
shasum -a 256 "$OUT"/* > "$OUT/MANIFEST.sha256"