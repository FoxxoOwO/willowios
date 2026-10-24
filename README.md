# willowios — iOS 16 (Apple XNU) Port for Xiaomi Redmi Note 8T (`willow`)

Port of Apple's **XNU kernel (`xnu-8796.141.3`, iOS 16)**, **Enxerto bootloader / Bergamota fastboot**, bare-metal **boot shim**, and **iOS 16 userland** to the **Xiaomi Redmi Note 8T (`willow`, Qualcomm Snapdragon 665 / SM6125 `trinket`)**.

Built upon:
- [`ry-diffusion/bergamota`](https://github.com/ry-diffusion/bergamota) — Enxerto bootloader, USB fastboot environment, off-mode charging, Renegade root builder
- [`MakrSas/ios-topaz`](https://github.com/MakrSas/ios-topaz/tree/topaz) — Kryo 260 Silver→Gold PSCI handoff, ARMv8.0 compatibility, Adreno 610 (`TopazAdreno`) & QDSP6 (`TopazAudio`) drivers
- [`dipa-studio/ios-sweet`](https://github.com/dipa-studio/ios-sweet) — Base Qualcomm Snapdragon XNU (`ARM64_BOARD_CONFIG_SWEET`) platform bring-up
- [`xiaomi-ginkgo`](https://github.com/xiaomi-ginkgo) & official `willow_global_images_V12.5.6.0.RCXMIXM` firmware — Hardware device trees, register maps, and firmware blobs

---

## Hardware Summary (`willow` / SM6125 `trinket`)

| Component | Hardware / Register Map on `willow` | Driver / Implementation |
|---|---|---|
| **SoC** | Qualcomm Snapdragon 665 (`SM6125` / `trinket`), `msm-id = <0x18a 0x10000>`, `board-id = <0x22 0x200>` | `dtb/willow/dtb` (`rom-8.dtb`), `dtb/willow/dtbo-willow.dtb` (`dtbo-11.dtb`) |
| **CPU** | 4× Kryo 260 Silver (Cortex-A53, MPIDR `0x0..0x3`, 4K granule only) + 4× Kryo 260 Gold (Cortex-A73, MPIDR `0x100..0x103`, 4K/16K/64K granules @ 2.016 GHz, OSM `0x0f523000`) | PSCI `CPU_ON` Silver→Gold `0x100` handoff in `shim` & `enxerto`; `SweetCPU` + `sweet_cpufreq` |
| **DRAM** | 4 GiB LPDDR4X at `0x40000000..0x140000000` (all Qualcomm carve-outs in `0x40000000..0x61a00000`; contiguous 3 GiB XNU kernel window at `0x80000000..0x140000000`) | `tools/mkadt.py`, `xnu/patches/0951-willow-board-ram-display-1080x2340.patch` |
| **Display** | 1080×2340 Tianma NT36672A / BOE FT8719 FHD+ video-mode DSI panel; ABL `cont_splash_region` at `0x5c000000` (`0x01900000`, stride `4320`, `BGRX8888`), DPU `mdp@5e01000` | `shim/console.h`, `enxerto/board.h`, `xnu/patches/0951-willow-board-ram-display-1080x2340.patch` |
| **Storage** | 64 GiB eMMC 5.1 on Qualcomm SDHCI MSM v5 `sdhci@4744000` (512-byte sectors, 56 GPT partitions, `userdata` at sector `12582912`, 49.4 GiB) | `shim/ufs.c`, `enxerto/ufs.c`, `enxerto/storage.c`, `xnu/patches/0952-willow-sdhci-emmc-root-storage.patch` |
| **Touchscreen** | Novatek NT36672A SPI (`spi@4a88000` QUP0 SE2 GENI SPI, CS GPIO 9, reset GPIO 87, IRQ GPIO 88 in TLMM WEST `0x00500000`) + FocalTech FT8719 I2C fallback (`i2c@4a88000` @ `0x38`) | `xnu/patches/0953-willow-touch-nt36672a-spi-ft8719.patch`, `firmware/willow/novatek_ts_tianma_fw.bin` |
| **PMIC / Battery / Keys** | SPMI arbiter v5 at `0x01c40000` (`OBS = 0x03e00000`, `CNFG = 0x01c0a000`, `CHNL = 0x02000000`); PM6125 (USID 0) PON `0x0800` + Vol+ GPIO5 `0xc400`; PMI632 (USID 2) QGauge `0x4800` + SMB5 charger `0x1000..0x1600` | `enxerto/pmic.c`, `enxerto/charger.c`, `xnu/patches/0954-willow-pmi632-battery-charger.patch` |
| **USB** | Synopsys DWC3 `dwc3@4e00000` (`QSCRATCH = 0x04ef8800`), QUSB2 v1 PHY `qusb@1613000`, GCC `0x01400000`, `apps_smmu` `0x0c600000` (stream ID `0x100`) | `enxerto/usb_dwc3.c`, `enxerto/usb_power.c`, `xnu/patches/0955-willow-usb-dwc3-qusb2-smmu.patch` |
| **GPU** | Qualcomm Adreno 610 (`5900000.qcom,kgsl-3d0`, GMUless A6xx, `gpu_smmu` `0x059a0000`), GPU pool at `0x64000000..0x7c000000` | `TopazAdreno.cpp`, `firmware/willow/a610_zap.*`, `firmware/willow/a630_sqe.fw` |

---

## Pre-Built Boot Images Ready to Boot

The following binaries are already compiled and verified in this workspace:

| File | Size | Description |
|---|---|---|
| [`dtb/willow/willow.adt`](dtb/willow/willow.adt) | 7,080 B | Apple Device Tree (`.adt`) for `willow` (4× Kryo 260 Gold `0x100..0x103`, GICv3 `0x0f200000`/`0x0f300000`, `1080×2340` @ `0x5c000000`, SDHCI `0x04744000`, DRAM `0x80000000 + 3 GiB`) |
| [`shim/out/shim-boot.img`](shim/out/shim-boot.img) | 348,160 B | Android Boot Image v2 with the bare-metal `shim` loader + hardware diagnostics (Silver→Gold handoff, SDHCI eMMC GPT probe, 16K MMU, GICv3/vtimer IRQ test) |
| [`enxerto/out/enxerto-boot.img`](enxerto/out/enxerto-boot.img) | 454,656 B | Android Boot Image v2 with the **Enxerto** graphical bootloader (Silver→Gold handoff, off-mode charging UI, DEFLATE XNU payload loader, fallback FDT/eMMC/GIC diagnostics) |
| [`enxerto/out/bergamota-fastboot.img`](enxerto/out/bergamota-fastboot.img) | 454,656 B | Android Boot Image v2 that boots directly into **Bergamota Fastboot** over USB (`fastboot flash userdata`, `fastboot oem hash`, `fastboot boot`) using the safe `0x62000000..0x80000000` low-DDR window |

---

## Quick Start

### 1. Boot Hardware Diagnostics or Bergamota Fastboot (Non-Destructive RAM Boot)

With your Redmi Note 8T (`willow`) connected via USB:

```powershell
# Reboot from Android into bootloader (Fastboot):
adb reboot bootloader

# Boot the Enxerto bootloader / hardware diagnostics in RAM (does not touch eMMC):
fastboot boot enxerto/out/enxerto-boot.img

# Or boot the classic bare-metal shim diagnostics in RAM:
fastboot boot shim/out/shim-boot.img

# Or boot into Bergamota Fastboot environment:
fastboot boot enxerto/out/bergamota-fastboot.img
```

### 2. Build the Apple XNU Kernel & Full iOS `boot-willow.img`

Because Apple's XNU kernel requires the macOS Xcode SDK (`xcrun -sdk macosx`), you can build it either:
- **Automatically via GitHub Actions**: Push this repository to GitHub and run the [`.github/workflows/xnu.yml`](.github/workflows/xnu.yml) workflow (`Build XNU (willow)`). It applies all 206 patches (`xnu/patches/0001..0955`), compiles `kernel.development`, packs `payload.bin` with `dtb/willow/willow.adt`, and uploads:
  - `boot-willow.img` (Shim + XNU kernel payload)
  - `boot-willow-enxerto.img` (Enxerto + compressed XNU kernel payload)
  - `boot-willow-fastboot.img` (Bergamota Fastboot)
- **Locally on macOS**:
  ```bash
  ./xnu/build.sh
  python3 tools/mkadt.py -o dtb/willow/willow.adt
  python3 tools/mkpayload.py \
      --kernel xnu/build/obj/KERNEL_DEV/arm64/willow/kernel.development \
      --adt dtb/willow/willow.adt \
      --phys-base 0x80000000 \
      --mem-size 0xc0000000 \
      --cmdline "debug=0x8 serial=2 rd=disk0 -v" \
      -o out/payload.bin
  ./shim/build.sh out/payload.bin
  ./enxerto/build.sh out/payload.bin
  ```

### 3. Build & Flash the iOS 16 Root Filesystem (`userdata`)

On macOS (or Linux for Renegade), build the HFS+ root filesystem image from the iOS 16.7.10 (`20H350`, iPhone 8 `iPhone10,1`) IPSW and flash it to `userdata`:

```bash
# Build 4 GiB HFS+ rootfs image with Darwin/iOS userland + Adreno/Touch/Audio daemons:
sudo ./userland/mkiosroot.sh /path/to/iPhone10,1_16.7.10_20H350_Restore.ipsw userland/out/iosroot.dmg

# Convert to Android sparse image and flash to userdata (or via Bergamota Fastboot):
python3 tools/img2simg.py userland/out/iosroot.dmg userland/out/iosroot.simg
fastboot flash userdata userland/out/iosroot.simg

# Boot XNU + iOS userland in RAM:
fastboot boot enxerto/out/enxerto-boot.img
```
