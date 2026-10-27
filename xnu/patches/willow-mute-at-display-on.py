#!/usr/bin/env python3
"""
willow-mute-at-display-on.py  (applied by xnu.yml after git-apply patches)

Patches iokit/Kernel/arm/SweetFramebuffer.cpp in the dxb/xnu tree to:
  1. Remove the dead sweet_first_swap block from swap() — SwapEnd never
     arrives because backboardd blocks in mach_msg waiting for a vsync
     notify that SweetFramebuffer doesn't deliver before the first swap.
  2. Add a mute trigger in externalMethod's default: case for selector 12
     (display on from backboardd) — always arrives before SwapBegin.
"""
import re, sys, pathlib

src = pathlib.Path('dxb/xnu/iokit/Kernel/arm/SweetFramebuffer.cpp')
if not src.exists():
    sys.exit(f'not found: {src}')

text = src.read_text()

# 1. Remove sweet_first_swap block from swap() (added by patch 0960)
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

new_swap_block = '''\tsweet_fps_count();
\tSweetSurface'''

if old_swap_block in text:
    text = text.replace(old_swap_block, new_swap_block, 1)
    print('removed sweet_first_swap block from swap()')
else:
    print('sweet_first_swap block not found (already removed or patch 0960 not applied) — skipping')

# 2. Add display-on mute in externalMethod default: case before break;
# The unique context is:  case kSweetFBSwapWait:\n\tdefault:\n\t\tbreak;
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
else:
    sys.exit('ERROR: default: case context not found — cannot apply mute patch')

src.write_text(text)
print(f'patched {src}')
