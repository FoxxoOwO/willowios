#!/usr/bin/env python3
import os
import subprocess
import sys

def main():
    repo = r"D:\repositories\willowios"
    py = sys.executable
    ndk_bin = r"C:\Users\Teresa\AppData\Local\Android\Sdk\ndk\28.2.13676358\toolchains\llvm\prebuilt\windows-x86_64\bin"
    clang = os.path.join(ndk_bin, "clang.exe")
    lld = os.path.join(ndk_bin, "ld.lld.exe")
    objcopy = os.path.join(ndk_bin, "llvm-objcopy.exe")
    readelf = os.path.join(ndk_bin, "llvm-readelf.exe")
    nm = os.path.join(ndk_bin, "llvm-nm.exe")

    # 1. Build ADT
    print("=== 1. Building willow.adt ===")
    adt_py = os.path.join(repo, "tools", "mkadt.py")
    adt_out = os.path.join(repo, "dtb", "willow", "willow.adt")
    subprocess.check_call([py, adt_py, adt_out])

    # 2. Build shim
    print("=== 2. Building shim ===")
    shim_dir = os.path.join(repo, "shim")
    shim_out = os.path.join(shim_dir, "out")
    os.makedirs(shim_out, exist_ok=True)
    cflags = [
        "--target=aarch64-none-elf", "-O2", "-ffreestanding", "-nostdlib",
        "-fno-builtin", "-fno-stack-protector", "-fno-pic", "-fno-pie",
        "-fno-jump-tables", "-mllvm", "-simplifycfg-sink-common=false",
        "-mgeneral-regs-only", "-mstrict-align", "-march=armv8-a",
        "-Wall", "-Wextra", "-Wno-unused-command-line-argument",
        "-Wno-unknown-attributes", "-DBOARD_WILLOW"
    ]
    shim_srcs = ["start.S", "shim.c", "console.c", "mmu.c", "fdt.c", "loader.c", "ufs.c"]
    shim_objs = []
    shim_c_objs = []
    for s in shim_srcs:
        o = os.path.join(shim_out, os.path.splitext(s)[0] + ".o")
        subprocess.check_call([clang] + cflags + ["-c", os.path.join(shim_dir, s), "-o", o])
        shim_objs.append(o)
        if s != "start.S":
            shim_c_objs.append(o)

    relocs = subprocess.check_output([readelf, "-r"] + shim_c_objs).decode()
    assert "R_AARCH64_ABS64" not in relocs, "ABS64 in shim C objects"

    shim_elf = os.path.join(shim_out, "shim.elf")
    subprocess.check_call([lld, "-T", os.path.join(shim_dir, "shim.ld"), "--build-id=none", "-N"] + shim_objs + ["-o", shim_elf])
    shim_img = os.path.join(shim_out, "Image")
    subprocess.check_call([objcopy, "-O", "binary", shim_elf, shim_img])
    print(f"shim Image built: {os.path.getsize(shim_img)} bytes")

    # 3. Build enxerto
    print("=== 3. Building enxerto ===")
    enx_dir = os.path.join(repo, "enxerto")
    enx_out = os.path.join(enx_dir, "out")
    os.makedirs(enx_out, exist_ok=True)
    enx_srcs = [
        "start.S", "enxerto.c", "console.c", "bootui.c", "fbui.c", "mmu.c", "fdt.c",
        "loader.c", "ufs.c", "inflate.c", "usb_dwc3.c", "usb_power.c", "fastboot.c",
        "sparse.c", "storage.c", "blake2b.c", "bergamota.c", "pmic.c", "charge.c",
        "charge_mode.c", "charger.c"
    ]
    enx_objs = []
    enx_c_objs = []
    for s in enx_srcs:
        o = os.path.join(enx_out, os.path.splitext(s)[0] + ".o")
        subprocess.check_call([clang] + cflags + ["-c", os.path.join(enx_dir, s), "-o", o])
        enx_objs.append(o)
        if s != "start.S":
            enx_c_objs.append(o)

    relocs = subprocess.check_output([readelf, "-r"] + enx_c_objs).decode()
    assert "R_AARCH64_ABS64" not in relocs, "ABS64 in enxerto C objects"

    enx_elf = os.path.join(enx_out, "enxerto.elf")
    subprocess.check_call([lld, "-T", os.path.join(enx_dir, "enxerto.ld"), "--build-id=none", "-N"] + enx_objs + ["-o", enx_elf])
    enx_img = os.path.join(enx_out, "Image")
    subprocess.check_call([objcopy, "-O", "binary", enx_elf, enx_img])
    print(f"enxerto Image built: {os.path.getsize(enx_img)} bytes")

    # 4. Pack boot images with mkbootimg_willow.py
    print("=== 4. Packing boot images ===")
    mkboot = os.path.join(repo, "tools", "mkbootimg_willow.py")
    dtb = os.path.join(repo, "dtb", "willow", "stock_dtb_all.bin")

    # 4a. shim-boot.img (header_version = 2 for internal eMMC boot with dtbo)
    subprocess.check_call([
        py, mkboot,
        "-k", shim_img,
        "-d", dtb,
        "--header-version", "2",
        "-o", os.path.join(shim_out, "shim-boot.img"),
    ])

    # 4b. enxerto-boot.img
    subprocess.check_call([
        py, mkboot,
        "-k", enx_img,
        "-d", dtb,
        "--header-version", "2",
        "-o", os.path.join(enx_out, "enxerto-boot.img"),
    ])

    # 4c. bergamota-fastboot.img (with cmdline bergamota.fastboot=1)
    fastboot_cmdline = (
        "console=ttyMSM0,115200n8 earlycon=msm_geni_serial,0x4a90000 "
        "androidboot.hardware=qcom androidboot.console=ttyMSM0 "
        "androidboot.memcg=1 lpm_levels.sleep_disabled=1 "
        "video=vfb:640x400,bpp=32,memsize=3072000 "
        "msm_rtb.filter=0x237 service_locator.enable=1 "
        "swiotlb=1 loop.max_part=7 bergamota.fastboot=1"
    )
    subprocess.check_call([
        py, mkboot,
        "-k", enx_img,
        "-d", dtb,
        "--header-version", "2",
        "-c", fastboot_cmdline,
        "-o", os.path.join(enx_out, "bergamota-fastboot.img"),
    ])

    print("ALL BUILDS AND PACKING COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
