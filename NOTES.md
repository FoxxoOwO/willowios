# Technical Notes — Xiaomi Redmi Note 8T (`willow`, SM6125 `trinket`)

## 1. Device Identification & Stock Firmware Provenance

- **Device**: Xiaomi Redmi Note 8T (`willow`, NFC variant of `ginkgo`)
- **SoC**: Qualcomm Snapdragon 665 (`SM6125` / `trinket`), `msm-id = <0x18a 0x10000>`, `board-id = <0x22 0x200>`
- **Bootloader**: `BOOT.BF.3.3-00185-NICOBAR_GEN_PACK-1` (`unlocked: yes`)
- **Stock Firmware in Workspace**: `willow_global_images_V12.5.6.0.RCXMIXM_20220623.0000.00_11.0_global_f58e9a4cc8(1).tgz`
  - `boot.img`: Android Boot Image `header_version = 2`, `page_size = 4096`, `base = 0x00000000`, `kernel_offset = 0x00008000`, `ramdisk_offset = 0x01000000`, `second_offset = 0x00f00000`, `tags_offset = 0x00000100`, `dtb_offset = 0x01f00000`
  - Concatenated DTBs in `boot.img`: 10 DTBs (`rom-0.dtb`..`rom-9.dtb`); **`rom-8.dtb`** (`331,775` bytes, `Qualcomm Technologies, Inc. TRINKET SoC`) matches `willow`'s `msm-id = <0x18a 0x10000>` and is stored at [`dtb/willow/dtb`](dtb/willow/dtb).
  - `dtbo.img`: 18 overlays; **`dtbo-11.dtb`** (`WillOW QRD Overlay`, `board-id = <0x22 0x200>`) is stored at [`dtb/willow/dtbo-willow.dtb`](dtb/willow/dtbo-willow.dtb).

---

## 2. Physical Memory Map (`willow` 4 GiB DDR)

Total DRAM is 4 GiB spanning `0x40000000..0x140000000` (`memory@40000000`).

| Physical Range | Size | Description |
|---|---|---|
| `0x40000000..0x48000000` | 128 MiB | Low DDR below reserved carve-outs (ABL loads `boot.img` kernel at `0x40080000` and ramdisk around `0x44000000`) |
| `0x48000000..0x4ac00000` | 44 MiB | `other_ext_region@48000000` (TZ / XBL / Hypervisor / PIMEM) |
| `0x4b000000..0x54600000` | 150 MiB | `modem_region@4b000000` (MSS PIL) |
| `0x54600000..0x57d00000` | 55 MiB | `adsp_fw_region`, `wcnss_fw_region`, `venus_region`, `cdsp_regions`, `gpu_region`, `ipa_fw_region` |
| `0x5c000000..0x5d900000` | 25 MiB | **`cont_splash_region@5c000000`** (`1080×2340×4` = `10,108,800` bytes, stride `4320`, `BGRX8888`) |
| `0x5d900000..0x61900000` | 64 MiB | `linux,cma` / `secure_display_region` / `qseecom_region` |
| `0x61600000..0x61a00000` | 4 MiB | `ramoops@61600000` (`pstore`) |
| `0x62000000..0x80000000` | 480 MiB | **Clean low DDR**: used for Enxerto's Bergamota Fastboot download + scratch window (`0x62000000..0x80000000`) and XNU's fallback Adreno GPU pool (`0x64000000..0x7c000000`) |
| `0x80000000..0x140000000` | **3,072 MiB (3 GiB)** | **XNU Kernel Contiguous RAM (`phys_base = 0x80000000`, `mem_size = 0xc0000000`)** — 100% free of Qualcomm firmware carve-outs |

---

## 3. `willow` XNU Kernel Patch Stack (`0951..0955`)

All 5 `willow` patches live in [`xnu/patches/`](xnu/patches/) on top of the 201 `ios-sweet` / `ios-topaz` patches:

1. [`0951-willow-board-ram-display-1080x2340.patch`](xnu/patches/0951-willow-board-ram-display-1080x2340.patch)
   - Fixes early framebuffer mapping in `osfmk/arm64/start.s`, `osfmk/arm64/arm_vm_init.c`, and `osfmk/arm64/sweet_early.c` so `0x5c000000` is mapped in **both** 16K page mode (used on `willow`'s Kryo 260 Gold cluster) and 4K page mode.
   - Updates panel height from `2400` to `2340` (`1080×2340`, stage 0 band at `0x5c000000 + 2308 * 4320`, `SweetHID.cpp` touch height `2340`).
   - Moves the fallback `GPU_POOL_BASE` in `iokit/Kernel/arm/TopazAdreno.cpp` from `0xc0000000` (which is inside `willow`'s kernel RAM) to `0x64000000..0x7c000000`.
2. [`0952-willow-sdhci-emmc-root-storage.patch`](xnu/patches/0952-willow-sdhci-emmc-root-storage.patch)
   - Adds a full Qualcomm SDHCI MSM v5 (`0x04744000`) eMMC 5.1 polled block read/write driver (`CMD17`/`CMD18`/`CMD24`/`CMD25`) and 512-byte-sector GPT partition scanner to `bsd/dev/sweet_ufs.c`.
   - Exposes `userdata` (`LBA 12582912`, 512-byte sectors aggregated into 4 KiB blocks for `/dev/disk0`) as the read-write iOS root filesystem, plus `boot` (console ring log flush) and `modem_a` (firmware loader).
3. [`0953-willow-touch-nt36672a-spi-ft8719.patch`](xnu/patches/0953-willow-touch-nt36672a-spi-ft8719.patch)
   - Adds QUP0 SE2 (`0x04a88000`) GENI SPI full-duplex support and a Novatek NT36672A SPI (`TOUCH_NVT_SPI`, reset GPIO 87, IRQ GPIO 88, CS GPIO 9 in TLMM WEST `0x00500000`) multi-touch parser to `bsd/dev/sweet_touch.c`, with FocalTech FT8719/FT5452 I2C fallback.
4. [`0954-willow-pmi632-battery-charger.patch`](xnu/patches/0954-willow-pmi632-battery-charger.patch)
   - Updates `bsd/dev/sweet_spmi.c` to `trinket`'s SPMI arbiter (`0x01c40000`, `OBS = 0x03e00000`, `CFG = 0x01c0a000`) and allows USID 2 (`pmi632`).
   - Updates `iokit/Kernel/arm/SweetBattery.cpp` to read PMI632 QG (`0x4800`) and SMB5 (`0x1000..0x1300`) on USID 2.
5. [`0955-willow-usb-dwc3-qusb2-smmu.patch`](xnu/patches/0955-willow-usb-dwc3-qusb2-smmu.patch)
   - Updates `bsd/dev/sweet_usb.c` and `bsd/dev/sweet_ufs.c` for `willow`'s DWC3 (`0x04e00000`), QSCRATCH (`0x04ef8800`), QUSB2 v1 PHY (`0x01613000`), and GCC (`0x01400000`) so USB CDC-ECM Ethernet (`ue0` at `192.168.7.2/24` + UDP console log streaming to `192.168.7.1:5140`) works on `willow`.


---

## 4. Qualcomm ABL (`LinuxLoader.efi`) & Fastboot Boot Root Cause Analysis

### Reverse Engineering Summary
- Disassembled stock willow ABL `LinuxLoader.efi` (`BOOT.BF.3.3-00185-NICOBAR_GEN_PACK-1`):
  - `0x37528` `CmdBoot`: Handles `fastboot boot <img_addr>`. Calls `0x207a0` (`RestoreSplashScreen`), `0x30fd8` (`FastbootUsbDeviceStop`), then `0x12340` (`BootLinux`).
  - `0x12340` `BootLinux`:
    - Checks for DTBO (`0x25e40`). In `fastboot boot`, no `dtbo` image is present in `BootInfo`.
    - Because DTBO check fails, `BootLinux` branches to fallback path `0x13414` (Qualcomm legacy appended DTB).
    - `0x14b58`: Decompresses gzip kernel and calculates `DtbOffset` as the exact byte length of the gzip stream (`len(gzip)`).
    - `0x134c8..0x134ec`: Reads `x24 = ImageBuffer + page_size + DtbOffset` and calls `fdt_check_header(x24)`.
    - If `fdt_check_header(x24)` fails, it prints `"Error: Device Tree blob not found\n"` at `0x1351c` and returns without jumping to the kernel!
    - Because the splash screen was already restored and USB stopped, the phone froze on the splash screen.
  - `0x13ce8` `KernelJump`: `ldur x8, [x23, #-0x70]; mov x1, xzr; ldur x0, [x23, #-0x58]; mov x2, xzr; mov x3, xzr; blr x8`. Prior to jumping, calls `ExitBootServices` at `0x13b70`.
  - `0x12ae8..0x12b08`: Computes kernel entry point offset. For 64-bit kernels (`[x23, -0x10] == 0`), calculates `entry = base + 0x80000`. DTB address = `base + dtb_offset`.
  - `0x12e88..0x12eac`: ARM64 Image header validation. Reads offset 0x38 (`ARM\x64`) and offset 0x10 (`image_size`). Verifies `image_size <= (dtb_addr - kernel_addr)`. If magic doesn't match, falls back to 32-bit mode.

### 1-Bit PSCI Reset Test & EvolutionX 15 Discovery
- Discovery from `EvolutionX-15.0-20250507-ginkgo-10.6-Official.zip`:
  - EvolutionX replaced `dtbo` partition with a single-entry overlay (`count: 1, id: 0, rev: 0`).
  - EvolutionX `boot.img` uses `header_version: 0`, `os_version: 0x1e000195` (Android 15), and a single appended DTB (`evolutionx_dtb.dtb`, 286,092 bytes).
  - When we tried stock MIUI `stock_dtb_all.bin` with `header_version: 2`, ABL's `DevTreeFinalize` (`0x18410`) failed to reconcile stock board IDs (`0x22 0x200`) with EvolutionX's DTBO on eMMC, printing `"Device Tree update failed"` and aborting before `blr x8`.
- Solution: Built `shim/out/shim-boot.img` using EvolutionX's exact container format:
  - `header_version: 0`, `os_version: 0x1e000195`
  - Kernel payload: `gzip(shim_with_psci_reset) + evolutionx_dtb.dtb`
  - Ramdisk: EvolutionX ramdisk
  - Cmdline: EvolutionX cmdline
- **RESULT (2026-10-24, observed)**: the PSCI-reset shim in this format made the phone reboot, so ABL does reach `_start` with the EvolutionX layout. Stock-MIUI v2 layout never did (the guess about the `DevTreeFinalize` failure is unconfirmed; the dtbo mismatch is the likely cause).
- Reusable packer: `tools/pack_evox_boot.py <Image> <out.img>` -> `shim/out/shim-evox-boot.img`, `enxerto/out/enxerto-evox-boot.img`. Use these, not `*-boot.img` from `build_all_willow.py` (v2/MIUI layout), while EvolutionX dtbo is installed.
- Next: flash `shim-evox-boot.img` (green fill at `0x5c000000`, no reset) and check whether the screen turns green; then enxerto.
- **RESULT (observed, photo)**: shim runs from `boot` in the EvolutionX layout, console text is visible on the red framebuffer at `0x5c000000` (display path works). Boot core: `MIDR=0x51AF8014`, `MPIDR=0x80000000`, `MMFR0 lo=0x1122`, `TGran16=0`. Shim then printed "no 16K granule: handing off to gold" and nothing more (no `GOLD` line).
- **Likely blocker (inference, not verified)**: Kryo 260 gold is Cortex-A73 class; A73 also reports `ID_AA64MMFR0=0x1122`, i.e. no 16K granule on any core of SM6125. XNU arm64 needs 16K pages, so the sweet/topaz shim handoff cannot work on willow. Patch 0951 notes claiming gold has 16K are unverified.
- Pending diagnostic: rebuilt shim now also prints the `CPU_ON` return value; flash again to see whether gold starts and prints its own MMFR0.

### Root Cause & Resolution
- **Issue 1 (Appended DTB)**: In the initial `mkbootimg_willow.py`, the gzipped kernel was padded to 4096 bytes and the DTB was placed in the v2 header DTB slot. `x24` therefore pointed to 4K zero padding instead of `0xd00dfeed`.
  - **Fix**: Appended DTB directly to `kernel_bytes` (`kernel_bytes = gzip(kernel) + dtb`) while also retaining the v2 DTB section. Verified `x24` matches `0xd00dfeed` at exact offset `page_size + len(gzip)`.
- **Issue 2 (PMIC Reset in Enxerto)**: `SPMI_CHNL_BASE` in `enxerto/board.h` was set to `0x02000000` instead of `0x01e00000` (off by 2 MiB), and `enxerto/charger.c` attempted SMB2 register writes to PMI632 SMB5, triggering PMIC reset.
  - **Fix**: Set `SPMI_CHNL_BASE` to `0x01e00000` and `#define ENXERTO_CHARGER 0`.
- **Issue 3 (Secondary CPU Stack)**: Gold core stack in `enxerto/start.S` was limited to 4 KiB, overflowing in `enxerto_main`.
  - **Fix**: Secondary CPU switches SP to `_stack_top` (32 KiB primary stack) since CPU0 parks in `wfi`.

---

## 5. Build Artifacts & Verified Status

- Automated build script: [`tools/build_all_willow.py`](tools/build_all_willow.py).
- Build outputs:
  - [`shim/out/shim-boot.img`](shim/out/shim-boot.img): 1,191,936 bytes (header_version=2 matching eMMC boot with dtbo, gzip=8,306 B pure stream, dtb=1,172,101 B stock 11 DTBs).
  - [`enxerto/out/enxerto-boot.img`](enxerto/out/enxerto-boot.img): 1,294,336 bytes (header_version=2 matching eMMC boot with dtbo, gzip=114,429 B pure stream, dtb=1,172,101 B stock 11 DTBs).
  - [`enxerto/out/bergamota-fastboot.img`](enxerto/out/bergamota-fastboot.img): 1,294,336 bytes with `bergamota.fastboot=1` cmdline.

---

## 6. Active Handoff & Next Steps

1. **Root Cause Confirmation on Qualcomm Trinket (ginkgo/willow)**:
   - On Snapdragon 665 / SM6125 with Xiaomi ABL, `fastboot boot` is broken by firmware design (always freezes on Redmi splash or loops to "System has been destroyed" across all custom ROMs/recoveries).
   - The only functional boot path is booting from storage partition (`boot` or `recovery`).
2. **Flash to `boot` partition**:
   - Stock `boot.img` is safely backed up at [`scratch/stock_boot.img`](scratch/stock_boot.img).
   - Removed PSCI test reset from `shim/start.S`.
   - Command to flash shim into `boot`:
     ```cmd
     fastboot flash boot D:\repositories\willowios\shim\out\shim-boot.img
     fastboot reboot
     ```
3. **Observe Display**:
   - Immediate visual proof of life: `shim` fills `0x5C000000` with solid **GREEN**, clears screen to dark red, prints `"SHIM on willow..."`, wakes Kryo Gold core (CPU 0x100) via PSCI, prints hardware status.
4. **Restoration**:
   - To restore stock boot image anytime:
     ```cmd
     fastboot flash boot D:\repositories\willowios\scratch\stock_boot.img
     ```

---

## 7. Investigation of "This system has been destroyed", DTB Matcher & Stock v2 Layout

### Findings
1. **"The system has been destroyed"**:
   - On Xiaomi devices, when a bootloader crash/panic triggers a reset or watchdog reboot, AVB verification trips on the subsequent automatic reboot into internal storage, showing the red "The system has been destroyed" screen.
   - The user can return to fastboot anytime by holding **Volume Down + Power**.
2. **PSCI CPU_ON target address bug**:
   - Because `shim.ld` and `enxerto.ld` link at address 0, `(uintptr_t)secondary_entry` evaluates to `0x848` (relative to binary origin).
   - `smc(PSCI_CPU_ON)` requires the **physical address** (`0x40080848`).
   - Passing `0x848` caused CPU 0x100 (Kryo Gold) to wake into zero/secure memory, faulting and triggering an immediate SoC reset.
   - **Fix**: Added `get_phys_base()` using PC-relative `adr x0, _head` to dynamically add the physical load base (`0x40080000`) before issuing `PSCI_CPU_ON`.
3. **Hardware Framebuffer Visual Probe**:
   - Added a pure 6-instruction assembly loop directly at `_start` (before stack/BSS/C code) that fills `0x5C000000` (2,527,200 pixels) with solid color (Green for shim, Cyan for enxerto).
   - This provides immediate visual confirmation the instant ABL branches to `_start`.
4. **OSM Register Access Guard**:
   - Commented out `gold_cpufreq_max()` which touched LMh/OSM registers at `0x0f523000` to prevent unhandled secure data aborts.
5. **Exact Stock ABL v2 vs v0 Root Cause Analysis & Single Appended DTB Requirement**:
   - Reverse-engineered ABL `BootLinux` fallback path (`0x134c8` .. `0x13ab0`):
     - In `header_version = 2`, ABL computes `DtbOffset = (1 + ceil(k_size / page_size)) * page_size` at `0x1315c`. Then at `0x134e0`, ABL computes `x24 = ImageBuffer + page_size + DtbOffset`, adding `page_size` TWICE (off by 4096 bytes!), failing `fdt_check_header` and aborting at `0x1351c` with `"Error: Device Tree blob not found"`.
     - In `header_version = 0`, ABL branches at `0x130f4` (`b.lo 0x131c4`), preserving `DtbOffset = len(gzip)` as set by `decompress()` (`0x14b58`). Then `x24 = ImageBuffer + page_size + len(gzip)` points EXACTLY to the appended DTB (`0xd00dfeed`).
     - **Critical ABL Check at `0x13968`**: ABL checks for a second DTB header at `x24 + totalsize`. If a second DTB is found (multi-DTB table like `stock_dtb_all.bin`), line `0x13968` branches to `0x13a74`, prints `"Not the single appended DTB\n"` and aborts! The fallback path **strictly requires a SINGLE appended DTB** (`rom-8.dtb` = `dtb/willow/dtb`).
     - **Fix**: Set `mkbootimg_willow.py` to `header_version = 0` with pure `gzip(kernel) + dtb/willow/dtb` (single DTB). Verified exact byte alignment of `0xd00dfeed` at `page_size + len(gzip)` and no second DTB. Rebuilt all images.

- (2026-10-24, observed) Shim prints CPU_ON=0 for gold 0x100 but gold shows no debug bands (start.S band macro in secondary_entry) -> gold never runs our code. Hypothesis (untested): stale silver caches; shim now does dc civac over the image before CPU_ON. Flash shim/out/shim-evox-boot.img to test. User asked about reflashing stock firmware: not needed now; if wanted, flash only boot+dtbo+vbmeta from scratch/willow_global_images*, never recovery/modem/persist/userdata without confirmation.

- (2026-10-24) ROOT CAUSE gold not starting: shim/enxerto computed PSCI CPU_ON entry as get_phys_base()+(uintptr_t)secondary_entry, but with -fno-pic the symbol is materialised with adr (already physical), so the entry was doubled. Fixed in shim.c and enxerto.c (4 sites). My earlier dc civac range had the same bug (hung silver after 'handing off to gold'). Retest: flash shim/out/shim-evox-boot.img, expect green/yellow/blue bands + GOLD lines.

## Milestone (2026-10-24, observed from photo): gold cluster boots our code
- shim-evox-boot.img on EvolutionX dtbo: silver MIDR 51AF8014 tg16=0 -> PSCI CPU_ON 0x100 OK -> GOLD midr=51AF8002 mpidr=0x80000100, ID_AA64MMFR0=0x00101122 **tg16=1 (16K granule supported on gold)**. Earlier 'no 16K anywhere' inference was WRONG.
- GICD/GICR/timer tests pass on gold, GICR+ for aff 0x101-0x103 ok. SPEED ticks silver=0x8F9CC gold=0xEA5FFE (gold ~16x slower: low clock, no cpufreq; gold_cpufreq_max uses topaz address 0xf523000, invalid for trinket - needs willow address).
- Loader: INITRD 0x4558B000..0x456FE487 found, 'no SWEETXNU payload'. NEXT: build willow XNU kernel (ios-sweet patches + xnu/patches 0951-0955), run tools/mkpayload.py KERNEL dtb/willow/willow.adt OUT, put payload in the ramdisk of the EvolutionX-layout boot image (extend tools/pack_evox_boot.py to append it to the ramdisk).

- (2026-10-24) Workspace is now a git repo (portable MinGit at C:\Users\Teresa\tools\mingit\cmd, add to PATH) pushed to private https://github.com/FoxxoOwO/willowios (scratch/, firmware/, EvolutionX zip, graphify-out ignored). XNU cannot be built on Windows -> CI. xnu.yml run 40125739744 started 19:32Z (push to main). Fetch: gh run download 40125739744 -R FoxxoOwO/willowios -n xnu-kernel -D xnu/out ; then tools/mkpayload.py + extend pack_evox_boot.py to append payload to ramdisk.

## Milestone (2026-10-24, verified): XNU kernel artifact downloaded and packed into boot image
- CI run 40125739744 built XNU kernel successfully (18 MB Mach-O, xnu/out/kernel.development.sweet).
- tools/mkpayload.py resolved fixups and packed kernel + willow.adt into xnu/out/payload.bin (17,437,712 bytes, magic SWEETXNU).
- Extended tools/pack_evox_boot.py to take --payload <path> as ramdisk.
- Packed shim/out/shim-evox-boot.img (17,739,776 bytes) containing full willow XNU kernel payload.
- Ready for device boot test!

## MILESTONE (2026-10-24, OBSERVED AND PHOTOGRAPHED): XNU KERNEL BOOT SUCCESS ON WILLOW!
- Real Apple XNU Kernel booted natively on Redmi Note 8T (willow, SM6125 Trinket).
- Kryo 260 Gold cluster at 2016 MHz, GICv3 interrupts, 1080x2340 framebuffer direct scanout @ 0x5c000000 stride 4320.
- AppleKeyStore, IOWatchdog, IOCoreSurfaceRoot, SweetHID buttons & touch, MAC framework, AMFI, VM bootstrap, Mach zones, Firehose logging all initialized.
- Reached BSD init waiting for root device.
- Rebuilt payload with rd=ufsroot0 to trigger willow SDHCI eMMC 5.1 (0x04744000) driver and GPT userdata partition scanner.
- Packed shim/out/shim-evox-boot.img ready for test.

- Rebuilt payload with startup_debug=1 -v rd=ufsroot0 to make XNU verbose on kernel_bootstrap_thread execution.
- Ready for device boot test!

## Root Cause Discovery: Silent Console & `kprintf` Suppression (2026-10-25)
- Discovered why console appeared frozen after `debug_log_init: Error!! gPanicBase is still not initialized`:
  1. `debug_log_init()` prints a warning when `gPanicBase` is uninitialized and returns cleanly (no hang, no crash).
  2. All subsequent initialization logs (`kernel_bootstrap_log`, `kernel_bootstrap_thread_log`) use `kprintf()`.
  3. In `xnu/pexpert/arm/pe_kprintf.c`, `DEVELOPMENT` builds default to `disable_kprintf_output = true` unless `-enable_kprintf_spam` is present in `boot-args`.
  4. Without `-enable_kprintf_spam`, all bootstrap/thread progress logging was silently suppressed.
- Rebuilt payload and boot image with `-enable_kprintf_spam`:
  - Cmdline: `debug=0xc serial=3 cpus=1 keepsyms=1 startup_debug=1 -v -enable_kprintf_spam rd=ufsroot0`
  - Regenerated `xnu/out/payload.bin` and packed [`shim/out/shim-evox-boot.img`](shim/out/shim-evox-boot.img).
- Next action: Put phone in fastboot mode (Vol Down + Power), flash [`shim/out/shim-evox-boot.img`](shim/out/shim-evox-boot.img), and observe the unsuppressed kernel bootstrap sequence.

## MILESTONE (2026-10-25, OBSERVED AND PHOTOGRAPHED): BSD SUBSYSTEM REACHED & ROOT CAUSE OF FROZEN SCREEN!
- Real Apple XNU Kernel on Willow (`kernel.development.sweet`) booted all the way through Mach, BSD, and IOKit into `IOKitInitializeTime()`!
- Verified from photo `media_1792908194021_399db4bb.jpg`:
  - `bsd_init: [8] current_uthread` -> `[8.1] current_uthread done`
  - `bsd_init: [9] calling mac_policy_initbsd` -> `MAC Framework successfully initialized` -> `[9.1] mac_policy_initbsd done`
  - `bsd_init: calling kauth_cred_create`
  - `bsd_init: calling chgproccnt`
  - `bsd_init: calling kmem_suballoc`
  - `bsd_init: calling bsd_bufferinit` -> `using 3883 buffer headers and 3883 cluster IO buffer headers`
  - `bsd_init: calling IOKitInitializeTime`
  - `SWEET CPU: 1/1 CPUs initialized, SGI1 verified`
  - `SWEET FB: DSI0 ctrl 0x1f7, brightness via DCS 0x51`
  - `SWEET FB: empty IOAcceleratorES published (no 30 s wait in CAMetalContextCreate)`
  - `SWEET INTF1: te_en 0x1 config 0x80800000 hsync 0x50c0002 vsync_period 0x2e8bac ...`
  - `SWEET FB: MDP VIGO src 0x5c000000 stride 4320 (boot), direct scanout ready`
- **Root Cause of Screen Freeze**:
  - Right after printing `SWEET FB: MDP VIG0 ... direct scanout ready`, `SweetFramebuffer.cpp` allocates a shadow frame `fCons` and calls `sweet_console_retarget((vm_offset_t)c)`.
  - This redirected `video_console` (`vinfo.v_baseaddr`) from the physical boot framebuffer `0x5c000000` to DRAM buffer `c`.
  - Because Trinket / continuous splash display controller does not dynamic page-flip without full DPU clock/bus handover, the screen continued scanning `0x5c000000`, while all subsequent kernel logging went into the unseen shadow buffer `c`!
- **Resolution**:
  - Added patch `0957-willow-fb-direct-console.patch`: requires boot-arg `sweetfb_shadow=1` to allocate shadow buffer; by default leaves `fCons = NULL`, so `sweet_console_retarget` is never called and the console draws directly to `0x5c000000` throughout the entire boot!

## MILESTONE (2026-10-25, OBSERVED AND PHOTOGRAPHED): FULL CONSOLE UNBLOCKED & SDHCI STORAGE REACHED!
- Real Apple XNU Kernel on Willow with patch 0957 kept console directly on `0x5c000000` throughout entire boot!
- Verified from photo `media_1792909168120_5348aa98.jpg`:
  - `bsd_init: calling proc_uuid_policy_init()`
  - `mcache: 1 CPU(s), 64 bytes CPU cache line size`
  - `bsd_init: calling mbinit` -> `mbinit: done [64 MB total pool size, (42/21) split]`
  - `bsd_init: calling audit_init`, `knote_init`, `eventhandler_init`, `aio_init`, `pshm_cache_init`
  - `dlil_init: All the created dlil kernel threads have been scheduled at least once. Proceeding.`
  - `bsd_init: calling socketinit`, `domaininit`, `skywalk_init`
  - Skywalk memory regions initialized, all 18 Skywalk self-tests PASSED (`sk_copy64`, `sk_copy32`, `sk_zero`, `memcmp mask`)
  - `bsd_init: calling memorystatus_init`, `sysctl_mib_init`, `bsd_autoconf`, `kminit`, `loopattach`
  - Network interfaces `lo0`, `gif0`, `stf0` attached and threads scheduled
  - `bsd_init: calling ether_family_init`, `net_init_run`, `inittodr`
  - `bsd_init: calling setconf`
  - `SWEET UFS: willow SDHCI eMMC host ready (pstate=0x1f800f0)`!
  - `panic: IOFindBSDRoot: SWEET UFS root ufsroot0 unavailable: 60 @IOKitBSDInit.cpp:778` (60 = `ETIMEDOUT`)
- **Action**:
  - Observed from photo `media_1792914324240_d269d049.jpg`:
    - Kernel booted cleanly without GCC abort.
    - `SWEET UFS: init: hctrl=0 clk=0x7 pstate=0x1f800f0 vspec=0x300a0c hc_mode=0`
    - SD bus power in `SDHCI_HOST_CONTROL` byte 1 (`SDHCI_POWER_CONTROL` at 0x29) was `0` (bus power off!).
    - `SDHCI_INT_ENABLE` lacked bit 15 (`SDHCI_INT_ERROR`), preventing error reporting in `INT_STATUS`.
    - Clock divider was at 0 (full uncalibrated frequency).
  - Updated patch `0958-willow-sdhci-diag.patch`:
    - Powers ON the SD bus (`SDHCI_POWER_ON` = 0x01 in byte 1 of `0x28`).
    - Enables ALL error and normal interrupt status bits (`SDHCI_INT_ENABLE = 0xffffffffu`).
    - Configures safe clock divider `N = 8` (divide by 16) and sets hardware timeout counter (`0x0E`) in byte 2 of `0x2C`.
    - Logs controller capabilities (`0x40`, `0x44`) and full 32-bit register states.
    - Strictly maintains 32-bit DWORD aligned accesses throughout.
  - Built in CI run `40174285141` (commit `bf9b65a`), downloaded `kernel.development.sweet`, generated `xnu/out/payload.bin` and repacked `shim/out/shim-evox-boot.img` (17,756,160 bytes).
- **Observed on Hardware (Photo `media_1792915870192_8cd84861.jpg`)**:
  - `SWEET UFS: init: hctrl=0xf00 clk=0xe0807 pstate=0x1f800f0 cap=0x742dc8b2 cap1=0x808f`
  - Bus power and clock were alive!
  - `CMD17` (read sector 0) received response and card transmitted data (`pstate=0x1f8002f6`, `Read transfer active: 1`, `DAT line active: 1`).
  - Error: `SDHCI: DATA error! is=0x208000` (`SDHCI_INT_DATA_CRC = 0x200000`).
  - Cause: Host controller was in 1-bit bus width (`hctrl=0xf00`, byte 0 was 0), but eMMC card was left by ABL in 8-bit bus width (`qcom,bus-width = <8>`). Controller read only DAT0 and CRC check failed.
  - Also: Controller capabilities (`0x40`) confirmed voltage is 1.8V (bit 26 = 1), not 3.3V.
- **Observed on Hardware (Photo `media_1792917155582_f3bef44d.jpg`)**:
  - `SWEET UFS: eMMC card status 0x900 (state=4, rca=2)`!
  - RCA is 2, card is alive and in TRAN state (`state=4`), ready for data (`0x900`).
  - `dll=0x6000642c` (DLL powered down & reset), `hc2=0` (SDR mode).
  - Cause of `DATA error! is=0x208000`: ABL left the eMMC chip in HS400 DDR mode (`0x06`). The host controller was sampling in SDR mode (only on rising clock edge), dropping every second half-word and causing CRC error.
## MILESTONE (2026-10-25, OBSERVED AND PHOTOGRAPHED): FULL XNU BOOT TO VFS_MOUNTROOT & eMMC STORAGE WORKING!
- Verified from photos `media_1792918469069_ef41b1d5.jpg` and `media_1792918471137_a4aa6655.jpg`:
  - `SWEET UFS: eMMC card status 0x900 (state=4, rca=2)`
  - JEDEC HS400 exit to High-Speed SDR via `CMD6` succeeded!
  - Sector 0 read PASSED without CRC errors!
  - SDHCI eMMC host scanner read the GPT partition table and matched `userdata` partition!
  - `BSD root: ufsroot0, major 1, minor 0`
  - `bsd_init: vfs_mountroot` -> read volume header from `userdata`!
  - `hfs_ValidateHFSPlusVolumeHeader: unknown Volume Signature : 1020`
  - Real-time subsystems verified active:
    - Display scanout: `SWEET INTF1: 318 frames in 5 s` (~60 FPS with active TE sync)
    - Hardware keys: `SWEET KEYS: key=0 down=1 pon=0xe3 gpio4:c110=0x1`, `SWEET HID: key 0x30 down` (power/volume buttons dispatching HID events)
    - Battery: `SWEET BATTERY: static fallback, 100% 4200mV external=1 charging=0`
    - Touch: `SWEET TOUCH: mapping GCC/TLMM/SE2`
  - XNU kernel is running interactively in `vfs_mountroot` retry loop waiting for an HFS+/APFS filesystem on `userdata`.

## MILESTONE (2026-10-25, OBSERVED AND PHOTOGRAPHED): LIBIGNITION & LAUNCHD.1 BOOTED!
- User flashed updated `shim/out/shim-evox-boot.img` with `unentitled_ios_sim_launch=1`.
- Verified from photo `media_1792925275652_27d592a5.jpg`:
  - `libignition: 1: hello: hello from launchd.1`!
  - `libignition: 1: dylib_cache: opened shared cache directory: /System/Library/Caches/com.apple.dyld`!
  - `libignition: 1: goodbye: ignition sequence complete`!
  - launchd completed ignition phase 1 and invoked `vm_shared_region_map_file()`.
  - Panic: `panic(cpu 0): initproc failed to start - exit reason namespace 6 subcode 0x1 description: Library not loaded: /usr/lib/libSystem.B.dylib (no such file, no dyld cache)`.
  - Root cause logged on screen:
    - `shared_region: ... map('...:dyld_shared_cache_arm64'): not in trust cache` -> falls back to `root_check:` in `bsd/vm/vm_unix.c`.
    - `shared_region: ... map('...:dyld_shared_cache_arm64'): owned by uid=501 instead of 0` -> `root_check` failed with `EPERM` because the image was created on macOS runner with runner UID 501.
    - `vm_shared_region_start_address() failed` -> dyld shared cache was not mapped into address space, so dyld could not find `/usr/lib/libSystem.B.dylib`.
- Resolution:
  - Added patch `0959-willow-shared-region-uid-check.patch`: allows dyld shared cache with non-root UID (501) and bypasses `SF_RESTRICTED` SIP flag under `ARM64_BOARD_CONFIG_SWEET`.
  - Pushed to main (commit `2518536`).
  - GitHub Actions run `40186601695` completed with `success` in 2m45s.
  - Downloaded updated `kernel.development.sweet` (18,052,352 bytes).
  - Regenerated `xnu/out/payload.bin` with complete boot-args.
  - Repacked [`shim/out/shim-evox-boot.img`](shim/out/shim-evox-boot.img) (17,756,160 bytes).
## HISTORIC MILESTONE (2026-10-25, OBSERVED AND PHOTOGRAPHED): FULL iOS 16 USERLAND BOOTED ON WILLOW!
- User flashed updated `shim/out/shim-evox-boot.img` with patch 0959.
- Verified from 5 hardware photos (`media_1792942671748_34f38eac.jpg`..`media_1792942681136_0ad3c494.jpg`):
  - **Shared Cache Mapped**: dyld shared cache loaded, `libSystem.B.dylib` mapped, all 43 split shared cache slices mapped into userland.
  - **System Daemons Executing**:
    - `launchd`: "Early boot complete. Continuing system boot."
    - `notifyd`, `userinit`, `blueflood`, `fairplayd_H2`, `AMFI_PST_Loader`
    - `fseventsd`, `watchdogd`, `lockdownd`
    - `backboardd`: Window server & event dispatch daemon initialized!
    - `SpringBoard` (PID 26): Main iOS Home Screen GUI process active!
    - `driverkitd`, `AppleCredentialManagerDaemon`, `dumpd`, `tangent`, `thermalmonitord`, `timed`, `sharingd`, `containermanagerd`, `distnoted`, `locationd`, `wifid`, `configd`, `mediaserverd`, `ptpd`, `chronod`, `passd`, `apsd`, `cfprefsd`, `corespeechd`, `securityd`, `mobileassetd`, `nehelper`, `bluetoothd`, `nsurlsessiond`, `liveactivitiesd`, `coreduetd`, `CloudKeychainProxy`, `ReportCrash`, `triald`, `biomed`, `assistantd`, `contextstored`, `ManagedSettingsAgent`, `apfs_iosd`, `ACCHWComponentAuthService`.
  - **Hardware Interaction**:
    - `SWEET TOUCH`: `SweetHIDTouch` opened by `IOHIDEventServiceUserClient` (`backboardd`) — touch input routed directly to iOS!
    - `SWEET HID`: `SweetHIDButtons` opened by `backboardd` — volume and power buttons active!
    - `SWEET AKS`: AppleKeyStore serving cryptographic tokens for all system daemons!
    - `SWEET INTF1`: continuous splash 60 FPS scanout active (`302 frames in 5 s`).
    - `SMP`: Process sampler tracing backtraces of `SpringBoard` and `backboardd` threads running normally in `CFRunLoopRun()`.
- Display Transition:
  - Repacked payload with `sweetfb_noconsole=1 sweetfb_stayon=1`:
    `cmdline: debug=0xc serial=3 cpus=1 keepsyms=1 startup_debug=1 -v -enable_kprintf_spam rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 launchd_unsecure_cache=1 wdt_test=no_user_checkin wdt=-1 ufsrw=1 rootrw=1 sweetfb_hz=60 sweetfb_noconsole=1 sweetfb_stayon=1`
  - Output image ready at [`shim/out/shim-evox-boot.img`](shim/out/shim-evox-boot.img) (17,756,160 bytes).
  - Next Action: Flash `shim/out/shim-evox-boot.img` via fastboot and observe graphical transition.






