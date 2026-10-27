#!/usr/bin/env python3
"""
willow-mute-at-display-on.py  (run by xnu.yml from inside dxb/ before build.sh)

Patches iokit/Kernel/arm/SweetFramebuffer.cpp to mute the text console at
selector 12 (display on) instead of at the first SwapEnd.  SwapEnd never
arrives because backboardd blocks in mach_msg waiting for a vsync notify that
SweetFramebuffer does not deliver before the first swap; sel 12 always arrives
right after backboardd opens the display, before any SwapBegin.

Also removes the dead sweet_first_swap block that patch 0960 used to add.
Exits non-zero on failure so CI does not silently ship an unpatched kernel.
"""
import sys, pathlib

candidates = [
    pathlib.Path('xnu/iokit/Kernel/arm/SweetFramebuffer.cpp'),      # cwd = dxb/
    pathlib.Path('dxb/xnu/iokit/Kernel/arm/SweetFramebuffer.cpp'),  # cwd = repo root
]
src = next((p for p in candidates if p.exists()), None)
if src is None:
    sys.exit('ERROR: SweetFramebuffer.cpp not found (tried %s)' % ', '.join(str(p) for p in candidates))

text = src.read_text()

# 1. Remove the dead sweet_first_swap block from swap() (added by older 0960)
old_swap_block = '''\tsweet_fps_count();
\t/* willow: mute the text console at the first SwapEnd, not only when present() runs */
\tstatic bool sweet_first_swap = true;
\tif (sweet_first_swap) {
\t\tint quiet = 0;
\t\tsweet_first_swap = false;
\t\tif (PE_parse_boot_argn("sweetfb_noconsole", &quiet, sizeof(quiet)) && quiet != 0) {
\t\t\tsweet_console_muted = 1;
\t\t}
\t\tIOLog("SWEET FB: first SwapEnd, console muted=%d\\n", sweet_console_muted);
\t}
\tSweetSurface'''

if old_swap_block in text:
    text = text.replace(old_swap_block, '\tsweet_fps_count();\n\tSweetSurface', 1)
    print('removed sweet_first_swap block from swap()')
else:
    print('sweet_first_swap block not present — ok')

# 2. Add display-on mute in externalMethod's default: case, before break;
old_default = '''\tcase kSweetFBSwapWait:
\tdefault:
\t\tbreak;'''

new_default = '''\tcase kSweetFBSwapWait:
\tdefault:
\t\tif (selector == 12) {
\t\t\t/* sel 12 = display on: mute console here.
\t\t\t * SwapEnd never arrives because backboardd blocks in mach_msg
\t\t\t * waiting for a vsync notify that SweetFramebuffer does not
\t\t\t * deliver before the first swap.  sel 12 always arrives right
\t\t\t * after backboardd opens the display, before any SwapBegin. */
\t\t\tstatic bool sweet_muted_at_display_on;
\t\t\tif (!sweet_muted_at_display_on) {
\t\t\t\tsweet_muted_at_display_on = true;
\t\t\t\tint quiet = 0;
\t\t\t\tif (PE_parse_boot_argn("sweetfb_noconsole", &quiet, sizeof(quiet)) && quiet != 0) {
\t\t\t\t\tsweet_console_muted = 1;
\t\t\t\t}
\t\t\t\tIOLog("SWEET FB: display on, console muted=%d\\n", sweet_console_muted);
\t\t\t}
\t\t}
\t\tbreak;'''

if old_default in text:
    text = text.replace(old_default, new_default, 1)
    print('added display-on mute in externalMethod default: case')
elif 'sweet_muted_at_display_on' in text:
    print('display-on mute already present — ok')
else:
    idx = text.find('case kSweetFBSwapWait:')
    if idx < 0:
        sys.exit('ERROR: neither kSweetFBSwapWait nor sweet_muted_at_display_on found')
    sys.exit('ERROR: default: case context not found near kSweetFBSwapWait — inspect SweetFramebuffer.cpp')

src.write_text(text)
print(f'patched {src}')