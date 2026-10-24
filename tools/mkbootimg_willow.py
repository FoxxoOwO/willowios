#!/usr/bin/env python3
"""
Build an Android Boot Image v2 (header_version = 2, page_size = 4096) for
Xiaomi Redmi Note 8T (willow, Qualcomm Snapdragon 665 / SM6125 "trinket").

Parameters verified from official willow fastboot firmware
(willow_global_images_V12.5.6.0.RCXMIXM_20220623.0000.00_11.0):
  - magic:          "ANDROID!"
  - header_version: 2 (1660-byte header)
  - page_size:      4096
  - kernel_addr:    0x00008000 (base 0x00000000 + offset 0x00008000)
  - ramdisk_addr:   0x01000000 (or 0x00000000 when no ramdisk)
  - second_addr:    0x00000000
  - tags_addr:      0x00000100
  - dtb_addr:       0x01f00000
  - os_version:     0x16000143 (Android 11.0.0, patch 2022-06)
  - dtb:            dtb/willow/dtb (rom-8.dtb: "Qualcomm Technologies, Inc. TRINKET SoC",
                    msm-id = <0x18a 0x10000>)
"""
import argparse
import gzip
import hashlib
import os
import struct
import sys

PAGE_SIZE = 4096
DEFAULT_CMDLINE = (
    "console=ttyMSM0,115200n8 earlycon=msm_geni_serial,0x4a90000 "
    "androidboot.hardware=qcom androidboot.console=ttyMSM0 "
    "androidboot.memcg=1 lpm_levels.sleep_disabled=1 "
    "video=vfb:640x400,bpp=32,memsize=3072000 "
    "msm_rtb.filter=0x237 service_locator.enable=1 "
    "swiotlb=1 loop.max_part=7"
)


def align_up(n: int, page: int = PAGE_SIZE) -> int:
    return (n + page - 1) & ~(page - 1)


def pad_to_page(data: bytes, page: int = PAGE_SIZE) -> bytes:
    rem = len(data) % page
    return data if rem == 0 else data + b"\x00" * (page - rem)


def build_bootv2(
    kernel_bytes: bytes,
    dtb_bytes: bytes,
    ramdisk_bytes: bytes = b"",
    cmdline: str = DEFAULT_CMDLINE,
    gzip_kernel: bool = True,
    append_dtb: bool = False,
) -> bytes:
    if gzip_kernel and kernel_bytes[:2] != b"\x1f\x8b":
        kernel_bytes = gzip.compress(kernel_bytes, compresslevel=9, mtime=0)

    # In stock firmware boot.img, the kernel is pure gzip with NO appended DTB.
    # The concatenated DTBs (11 DTBs matching all trinket board variants) reside
    # in the v2 header DTB slot at offset (page_size + align_up(k_size)).
    # ABL's decompress() expects a clean gzip stream and validates its size.
    if append_dtb:
        kernel_bytes = kernel_bytes + dtb_bytes

    k_size = len(kernel_bytes)
    r_size = len(ramdisk_bytes)
    s_size = 0
    rec_size = 0
    dtb_size = len(dtb_bytes)

    k_addr = 0x00008000
    r_addr = 0x01000000 if r_size else 0x00000000
    s_addr = 0x00000000
    tags_addr = 0x00000100
    dtb_addr = 0x01F00000
    os_version = 0x16000165  # 11.0.0 / 2022-06 (matching stock boot.img)
    header_version = 2
    header_size = 1660

    cmd_bytes = cmdline.encode("ascii")[:1535]
    cmd_part1 = cmd_bytes[:512].ljust(512, b"\x00")
    cmd_part2 = cmd_bytes[512:1536].ljust(1024, b"\x00")
    board_name = b"\x00" * 16

    sha = hashlib.sha1()
    sha.update(kernel_bytes)
    sha.update(struct.pack("<I", k_size))
    sha.update(ramdisk_bytes)
    sha.update(struct.pack("<I", r_size))
    sha.update(b"")
    sha.update(struct.pack("<I", s_size))
    sha.update(b"")
    sha.update(struct.pack("<I", rec_size))
    sha.update(dtb_bytes)
    sha.update(struct.pack("<I", dtb_size))
    img_id = sha.digest().ljust(32, b"\x00")

    hdr = struct.pack(
        "<8s10I16s512s32s1024sIQIIQ",
        b"ANDROID!",
        k_size,
        k_addr,
        r_size,
        r_addr,
        s_size,
        s_addr,
        tags_addr,
        PAGE_SIZE,
        header_version,
        os_version,
        board_name,
        cmd_part1,
        img_id,
        cmd_part2,
        rec_size,
        0,
        header_size,
        dtb_size,
        dtb_addr,
    )
    assert len(hdr) == header_size

    out = bytearray()
    out += pad_to_page(hdr)
    out += pad_to_page(kernel_bytes)
    if r_size:
        out += pad_to_page(ramdisk_bytes)
    if dtb_size:
        out += pad_to_page(dtb_bytes)
    return bytes(out)


def build_bootv0(
    kernel_bytes: bytes,
    dtb_bytes: bytes,
    ramdisk_bytes: bytes = b"",
    cmdline: str = DEFAULT_CMDLINE,
    gzip_kernel: bool = True,
) -> bytes:
    if gzip_kernel and kernel_bytes[:2] != b"\x1f\x8b":
        kernel_bytes = gzip.compress(kernel_bytes, compresslevel=9, mtime=0)

    # In header_version = 0, Qualcomm legacy ABL decompress() sets DtbOffset
    # to len(gzip). The 0x130f4 check branches around the v2 DtbOffset overwrite,
    # preserving DtbOffset = len(gzip). ABL then verifies the DTB table header at
    # (ImageBuffer + page_size + DtbOffset) = (kernel_start + len(gzip)).
    kernel_bytes = kernel_bytes + dtb_bytes

    k_size = len(kernel_bytes)
    r_size = len(ramdisk_bytes)
    s_size = 0
    k_addr = 0x00008000
    r_addr = 0x01000000 if r_size else 0x00000000
    s_addr = 0x00000000
    tags_addr = 0x00000100
    header_version = 0
    os_version = 0x16000165

    cmd_bytes = cmdline.encode("ascii")[:511]
    cmd_part1 = cmd_bytes.ljust(512, b"\x00")
    board_name = b"\x00" * 16

    sha = hashlib.sha1()
    sha.update(kernel_bytes)
    sha.update(struct.pack("<I", k_size))
    sha.update(ramdisk_bytes)
    sha.update(struct.pack("<I", r_size))
    sha.update(b"")
    sha.update(struct.pack("<I", s_size))
    img_id = sha.digest().ljust(32, b"\x00")
    extra_cmdline = b"\x00" * 1024

    hdr = struct.pack(
        "<8s10I16s512s32s1024s",
        b"ANDROID!",
        k_size,
        k_addr,
        r_size,
        r_addr,
        s_size,
        s_addr,
        tags_addr,
        PAGE_SIZE,
        header_version,
        os_version,
        board_name,
        cmd_part1,
        img_id,
        extra_cmdline,
    )
    assert len(hdr) == 1632

    out = bytearray()
    out += pad_to_page(hdr)
    out += pad_to_page(kernel_bytes)
    if r_size:
        out += pad_to_page(ramdisk_bytes)
    return bytes(out)


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    single_dtb = os.path.join(repo_root, "dtb", "willow", "dtb")
    default_dtb = single_dtb

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-k", "--kernel", required=True, help="Input ARM64 Linux-header Image (shim.bin / enxerto.bin)")
    ap.add_argument("-p", "--payload", help="Optional SWEETXNU payload to append at 4K boundary after kernel")
    ap.add_argument("-r", "--ramdisk", help="Optional ramdisk / initrd file")
    ap.add_argument("-d", "--dtb", default=default_dtb, help="DTB blob (default: dtb/willow/stock_dtb_all.bin)")
    ap.add_argument("-c", "--cmdline", default=DEFAULT_CMDLINE, help="Kernel command line")
    ap.add_argument("--header-version", type=int, default=0, choices=[0, 2], help="Boot header version (0: legacy appended DTB, 2: v2 DTB section)")
    ap.add_argument("--raw-kernel", action="store_true", help="Do not gzip-compress the kernel Image")
    ap.add_argument("--append-dtb", action="store_true", help="Append DTB to gzip stream in v2 mode")
    ap.add_argument("-o", "--output", required=True, help="Output boot.img path")
    args = ap.parse_args()

    with open(args.kernel, "rb") as f:
        kernel = f.read()
    if args.payload:
        with open(args.payload, "rb") as f:
            payload = f.read()
        kernel = pad_to_page(kernel, 4096) + payload

    with open(args.dtb, "rb") as f:
        dtb = f.read()

    ramdisk = b""
    if args.ramdisk:
        with open(args.ramdisk, "rb") as f:
            ramdisk = f.read()

    if args.header_version == 0:
        img = build_bootv0(
            kernel_bytes=kernel,
            dtb_bytes=dtb,
            ramdisk_bytes=ramdisk,
            cmdline=args.cmdline,
            gzip_kernel=not args.raw_kernel,
        )
    else:
        img = build_bootv2(
            kernel_bytes=kernel,
            dtb_bytes=dtb,
            ramdisk_bytes=ramdisk,
            cmdline=args.cmdline,
            gzip_kernel=not args.raw_kernel,
            append_dtb=args.append_dtb,
        )
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "wb") as f:
        f.write(img)
    print(
        f"mkbootimg_willow: wrote {len(img)} bytes ({len(img):#x}) -> {args.output} "
        f"(kernel_in={len(kernel)}B, dtb={len(dtb)}B, gzip={not args.raw_kernel})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
