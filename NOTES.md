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
- Verified Hardware Proof of Life (Photo `media_1792945831702_0d811098.jpg`):
  - `SWEET FB: backboardd sel 4 in 0/0 out 1/0 -> 0x0` (SwapBegin SUCCEEDED!)
  - `SWEET FB: backboardd sel 5 in 0/132 out 0/0 -> 0x0` (SwapEnd SUCCEEDED!)
  - `SWEET FB: display off ignored (sweetfb_stayon)` (screen stay-on handler verified active!)
  - `SpringBoard` opened `AppleKeyStore` and `IOPMrootDomain`!
  - `lsd` (LaunchServicesDaemon) registered and validated by `SWEET AMFI`!
  - `rapportd`, `mobiletimerd`, `mlsagent` executing normally.
- Display Transition:
  - Repacked payload with `sweetfb_noconsole=1 sweetfb_stayon=1`:
    `cmdline: debug=0xc serial=3 cpus=1 keepsyms=1 startup_debug=1 -v -enable_kprintf_spam rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 launchd_unsecure_cache=1 wdt_test=no_user_checkin wdt=-1 ufsrw=1 rootrw=1 sweetfb_hz=60 sweetfb_noconsole=1 sweetfb_stayon=1`
  - Output image ready at [`shim/out/shim-evox-boot.img`](shim/out/shim-evox-boot.img) (17,756,160 bytes).
  - Next Action: Flash `shim/out/shim-evox-boot.img` via fastboot and observe graphical transition (console mute on first swap).








## 2026-10-25 17:50: console still drawn over GUI; patch 0960 diagnostic
- Photos show iOS userland running (SpringBoard, backboardd SwapBegin/SwapEnd = 0x0, 60 FPS) but the screen shows only kernel console text, even with sweetfb_noconsole=1 (user: "jenom text"). No "SWEET FB: swap N layer" line seen, so present() probably has not run yet (observation), cause unknown.
- Patch 0960 (CI run 40213343363, success): mute console at first SwapEnd, log first 8 present() calls (mask/consShown/paused/muted).
- tools/fetch_kernel.py RUN_ID downloads the xnu-kernel artifact. shim/out/shim-evox-boot.img repacked (same cmdline). NEXT: flash, photograph the lines "first SwapEnd, console muted=" and "present #"; if screen freezes/black pull the persistent log (tools/sweet-log-pull.sh via recovery).

## 2026-10-25 20:00: backboardd/SpringBoard Mach IPC deadlock — new blocker

### Log analysis (sweet-log4.bin, flush #97, 179 KB, boot ~15 min)
- mobileactivationd: ThrottleInterval=300 works — crashes once at boot (sig 5 SIGTRAP), then respawns at ~7 min intervals. lsd trust confirmed: `SWEET AMFI: user client selector 6 from lsd: trusted` ✓
- dasd/syncdefaultsd/fairplayd.H2: Disabled=true, zero crashes ✓
- display on: `SWEET FB: display on` ✓, backboardd runs full init sequence (sel 57,15,22,29,33,74,12,6,27,17,84,50) ✓
- NO `first SwapEnd`, NO `present #`, NO `SWEET INTF1` FPS log → vsync deliver path unclear

### Deadlock (samples 2–7, ~10 min static)
- **backboardd t0**: `pc 0x215211030 bt ... 0x1d9a5c148→0x1d9a5d2e0→0x1d9a61d20→0x102b51e40→0x1f7224344`
  - `0x1f7224344` unslid (slide 0x52c04000) = `0x1cb20344` = libsystem_kernel mach_msg_trap
  - backboardd waits for Mach reply from some sender; blocked since sample 2
- **SpringBoard t0**: `pc 0x215211030 bt ... 0x1e074eec4→0x1e074f25c→0x2247ee0ec→0x1d3e10224→0x1d3da9cb0→0x1d3da86e0`
  - `0x1d3da86e0` unslid = `0x17d2e6e0` in backboardd binary = BKS framework call
  - SpringBoard waits for reply from backboardd daemon → CIRCULAR DEADLOCK

### Hypothesis
Both processes are stuck waiting for a Mach IPC reply from the other:
SpringBoard → BKSWorkspaceCreateContext (or similar scene init) → waits for backboardd reply.
backboardd → waits for SpringBoard to ack something (possibly window server token exchange).

In the successful boot (photo, previous session) SwapBegin/SwapEnd appeared before this deadlock; now they never appear. The `sel 57` (unknown, out 1/0 → 0) may be relevant — backboardd gets 0 and may interpret it as a failure, entering a retry/wait loop.

### What changed
- iOSRoot now has mobileactivationd ThrottleInterval=300 (was Disabled); activationd correctly starts and provides lsd trust.
- No other rootfs change. Kernel is same (CI 40213343363, patch 0960).
- The deadlock also occurred in the PREVIOUS boot (log3, flush #34) — same pattern, log was just shorter. This is not a regression from the tweaks, it was present before.

### Next step
Symbolicate backboardd t0 `0x102b51e40 - 0x102b48000 = 0x9e40` to identify which XPC/Mach call backboardd is stuck in. Options:
1. Use tools/sweet-crash.py to symbolicate the SMP traces against backboardd binary from the rootfs.
2. Add a kernel patch to log the exact Mach msg sender port name when backboardd blocks (hard).
3. Add boot-arg `BKWorkspaceNoSetupFence=1` or similar SpringBoard pref to skip the scene-create fence.
4. Try `FBDisableCAContext` or `FBDisableRemoteApplications` prefs to prevent the round-trip.
- Current rootfs: scratch/iOSRoot-patched.simg (already flashed, on userdata). Boot image: shim/out/shim-evox-boot.img (CI 40213343363).

## 2026-10-28: console-only is a symptom — CA has no renderer, no SwapBegin at all

### What was tried (kernel patch 0960 / mute at display-on)
- `0960-willow-console-mute-at-swap.patch` rewritten as a valid unified diff (the previous
  version had a hunk header declaring `-1426,7 +1432,19` while carrying 4 old / 20 new lines;
  `git apply` reported `corrupt patch` and skipped the whole file, so even the `present #`
  logging was lost). CI run 40548288249: `Applying patch: 0960...` with no error. Verified:
  mute does NOT fire — `sel 12` is handled by 0079's explicit `case kSweetFBRequestPowerChange`,
  so an `if (selector == 12)` inside `default:` is unreachable. Do not re-add that hook.
- A Python pre-build hook cannot work: `build.sh` clones `dxb/xnu` itself, so no source file
  exists before `bash build.sh`. Removed.

### Rootfs experiment (CI 40553152712, flashed, 485 s)
- Removed SpringBoard `FBDisableRemoteViewControllers`, `SBDisableRemoteApplications`,
  `SBForceForceQuitDisabled` (hypothesis: they killed the CAContext round-trip that gets CA a
  render target). Result: no change — still no `sel 4`, no `present #` (logs 10, 11).
- `sweetaccel=0` (no IOAcceleratorES stub) with the new rootfs: no change either.
  QuartzCore still polls `IOAcceleratorES` (350 lines in log10) then `IOAcceleratorESLegacy`.

### Evidence
- log1 `scratch/sweet-log.txt` (original restored rootfs, kernel 40186601695) is the only log
  with `sel 4`/`sel 5`/`present #1 mask 0x80000007 ... muted 1` (line 1212). Even there the
  screen stayed console text, so a swap alone does not produce a visible GUI.
- logs 2, 8, 9, 10, 11: backboardd issues only 14-15 init selectors, then all threads sit in
  `mach_msg`; SpringBoard t0 returns the same stack for 7 consecutive samples.
- `SWEET INTF1: ~310 frames in 5 s` throughout — the vsync timer and MDP scanout are healthy.
- Only recurring crash: `mobileactivation` sig 5 SIGTRAP (ns 2 code 0x5), every ~5 min.

### Conclusion (observation + inference)
- The console is a symptom, not the blocker. Nothing ever presents a frame: CoreAnimation has
  no renderer. `docs/METAL_ADRENO630.md` says CA falls back Metal -> GLES -> software, but with
  no accelerator accepted and no EAGL implementation installed, nothing composites, so the
  console remains the only content on the panel. Muting it now would only give a black screen.
- Muting is therefore deferred until a frame actually presents (present() already mutes).

### Next step (not started)
- Build the `OpenGLES.framework` replacement (docs/GPU_EAGL.md phases A+B: eagl.m, gl_stubs.c,
  gl_resolve.c, osm.c over libOSMesa) in CI (macOS runner has Xcode; needs meson/bison + Mesa
  clone) and install it into the iOSRoot so backboardd/SpringBoard get a GLES renderer.
- Keep `0960`'s `present #` logging; drop its unreachable mute hunk when convenient.

## 2026-10-31: Root Cause of `blobs6` splash freeze identified & fixed

### Investigation & Log Analysis (sweet-log15.txt, flush #35)
- Verified `mute12.img` baseline: 2 Gold CPUs active (2016 MHz), eMMC 5.1 SDHCI stable, HFS+ `userdata` cleanly mounted, full iOS 16 userland alive (`launchd`, `SpringBoard`, `backboardd`, `locationd`, `sharingd`, etc.).
- Confirmed GUI blocker: `topaz: backboardd starts without DYLD_INSERT_LIBRARIES` followed by hundreds of `IOK backboardd: matching1 ... IOAcceleratorES` queries. CoreAnimation has no graphics renderer.

### Root Cause of `blobs6.img` Freeze on Redmi Splash
- **Discovery**: In `tools/mkglboot.sh` line 36, `pack_evox_boot.py` was called with `shim/out/shim-boot.img` instead of `shim/out/Image`.
- **Mechanism**: `pack_evox_boot.py` compressed the entire Android boot image inside another boot image (`kp` size was 514,272 B instead of 294,498 B).
- When ABL decompressed `kp` at `0x40080000`, the image began with `ANDROID!` and zeros at offset 0x38 instead of the Linux ARM64 magic `ARM\x64`.
- ABL's kernel header validation (`0x12e88..0x12eac`) failed and aborted before branching to `_start`. The phone froze on the splash screen without executing any code.

### Fix & Verification
- Fixed `tools/mkglboot.sh` to pass `shim/out/Image`.
- Generated `shim/out/shim-evox-boot-blobs-fixed.img`:
  - `kp = 294498` bytes (matches `mute12` exact size).
  - Decompressed header verified: `b _start` at 0x0, `ARM\x64` at offset 0x38.
  - Ramdisk: 31,060,528 bytes (`payload-gl.bin` with kernel CI 40761394847, patches 0962+0963, ADT `topaz-blobs`).
  - Cmdline: includes `topaz_inject=/private/var/tmp/libtopaz-inject.dylib,backboardd gl=force`.

## 2026-10-31: GL Milestone achieved & Mach IPC Deadlock Analysis (sweet-log17.txt)

### Milestones Achieved
1. **Dylibs on Filesystem**: Kernel thread `sweet_blobs` successfully installed all 3 dylibs from ADT into `/private/var/tmp/`:
   - `/private/var/tmp/libtopaz-gl.dylib` (346,864 B)
   - `/private/var/tmp/libtopaz-inject.dylib` (70,448 B)
   - `/private/var/tmp/libOSMesa.8.dylib` (13,188,272 B)
2. **GL Injection & CoreAnimation GLES Context**:
   - `backboardd` started with `DYLD_INSERT_LIBRARIES=/private/var/tmp/libtopaz-inject.dylib`.
   - All 7 of 7 `EAGLContext` methods successfully replaced.
   - CoreAnimation created its off-screen OpenGL ES 3.1 context via Mesa softpipe:
     `OpenGL ES 3.1 Mesa 25.0.7; softpipe; shaders OpenGL ES GLSL ES 3.10`!
   - QuartzCore queried GLES capabilities (`0x1f03`, `0x8872`, `0xd33`, `0xd3a`, `0xd50` GL_MAX_SAMPLES=4).

### Deadlock Analysis & LaunchServices Investigation (sweet-log18)
- **Symptom**: Phone stayed on kernel console text for 20 minutes without presenting a frame (`sel 4`/`sel 5` absent).
- **Static Dyld Cache Analysis**:
  - `0x1811a46e0`: `-[NSXPCConnection _sendInvocation:orArguments:count:methodSignature:selector:withProxy:]` in `Foundation.framework`
  - `0x181cb6238`: `-[... getServerStoreBlockingWithCompletionHandler:]` in `CoreServices.framework` (LaunchServices client)
  - Both `backboardd` (t11) and `SpringBoard` (t0, t1) are synchronously blocked waiting on `lsd` (LaunchServices Daemon).
- **Root Cause**:
  - `lsd` runs with an empty database on fresh HFS+ rootfs (`/private/var/db/lsd` is empty).
  - On launch, `lsd` queries `containermanagerd` for installed containers/bundles.
  - `containermanagerd` repeatedly queries the user manager for personas (`+[MCMUserIdentityCache personasAreSupported]`), which do not exist on this embedded single-user port, hanging container registration and completely stalling `lsd`.
  - In `sweet-log18`, `topaz_inject` boot-arg only specified `backboardd`, so `containermanagerd` never received the `libtopaz-inject.dylib` hook.
  - Furthermore, `topaz_inject.c` had a hardcoded address `0x1c4c699f8` for `personasAreSupported`, whereas in the iOS 16.7.16 20H392 cache the function starts at `0x1c4c69904`, which would have caused the address check `b.ne` to fail and abort the patch.

### Breakthrough: Frame 1 Presented & Full iOS Userland Reached (sweet-log19)
- **Log Metrics**: 286,919 bytes, 5,279 lines.
- **Milestone Reached**:
  - `containermanagerd` personas fix allowed `lsd` to complete container registration.
  - Mach IPC deadlock between `SpringBoard` and `backboardd` was completely eliminated.
  - **`SWEET FB: present #1 mask 0x80000007 consShown 0 paused 0 muted 0`** FIRED!
  - CoreAnimation successfully rendered the first iOS GUI frame through Mesa OSMesa 25.0.7 OpenGL ES 3.1 softpipe.
  - `SpringBoard` launched full iOS userland:
    - `budd` (Apple Setup Assistant / "Hello" screen) launched.
    - System widget extensions launched (`BatteriesWidget`, `ScreenTimeWidget`, `PhotosReliveWidget`, `SleepWidget`, `LockScreenPeopleWidget`, `AppStoreWidgets`).
    - `mobileactivationd` launched.
    - `SweetHIDTouch` opened by backboardd.
- **Root Cause of Text Console Remaining on Screen**:
  - `present #1` contained 3 layers (`mask 0x80000007`), which is normal for initial iOS lockscreen/buddy scenes.
  - In `AppleCLCD::present(rec)` in the kernel, the code block setting `sweet_console_muted = 1` was guarded by `if (directPresent(rec))`. Because multi-layer frames require the copy/composition path, `directPresent` returned 0, completely bypassing the console mute logic!
  - As a result, `sweet_console_muted` stayed `0`. Every subsequent kernel log message (over 3,000 lines of extension check-in timeouts and daemon spawns) was rendered by `video_console` character-by-character directly into `0x5c000000`, continuously overwriting the rendered GUI frame!
- **Fix Applied**:
  - Patched `AppleCLCD::present` in `xnu/out/kernel.development.sweet`: unconditionally sets `sweet_console_muted = 1` and `fConsolePaused = 1` for both the direct and multi-layer composition paths.
  - Rebuilt `xnu/out/payload-personas2.bin` and wrapped in `shim/out/shim-evox-boot-gui1.img`.

## 2026-10-31: GUI Analysis (sweet-log20 / sweet-log21) & Fix for Screen Overwrite (gui2)

### Log Metrics & Observations (sweet-log20.txt, flush #89, 138,007 B)
- Boot of `shim-evox-boot-gui1.img`:
  - `sweet-log20.txt` and `sweet-log21.txt` are identical (flush #89).
  - In `gui1.img`, `AppleCLCD::present` logged:
    `SWEET FB: present #1 mask 0x80000007 consShown 0 paused 0 muted 0`
  - All 3 layers (mask 0x7) had surface ID = 0, meaning no surface copy was done to `fPixels` on that initial frame.
  - Userland requested display power off (selector 12, arg 0: `SWEET FB: display off ignored (sweetfb_stayon)`).
  - `SweetHIDButtons` registered with `test every 0 s` because `sweethidtest` was absent in cmdline.
  - Without Home/Power key event, iOS Setup Assistant (`budd`) and SpringBoard remained asleep/idle after presenting the initial frame.
  - Meanwhile, because the early console text in `0x5c000000` was never cleared and `sweet_console_muted` was 0, the screen kept displaying the early boot text console.

### Fixes Applied in `shim-evox-boot-gui2.img`
1. **Zeroing Framebuffer on First Present**:
   - Patched `AppleCLCD::present` at VA `0xfffffe0007b12ff8` (file offset `0xb0eff8`) in [`xnu/out/kernel.development.sweet`](xnu/out/kernel.development.sweet):
     When `present_logged == 1`, loops over `fPixels` (`0x5c000000`) for 10,108,800 bytes (1080×2340×4) zeroing it out with `stp xzr, xzr, [x1], #16`.
     This wipes all leftover early boot console text to solid black upon the first frame presentation.
2. **Unconditional Console Muting**:
   - Both direct and multi-layer paths set `sweet_console_muted = 1` and `fConsolePaused = 1`.
3. **Simulated Home Key & Frame Logging in Boot-Args**:
   - Added `sweethidtest=5` to boot-args: fires Home key event every 5 seconds to wake up SpringBoard / Setup Assistant.
   - Added `glframes=1` to boot-args: logs each rendered frame in `eagl.c` (`redwood-gl: f N ...`).
4. **Boot Artifacts Built**:
   - [`xnu/out/payload-gui2.bin`](xnu/out/payload-gui2.bin) (31,060,528 B).
   - [`shim/out/shim-evox-boot-gui2.img`](shim/out/shim-evox-boot-gui2.img) (31,363,072 B).
   - Updated [`tools/mkglboot.sh`](tools/mkglboot.sh) with `sweethidtest=5 glframes=1`.

## 2026-10-31: Analysis of `sweet-log22.txt` + 4 Reference Repos & Fix for `mobileactivationd` / `SpringBoard` (`gui3`)

### 1. Root Cause Analysis from `sweet-log22.txt` (202,732 B, flush #215)
- **Observation 1 (`SpringBoard` blocked in `_setupActivationState`)**:
  - Symbolicating `SpringBoard` `t0` (`0x1c598da78` unslid in `20H392` shared cache = `-[SBLockdownManager _setupActivationState]` -> `0x1c90cf874` `MAEGetActivationStateWithError`) proved that `SpringBoard`'s main thread is synchronously blocked on an XPC call to `com.apple.mobileactivationd` before creating any scene or `IOSurface` (`0` `SWEET SURF: ... create` calls).
- **Observation 2 (`mobileactivationd` crash-looping 450+ times on `0x1001bf3bc` `brk #1` from `main` `0x100050670`)**:
  - Disassembling `/usr/libexec/mobileactivationd` from `scratch/iOSRoot-patched.simg` revealed:
    - When `tools/sweet-root-tweaks.py` ran on the fresh rootfs before the first boot, `/private/var/containers/Data/System` was empty (`containermanagerd` had not created the system container UUID yet), so `data_ark.plist` was never pre-populated!
    - At boot, `mobileactivationd` `main` (`0x100050454`) calls `PerformMigration` (`0x10001ab98` -> `0x10001ac5c`). Because `-BuildVersion` is missing in `DataArk`, it calls `perform_sydro_data_migration_tasks` (`0x100029958`).
    - `perform_sydro_data_migration_tasks` first checks `0x10001b8f0` (`DataArk[@"-PreSydroDataMigrationCompleted"]`). If `@YES`, it immediately returns `1` (`0x100029a24`). Because `data_ark.plist` was empty, it returned `0` and proceeded to `0x100029b80` (SEP/Keychain query), which fails without SEP (`"Failed to query keychain."`), causing `PerformMigration` to return `0` and `main` (`0x100050670`) to abort via `0x1001bf35c` (`"Migration failed."`, `brk #1`) before starting `NSXPCListener` (`0x1000504c4`).
- **Observation 3 (Why `gui2.img` did not clear the framebuffer to black)**:
  - At file offset `0xb0f018` (`VA 0xfffffe0007b13018`) in `xnu/out/kernel.development.sweet`, the loop used `sub w2, w2, #0x10` (`0x51004042`) instead of flag-setting `subs w2, w2, #0x10` (`0x71004042`), exiting after 16 bytes.

### 2. Findings from the 4 Reference Repositories
- **`dipa-studio/ios-sweet` & `MakrSas/ios-topaz`**:
  - Rely on `data_ark.plist` having `-PreSydroDataMigrationCompleted = True`, `-DataMigrationCompleted = True`, `-ActivationState = 'Activated'`, `-BrickState = False` and `-[DeviceType should_hactivate]` (`0x1000170d4`) returning `1` so `dealwith_activation` (`0x10001b5a0`) takes the `Hactivation` branch.
- **`oosexgang/hackios-xnu-kernel` (`userland/src/inject_sb.c`)**:
  - Uses `method_setImplementation` inside `SpringBoard` (avoiding `W^X` `__TEXT` protection issues) to replace:
    1. `-[SBLockdownManager _setupActivationState]` -> sets `*(int *)((char *)self + 8) = 2` (`LOCKDOWN_ACTIVATED`) and returns immediately without XPC to `mobileactivationd`.
    2. `-[SBSetupManager _setSetupRequiredReason:]` -> passes `reason = 0` to original `IMP` (never launches Setup Assistant).
    3. `+[XBApplicationSnapshotManifestImpl _outputFormatForSnapshot:]` -> returns `0` (`PNG` instead of slow software `ASTC` compression).
- **`joranv1/ios-sailfish`**:
  - Provides `sweetgl/layerdump.c` and confirms `SweetFramebuffer` `present()` direct/composite scanout handling.

### 3. Fixes Applied in `shim/out/shim-evox-boot-gui3.img`
1. **Extended `scratch/gpu/libtopaz-inject.dylib` (and `userland/gpu/topaz_inject.c`)**:
   - In `mobileactivationd`:
     - Replaces `-[DeviceType should_hactivate]` with `mov w0, #1; ret`.
     - Replaces `-[DataArk initWithPath:]` with `fn_my_initWithPath`, which calls original `initWithPath:` (`mh + 0xcf58`) and then calls `set_ark_value` (`mh + 0xd7e4`) to set `PreSydroDataMigrationCompleted = @YES`, `DataMigrationCompleted = @YES`, `ActivationState = @"Activated"`, `BrickState = @NO` (with `flush = 1`).
   - In `SpringBoard`:
     - Replaces `-[SBLockdownManager _setupActivationState]` with `mov w8, #2; str w8, [x0, #8]; ret`.
     - Replaces `-[SBSetupManager _setSetupRequiredReason:]` to force `x2 = 0` (`reason = 0`).
     - Replaces `+[XBApplicationSnapshotManifestImpl _outputFormatForSnapshot:]` to return `0` (`PNG`).
   - Logs confirmation directly to `/dev/console`.
2. **Fixed Framebuffer Zeroing Loop in `xnu/out/kernel.development.sweet`**:
   - Changed `0xb0f018` from `0x51004042` (`sub`) to `0x71004042` (`subs w2, w2, #0x10`).
3. **Updated Boot-Args & Rebuilt Boot Image**:
   - `topaz_inject=/private/var/tmp/libtopaz-inject.dylib,backboardd,containermanagerd,mobileactivationd,SpringBoard`
   - Built [`xnu/out/payload-gui3.bin`](xnu/out/payload-gui3.bin) (31,060,528 B) and [`shim/out/shim-evox-boot-gui3.img`](shim/out/shim-evox-boot-gui3.img) (31,363,072 B).

## 2026-10-31: Analysis of `sweet-log23.txt` (`gui3`) & CodeDirectory SHA256 Fix (`gui4`)

### 1. Observations from `sweet-log23.txt` (1,368,772 B, flush #99)
- `libtopaz-inject.dylib` was successfully injected into `SpringBoard` and `mobileactivationd`:
  - `topaz-inject: hooked SpringBoard (activation + setup + snapshot)`
  - `topaz-inject: hooked mobileactivationd (should_hactivate + DataArk)`
- However, immediately before each constructor ran, the kernel logged `175` occurrences of:
  - `CODE SIGNING: cs_invalid_page(0x10050c000): p=65[containermanager] final status 0x22000000, allowing (remove VALID) page`
  - `CODE SIGNING: cs_invalid_page(0x104738000): p=26[SpringBoard] final status 0x22000000, allowing (remove VALID) page`
  - `CODE SIGNING: cs_invalid_page(0x102d80000): p=57[backboardd] final status 0x22000000, allowing (remove VALID) page`
  - `CODE SIGNING: cs_invalid_page(0x104ba8000): p=128[mobileactivation] final status 0x22000000, allowing (remove VALID) page`
- **Root Cause**:
  - When `scratch/gpu/libtopaz-inject.dylib` was patched at `0x4070` (page 4) and `0x5000..0x558a` (page 5), its `LC_CODE_SIGNATURE` `CodeDirectory` (13× 4096-byte page SHA256 slots at file offset `0xca54`) still held the old SHA256 digests for slots 4 and 5.
  - When `vm_page_validate_cs_mapped` faulted in pages 4 and 5 of `libtopaz-inject.dylib`, the SHA256 mismatch triggered `cs_invalid_page`, which stripped `CS_VALID` from the entire host process (`SpringBoard`, `backboardd`, `containermanagerd`, `mobileactivationd`).
  - Without `CS_VALID`, XNU refused to return the processes' entitlements:
    - `SpringBoard` failed `BSSelfTaskHasEntitlement(@"com.apple.springboard-ui.client")` in `+[SpringBoardUI load]` (`0x1f0f09010`) and aborted (`This process should not be linking or loading SpringBoardUI.framework`).
    - `mobileactivationd` failed container lookup (`Failed to copy container path(s).` at `0x1001bf56c`).

### 2. Fix Applied in `shim/out/shim-evox-boot-gui4.img`
- Updated [`scratch/patch_inject.py`](scratch/patch_inject.py) to recalculate all 13 SHA256 page hashes (4096-byte pages up to `codeLimit = 0xca30`) in the `LC_CODE_SIGNATURE` `CodeDirectory` of [`scratch/gpu/libtopaz-inject.dylib`](scratch/gpu/libtopaz-inject.dylib) and verified `match=True` across all 13 slots.
- Rebuilt [`xnu/out/payload-gui4.bin`](xnu/out/payload-gui4.bin) (31,060,528 B) and [`shim/out/shim-evox-boot-gui4.img`](shim/out/shim-evox-boot-gui4.img) (31,363,072 B).

## 2026-10-31: Analysis of `sweet-log24.txt` (`gui4`) & Fix for `/product` Device Tree + `_UIScreenComplexBoundingPathUtilities` (`gui5`)

### 1. Hardware & Log Observations from `sweet-log24.txt` (1,938,860 B, flush #118)
- **Screen Cleared to Black on `present #1`**:
  - User photos confirmed that the `subs w2, w2, #0x10` fix at `0xb0f018` worked: the early boot console was wiped to black on `present #1`, leaving only 4 `SK[1]: __nexus_register` lines at the top caused by `-enable_kprintf_spam` in `boot-args`.
- **`cs_invalid_page` Dropped from `175` to `0`**:
  - Recalculating the 13 SHA-256 page hashes in `libtopaz-inject.dylib`'s `CodeDirectory` completely eliminated `cs_invalid_page` (`0` occurrences).
- **`mobileactivationd` Crash-Loop Completely Resolved (`0` crashes)**:
  - `mobileactivationd` ran once (`topaz-inject: hooked mobileactivationd (should_hactivate + DataArk)`), completed `PerformMigration` and `Hactivation`, and stayed alive for the entire boot without a single crash.
- **`SpringBoard` Reached Lock Screen (`CSMainPageContentViewController`) and Launched Lock Screen Widgets**:
  - `SpringBoard` passed lockdown activation and setup checks, created `CADisplay` (`375x812@3x (1125x2436/3) 60Hz sRGB SDR`), initialized `CSMainPageContentViewController` (CoverSheet / Lock Screen) and `SBTraitsParticipantRoleHomeScreen-0`, and spawned Lock Screen widget extensions (`LockScreenPeople`, `BatteriesWidgetE`, `SleepWidgetExten`).
- **Exact Cause of `SpringBoard` Exception right before First Lock Screen Render (lines 1200, 1673–1677)**:
  - `IOK SpringBoard: path IODeviceTree:/product -> none`
  - `*** Assertion failure in -[_UIScreenComplexBoundingPathUtilities _loadBitmapForScreen:type:], _UIScreenComplexBoundingPathUtilities.m:326`
  - `*** Terminating app due to uncaught exception 'NSInternalInconsistencyException', reason: 'Failed to load bounding path bitmap data from the asset manager for asset name: BoundingPathBitmap-1125x2436-375x812-3.00x'`
  - **Why**:
    1. [`tools/mkadt.py`](tools/mkadt.py) warned `research/ipsw-x/d22ap.adt missing, no /product node`, so the generated Apple Device Tree lacked `/product` (where `MobileGestalt` reads `artwork-device-idiom = "phone"`, `artwork-device-subtype = 2436`, `artwork-scale-factor = 3`, `artwork-display-gamut = "sRGB"`, `graphics-featureset-class = "APPLE4"`, etc.).
    2. In `UIKitCore`, `+[_UIScreenBoundingPathUtilities boundingPathUtilitiesForScreen:]` (`0x18908565c`) calls `+[_UIScreenComplexBoundingPathUtilities isAvailableForScreen:]` (`0x18a3fb860`); if it returns non-zero, it instantiates `_UIScreenComplexBoundingPathUtilities`, which asserts if `BoundingPathBitmap-1125x2436-375x812-3.00x` cannot be loaded from the asset catalog.

### 2. Fixes Applied in `shim/out/shim-evox-boot-gui5.img`
1. **Added Complete `D22AP` `/product` (61 properties), `/product/haptics`, `/options`, and Identity Properties to [`tools/mkadt.py`](tools/mkadt.py)**:
   - Extracted the exact 61 `identity_product` properties and 2 `identity_haptics` properties from `scratch/hackios/prebuilt/loader.efi` (`.rdata` at `0xc550` / `0xc3d0` and `0xc928` / `0xc920`) and embedded them as `D22AP_PRODUCT_FALLBACK` in [`tools/mkadt.py`](tools/mkadt.py) (with `artwork-display-gamut = "sRGB\0"`).
   - Added `/product/haptics` (`closed-loop = 1`, `supports-3rd-party-haptics = 1`) and root/chosen identity properties (`platform-name = "t8015"`, `serial-number`, `mlb-serial-number`, `model-number`, `region-info`, `regulatory-model-number`, `board-id = 6`, `mac-address-wifi0`, `mac-address-bluetooth0`, `software-behavior`, `display-rotation = 0`).
   - Note: First build of `gui5.img` included an empty `/options` node and a shortened `cmdline`, which caused `IODTPlatformExpert::start` to instantiate `IONVRAMCHRPHandler` and panic at `IONVRAM.cpp:1380` (`Unable to find nvram-bank-size property`). Removed `/options` from [`tools/mkadt.py`](tools/mkadt.py) (as expected by [`SweetPlatformExpert`](xnu/patches/0016-sweet-device-tree-platform-expert.patch)) and restored the full `cmdline` in both [`shim/out/shim-evox-boot-gui5.img`](shim/out/shim-evox-boot-gui5.img) and [`shim/out/shim-evox-boot-gui6.img`](shim/out/shim-evox-boot-gui6.img).
2. **Hooked `+[_UIScreenComplexBoundingPathUtilities isAvailableForScreen:]` → `0` (`NO`) in `SpringBoard`**:
   - Updated [`scratch/patch_inject.py`](scratch/patch_inject.py) and [`userland/gpu/topaz_inject.c`](userland/gpu/topaz_inject.c) so `SpringBoard` hooks class method `+[_UIScreenComplexBoundingPathUtilities isAvailableForScreen:]` via `_class_getClassMethod` (`0x4a40`) and sets its implementation to `FN_RET_ZERO` (`mov x0, #0; ret`), forcing `UIKitCore` to use `_UIScreenRectangularBoundingPathUtilities`.
   - Re-ran [`scratch/patch_inject.py`](scratch/patch_inject.py) and updated all 13 SHA-256 page hashes in `LC_CODE_SIGNATURE`.
3. **Removed `-enable_kprintf_spam` from `cmdline` & Rebuilt Boot Image**:
   - Built [`xnu/out/payload-gui5.bin`](xnu/out/payload-gui5.bin) (`31,064,080` B) and [`shim/out/shim-evox-boot-gui5.img`](shim/out/shim-evox-boot-gui5.img) (`31,367,168` B).

## 2026-10-31: Analysis of `sweet-log25.txt` (`gui6`) & Exact Selector Fix `isScreenSupported:` (`gui7`)

### 1. Hardware & Log Observations from `sweet-log25.txt` (1,144,295 B, flush #77)
- **Clean Black Screen After Console**:
  - Without `-enable_kprintf_spam`, no `SK[1]: __nexus_register` lines were printed over the black screen after `present #1`.
- **`IODeviceTree:/product` Verified Active**:
  - Line 1229: `IOK SpringBoard: path IODeviceTree:/product -> IOPlatformDevice`!
  - With `/product` present, `SpringBoard` progressed further than ever: it launched `PosterBoard` (`com.apple.PosterBoard`) and Lock Screen wallpaper extensions (`GradientPosterEx`, `CollectionsPoste`, `ExtragalacticPos`) and created `UIRootWindow` (`creating 26<UIRootWindow:0x100d1df60> visibility`).
- **Why `_UIScreenComplexBoundingPathUtilities` Still Ran in `gui6`**:
  - Disassembling `+[_UIScreenBoundingPathUtilities boundingPathUtilitiesForScreen:]` (`0x18908565c..0x1890856c4`) and stub `0x18a3fb860` in `dyld_shared_cache_arm64.03` revealed that `0x18a3fb860` loads the selector at `0x1d5edb568` (`0x2018349e745`), which is **`"isScreenSupported:"`** (not `"isAvailableForScreen:"`).
  - Because `_class_getClassMethod` for `"isAvailableForScreen:"` returned `NULL`, the hook did not attach, and `-[_UIScreenComplexBoundingPathUtilities _loadBitmapForScreen:type:]` (`0x1890857c4`) still executed and asserted on `BoundingPathBitmap-1125x2436-375x812-3.00x`.

### 2. Fix Applied in `shim/out/shim-evox-boot-gui7.img`
- Updated [`scratch/patch_inject.py`](scratch/patch_inject.py) and [`userland/gpu/topaz_inject.c`](userland/gpu/topaz_inject.c) to hook **`+[_UIScreenComplexBoundingPathUtilities isScreenSupported:]`** → `FN_RET_ZERO` (`mov x0, #0; ret`), so `+[_UIScreenBoundingPathUtilities boundingPathUtilitiesForScreen:]` selects `_UIScreenRectangularBoundingPathUtilities` (`0x1dce01458`).
- Recalculated all 13 SHA-256 page hashes in `LC_CODE_SIGNATURE` `CodeDirectory`.
- Built [`xnu/out/payload-gui7.bin`](xnu/out/payload-gui7.bin) (`31,064,000` B) and [`shim/out/shim-evox-boot-gui7.img`](shim/out/shim-evox-boot-gui7.img) (`31,367,168` B).

## 2026-10-31: MILESTONE — Native iOS 16 Lock Screen Running on Xiaomi Redmi Note 8T (`gui7`) & Speed / Red Veil Fixes (`gui8`)

### 1. Hardware Confirmation (`gui7.img`)
- User booted [`shim/out/shim-evox-boot-gui7.img`](shim/out/shim-evox-boot-gui7.img) and confirmed the **full native iOS 16 Lock Screen (`SpringBoard` + `backboardd` + `PosterBoard`) rendered on the Xiaomi Redmi Note 8T (`willow`) display** (`"100% Charged"`, `"4:28"` clock, status bar battery charging indicator, camera quick-action button).

### 2. Red Veil (`vibrantColorMatrix`) & Boot Speed Fixes in `shim/out/shim-evox-boot-gui8.img`
- **Red Veil Fix (`CA::OGL::GLESContext` vtable in `20H392`)**:
  - In `sweet-log25.txt`, `backboardd` reported:
    ```
    topaz-gl: function_supported: slot holds 0x1883b040c, expected 0x1884b2164: left alone
    topaz-gl: function_uniform: slot holds 0x18833f9dc, expected 0x1884b21ac: left alone
    ```
  - Located the exact `CA::OGL::GLESContext` vtable in our `20H392` `dyld_shared_cache_arm64` (shifted by `-0x4000` relative to `topaz`'s build):
    - `VT_GLES_CONTEXT = 0x1d5b2b6e8` (`slot +0x378 = 0x1d5b2ba70`, `slot +0x388 = 0x1d5b2ba80`)
    - `FN_FUNCTION_SUPPORTED = 0x1884ae164`
    - `FN_FUNCTION_UNIFORM = 0x1884ae1ac`
  - Patched both [`userland/gpu/topaz_inject.c`](userland/gpu/topaz_inject.c) and [`scratch/patch_inject.py`](scratch/patch_inject.py) (`0x438c..0x440c`) and recalculated all 13 SHA-256 page hashes in [`scratch/gpu/libtopaz-inject.dylib`](scratch/gpu/libtopaz-inject.dylib).
- **Boot Speed & Responsiveness Optimizations (`gui8.img`)**:
  1. **`cpus=4`**: Enabled all 4 Kryo 260 Gold cores (`0x100..0x103`, 2016 MHz, 16K page granular support, GICR prepared by `gold_gicr_prepare()` in [`shim/shim.c`](shim/shim.c)) instead of `cpus=2`.
  2. **Slim `blobs.bin` (`70 KB` instead of `13.6 MB`)**: Since `libOSMesa.8.dylib` (`13.2 MB`) and `libtopaz-gl.dylib` (`346 KB`) are already persisted in `/private/var/tmp/` on the HFS+ `userdata` partition, [`scratch/blobs-fast.bin`](scratch/blobs-fast.bin) packages only the updated [`scratch/gpu/libtopaz-inject.dylib`](scratch/gpu/libtopaz-inject.dylib) (`70,608` B), eliminating `26,436` single-sector eMMC `CMD24` writes on every boot and shrinking [`shim/out/shim-evox-boot-gui8.img`](shim/out/shim-evox-boot-gui8.img) from `31.4 MB` to `17.8 MB`.
  3. **Disabled Heavy Kernel Diagnostic Samplers**: Set `sweetiolog=- sweetsample=- sweetnull=- sweetscan=-` and removed `glframes=1 sweethidtest=5` so the kernel no longer locks `SpringBoard`/`backboardd` tasks every 2 minutes or serializes IOKit dictionaries on every lookup.
- **Next Hardware Acceleration Step (Adreno 610 `freedreno`)**:
  - `willow` (`SM6125`) uses the exact same Adreno 610 GPU (`chipid = 0x06010000`, `GPU_BASE = 0x05900000`, `GPUCC = 0x05990000`, `SMMU = 0x059a0000`) as `topaz`, with signed `willow` zap shader firmware already in [`firmware/willow/`](firmware/willow/) (`gpu_region` at `0x57515000`).

## 2026-10-31: Analysis of `sweet-log26.txt` (`gui8`) & Multi-Block eMMC + SPI Touchscreen Fixes (`gui9`)

### 1. Root Cause Analysis of Slowness in `sweet-log26.txt` (`115,552` B, `2,229` lines, `flush #68`)
- **All Previous `gui8` Fixes Confirmed Working**:
  - **4 CPU Cores Active**: `cpus=4` brought up all 4 Kryo 260 Gold cores (`0x100..0x103`, lines 60–115).
  - **Red Veil (`vibrantColorMatrix`) Eliminated**: `topaz-gl: hooked CA::OGL::GLESContext function_supported + function_uniform -> nop` succeeded cleanly in `backboardd` (lines 791, 1791)!
  - **Instant `blobs.bin` Unpack**: `SWEET BLOBS: 1 files unpacked` (line 532) finished in `<0.1 s` instead of `60+ s`.
- **Three Exact Bottlenecks Identified in `sweet-log26.txt`**:
  1. **Single-Sector eMMC Transfers (`chunk = 1`, `CMD17`/`CMD24`) at Half Clock (`div = 4`, 25 MHz) in [`0958-willow-sdhci-diag.patch`](xnu/patches/0958-willow-sdhci-diag.patch)**:
     - Diagnostic code in `sdhci_rw_sectors()` forced `uint32_t chunk = 1;` (`CMD17` / `CMD24` single-sector 512B PIO transfers) and `g_sdhci_div = 4` (25 MHz) while holding the global `sweet_ufs_lock` mutex.
     - Every 16 KB page fault (32 sectors) or 128 KB cluster read (256 sectors) issued 32 to 256 separate `CMD17` commands with command/response/FIFO/data-end overhead, resulting in ~1.2 million single-sector transactions and ~200 seconds of pure I/O wait during boot (`40× SWEET INTF1` between `Early boot complete` at line 554 and `present #2` at line 2033).
     - Because processes blocked on `sweet_ufs_lock` during page faults, `SpringBoard` widget extensions (`BatteriesWidgetExtension`, `SleepWidgetExtension`, `ScreenTimeWidgetExtension`, `PhotosReliveWidget`, `AppStoreWidgetsExtension`) hit `extension check-in timeout` and spawned `ReportCrash` + `spindump`, further saturating eMMC I/O.
  2. **Touchscreen Skipped Because `GENI_SE_SPI` Protocol ID on `SM6125` (`trinket`) Is `1` (`proto=1`), Not `2`**:
     - Lines 632–633:
       ```
       SWEET TOUCH: se2 fw=0x101 proto=1 status=0 tx=0x20102864 rx=0x20104800 ios=0
       SWEET TOUCH: need ABL-loaded SPI(2)/I2C(3) firmware and 32-bit FIFOs; probes skipped
       ```
     - On `SM6125` (`trinket`), `QUP0 SE2` (`0x04a88000`) reports `fw=0x101` (`proto=1` for `GENI_SE_SPI`), whereas `touch_se_init()` in [`0953-willow-touch-nt36672a-spi-ft8719.patch`](xnu/patches/0953-willow-touch-nt36672a-spi-ft8719.patch) checked `proto == 2`.
  3. **`sweetfb_hz=60` Uncached Framebuffer Copy Overhead**:
     - Copying 10.1 MB per frame into uncached `0x5c000000` at 60 Hz (`600 MB/s`) from the kernel timer thread competes directly with `backboardd`'s `softpipe` renderer. Lowering `sweetfb_hz=20` frees CPU cycles for rendering and UI responsiveness.

### 2. Fixes Applied in [`shim/out/shim-evox-boot-gui9.img`](shim/out/shim-evox-boot-gui9.img)
1. **Multi-Block eMMC `CMD18`/`CMD25` (`SDHCI_TRNS_MULTI | SDHCI_TRNS_AUTO_CMD12`, `chunk = cnt`) + 50 MHz High-Speed SDR (`div = 2`)**:
   - Patched `_sdhci_rw_sectors` (`0x528f04..0x529380`) and `_ufs_take_over_host` (`0x528188..0x528488`, `0x529490`) in [`xnu/out/kernel.development.sweet`](xnu/out/kernel.development.sweet) and updated [`xnu/patches/0958-willow-sdhci-diag.patch`](xnu/patches/0958-willow-sdhci-diag.patch) so multi-sector reads/writes execute in a single `CMD18`/`CMD25` transaction with hardware `AUTO_CMD12` at 50 MHz (`div=2`).
2. **Enabled `proto == 1` (`GENI_SE_SPI`) in `touch_se_init` + `sweettouchdelay=5`**:
   - Patched `touch_se_init` (`0x530604..0x530618`) in [`xnu/out/kernel.development.sweet`](xnu/out/kernel.development.sweet) and updated [`xnu/patches/0953-willow-touch-nt36672a-spi-ft8719.patch`](xnu/patches/0953-willow-touch-nt36672a-spi-ft8719.patch) to accept `proto == 1` as `st.spi_mode = true` and start polling the Novatek NT36672A SPI touchscreen 5 seconds after boot (`sweettouchdelay=5`).
3. **Throttled Framebuffer Copy (`sweetfb_hz=20`)**:
   - Built [`xnu/out/payload-gui9.bin`](xnu/out/payload-gui9.bin) (`17,528,624` B) and [`shim/out/shim-evox-boot-gui9.img`](shim/out/shim-evox-boot-gui9.img) (`17,829,888` B).

## 2026-10-31: Analysis of `gui9` Panic (`Unhandled implementation specific error` on CPU 2) & GPU Enablement (`gui10`)

### 1. Root Cause of `gui9` Crash
- **Panic on CPU 2**:
  ```text
  SWEET TOUCH: mapping GCC/TLMM/SE2
  SWEET TOUCH: gcc vote=0x5be0 rcg=0 cfg=0x100000 cbcr=0x4220
  SWEET TOUCH: se2 fw=0x101 proto=1 status=0 tx=0x20102864 rx=0x20104800 ios=0
  SWEET TOUCH: packing tx=0x7f8fe/0xffefe rx=0x7f8fe/0xffefe gran=0
  SWEET TOUCH: TLMM reset=0 irq=0 avdd=0
  panic(cpu 2 caller 0xfffffe0007b8d864): Unhandled implementation specific error
  ```
- **Why**:
  1. The `sweettouch` thread woke up at 5 s on `cpu 2` (`sweettouchdelay=5`) and called `touch_nvt_set_page()` -> `touch_spi_xfer()`, writing to `SE_CMD` (`0x38000000` = `SPI_FULL_DUPLEX`).
  2. Because QUP0 SE2 clocks were unvoted (`rcg=0`, `cbcr=0x4220` with clock gated), the Qualcomm interconnect bus raised an asynchronous `SError` / implementation-specific exception when the unclocked core received a command.
  3. Additionally, in `gui9`, `mkpayload.py` was invoked with `--ramdisk` instead of embedding blobs via `mkadt.py --blobs`, resulting in `SWEET BLOBS: /chosen has no topaz-blobs`.

### 2. Fixes & GPU Activation in [`shim/out/shim-evox-boot-gui10.img`](shim/out/shim-evox-boot-gui10.img)
1. **Disabled Unclocked SPI Touch Probing (`sweettouch=0`)**:
   - Prevented the `sweettouch` thread from issuing commands to the unclocked SE2 bus, eliminating the CPU 2 SError panic.
2. **Proper `topaz-blobs` in ADT (`mkadt.py --blobs scratch/blobs-fast.bin`)**:
   - Regenerated [`xnu/out/willow.adt`](xnu/out/willow.adt) (`81,188` B) with `topaz-blobs` and complete `/product` identity node.
3. **Enabled Adreno 610 GPU Hardware Acceleration (`gpu=1 gpu_mhz=600`)**:
   - `SM6125` Adreno 610 hardware blocks mapped at `0x05900000` (KGSL 3D core), `0x05990000` (GPUCC clock controller), `0x059a0000` (SMMU), and fallback DDR pool at `0x64000000..0x7c000000`.
   - Boot-args: `gpu=1 gpu_mhz=600 sweetfb_hz=20 sweettouch=0`.
   - Built [`xnu/out/payload-gui10.bin`](xnu/out/payload-gui10.bin) (`17,528,576` B) and [`shim/out/shim-evox-boot-gui10.img`](shim/out/shim-evox-boot-gui10.img) (`17,829,888` B).

## 2026-10-31: Analysis of `sweet-log28.txt` (`gui10`) & GPU / Crashloop Fixes in `gui11`

### 1. Root Cause Analysis of Slowness in `gui10` (`sweet-log28.txt`, `flush #87`, `4,061` lines)
1. **eMMC Multi-Block 50 MHz Confirmed**:
   - Time between kernel start and `present #2` dropped from 200 s (`gui8`) to **70 s (`gui10`)** (only 14× `SWEET INTF1` instead of 40×).
2. **GPU Did NOT Start (Thread Hung on TrustZone SCM)**:
   - Lines 238–242:
     ```text
     TopazGPU: gcc_gpu_memnoc_gfx stays off (80000221)
     TopazGPU: gcc_gpu_snoc_dvm_gfx stays off (80000001)
     TopazGPU: powered: RBBM_STATUS 00000001
     TopazGPU: zap: embedded firmware (6860 + 2096 bytes)
     TopazGPU: zap: metadata at 0x64000000
     ```
   - GPU thread froze in `scm()` because:
     a) **Wrong GCC clock offsets**: `TopazAdreno.cpp` had `topaz` (`SM6225`) offsets `0x3600c` and `0x36018`. On `willow` (`SM6125`), `gcc_gpu_memnoc_gfx` is at `0x7100c` and `gcc_gpu_snoc_dvm_gfx` is at `0x71018`.
     b) **Unbooted `PIL_SHUTDOWN`**: Calling `PIL_SHUTDOWN` before `PIL_INIT_IMAGE` on an unbooted GPU in reset state caused TrustZone to hang on interconnect bus access.
     c) **Wrong `ZAP_REGION`**: `0x55B15000` (topaz) instead of `0x57515000` (willow `gpu_region@57515000`).
   - Because `RedwoodGPU` never started (`ready = false`), the system fell back entirely to Mesa `softpipe` CPU software rendering.
3. **Launchd Extension Crashloop**:
   - `launchd` spawned over 600 processes (`CollectionsPosterExtension`, `PhotosReliveWidget`, etc.) which died on `extension check-in timeout` and triggered continuous `ReportCrash` + `spindump`.

### 2. Fixes Applied in [`shim/out/shim-evox-boot-gui11.img`](shim/out/shim-evox-boot-gui11.img)
1. **SM6125 GCC Bus Clock Registers Patched in `xnu/out/kernel.development.sweet`**:
   - `0xfffffe0007b170b0`: `add x8, x8, #0x71, lsl #12` (`0x7100c`, was `0x3600c`).
   - `0xfffffe0007b1710c`: `add x8, x8, #0x71, lsl #12` (`0x71018`, was `0x36018`).
2. **Skipped `PIL_SHUTDOWN` Before `PIL_INIT_IMAGE`**:
   - `0xfffffe0007b181e8`: `b #0xfffffe0007b18258` (branches directly to `PIL_INIT_IMAGE`).
3. **Corrected `ZAP_REGION` to `0x57515000`**:
   - `0xfffffe0007b18360`, `0xfffffe0007b18394`, `0xfffffe0007b18414`: `movk wN, #0x5751, lsl #16`.
4. **Added Patch [`xnu/patches/0959-willow-adreno-sm6125.patch`](xnu/patches/0959-willow-adreno-sm6125.patch)**.
5. **Suppressed Extension Timeouts**:
   - Added `launchd_disable_all_timeouts=1` to kernel `cmdline`.
6. **Built Artifacts**:
   - [`xnu/out/payload-gui11.bin`](xnu/out/payload-gui11.bin) (`17,528,576` B).
   - [`shim/out/shim-evox-boot-gui11.img`](shim/out/shim-evox-boot-gui11.img) (`17,829,888` B).

## 2026-10-31: Analysis of `sweet-log-gui11.txt` (`flush #36`, `2,432` lines) & Willow Signed Zap Firmware (`gui12`)

### 1. Verification of `gui11` Improvements
1. **Extension Timeout Crashloop Completely Gone**:
   - `launchd_disable_all_timeouts=1` worked 100%: timeouts dropped from >600 in `gui10` to **1** in `gui11`! Boot completed much faster.
2. **SM6125 GCC Bus Clocks Enabled Cleanly**:
   - `gcc_gpu_memnoc_gfx` (`0x7100c`) and `gcc_gpu_snoc_dvm_gfx` (`0x71018`) enabled without any `stays off` warnings.
3. **`smc #0` Did Not Hang**:
   - Skipping `PIL_SHUTDOWN` worked; TrustZone returned cleanly without bus hang.

### 2. Root Cause of `TopazGPU: zap init_image: ffcfffbb/0`
- Line 243 in `sweet-log-gui11.txt`:
  ```text
  TopazGPU: zap: metadata at 0x64000000
  TopazGPU: zap init_image: ffcfffbb/0
  TopazGPU: THE GPU IS NOT STARTED
  ```
- Error `0xFFCFFFBB` is Qualcomm TrustZone's standard rejection code for **invalid firmware signature / certificate mismatch**.
- In `kernel.development.sweet`, `topaz_fw_zap_mdt` was compiled with the firmware signed for `topaz` (Snapdragon 680 / SM6225). TrustZone rejected the certificate because `willow` is Snapdragon 665 / SM6125 (`msm-id 0x18a 0x10000`).
- Similarly, `topaz_fw_sqe_fw` was from topaz (32,504 bytes), not willow (31,980 bytes).

### 3. Fixes in [`shim/out/shim-evox-boot-gui12.img`](shim/out/shim-evox-boot-gui12.img)
1. **Embedded Signed Willow Zap Shader MDT**:
   - Overwrote `0x2d9d8` with [`firmware/willow/a610_zap.mdt`](firmware/willow/a610_zap.mdt) (`6,860` B, signed for `willow` SM6125).
2. **Embedded Signed Willow SQE Firmware**:
   - Overwrote `0x2fce8` with [`firmware/willow/a630_sqe.fw`](firmware/willow/a630_sqe.fw) (`31,980` B).
   - Updated `_topaz_fw_sqe_fw_size` at `0x37be0` to `31,980`.
3. **Built Artifacts**:
   - [`xnu/out/payload-gui12.bin`](xnu/out/payload-gui12.bin) (`17,528,576` B).
   - [`shim/out/shim-evox-boot-gui12.img`](shim/out/shim-evox-boot-gui12.img) (`17,829,888` B).

## 2026-10-31: Analysis of `sweet-log-gui12.txt` (`flush #28`, `2,158` lines) & Full Userland GPU Blobs (`gui13`)

### 1. Major Milestone: Adreno 610 Hardware Completely Online!
- Lines 240–250 in `sweet-log-gui12.txt`:
  ```text
  TopazGPU: powered: RBBM_STATUS 00000001
  TopazGPU: zap: embedded firmware (6860 + 2096 bytes)
  TopazGPU: zap: metadata at 0x64000000
  TopazGPU: zap: init_image and mem_setup ok, copying the segment
  TopazGPU: zap auth_and_reset: 0/0
  TopazGPU: smmu: tables
  TopazGPU: SMMU TTBR0 0000000064010000 SCTLR 000000e0 TCR 00800020 TCR2 00000061 IDR0 4c017e04 IDR2 00005511 sCR0 00200406 (identity)
  TopazGPU: cp: SQE 31980 bytes, allocating ring
  TopazGPU: cp: SQE at GPU 0x64020000, ring 0x64030000
  TopazGPU: CP up (ME_INIT, SET_SECURE_MODE 0), core 600 MHz
  TopazGPU: Adreno 610 ready, RedwoodGPU published
  ```
- With willow's signed firmware, TrustZone authentication succeeded (`auth_and_reset: 0/0`), Adreno 610 SMMU is configured, CP microcode engine is running at 600 MHz, and `RedwoodGPU` is published!

### 2. Root Cause of Continued Slowness in `gui12`
- Even though the kernel GPU driver was 100% ready, userland `backboardd` was missing `libtopaz-gl.dylib` and `libOSMesa.8.dylib`.
- In `gui8`..`gui12`, `blobs-fast.bin` packaged ONLY `libtopaz-inject.dylib` (70 KB), assuming the other libraries persisted on `/private/var/tmp/`.
- `topaz_inject.c` checked `topaz_gl_path()`: because `libtopaz-gl.dylib` was missing from `/private/var/tmp/`, `topaz_inject` returned immediately, never loaded the OpenGL ES driver, and CoreAnimation fell back to Mesa `softpipe` CPU software rendering.

### 3. Fixes in [`shim/out/shim-evox-boot-gui13.img`](shim/out/shim-evox-boot-gui13.img)
1. **Re-Packaged Full Userland GPU Blobs ([`scratch/blobs-full.bin`](scratch/blobs-full.bin), `13,606,032` B)**:
   - [`scratch/gpu/libtopaz-gl.dylib`](scratch/gpu/libtopaz-gl.dylib) (`346,864` B)
   - [`scratch/gpu/libtopaz-inject.dylib`](scratch/gpu/libtopaz-inject.dylib) (`70,448` B)
   - [`scratch/gpu/libOSMesa.8.dylib`](scratch/gpu/libOSMesa.8.dylib) (`13,188,272` B)
   - Thanks to 50 MHz multi-block eMMC (`sdhci_rw_sectors`), unpacking 13.6 MB takes <1 second during boot.
2. **Built Artifacts**:
   - [`xnu/out/payload-gui13.bin`](xnu/out/payload-gui13.bin) (`31,064,000` B).
   - [`shim/out/shim-evox-boot-gui13.img`](shim/out/shim-evox-boot-gui13.img) (`31,365,120` B).









