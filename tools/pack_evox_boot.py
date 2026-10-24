#!/usr/bin/env python3
"""Pack a kernel Image into the boot.img layout that ABL accepts on a willow
running EvolutionX 15 (header_version 0, gzip(kernel)+single appended DTB,
EvolutionX ramdisk/cmdline). Needs EvolutionX zip in the repo root.
Usage: pack_evox_boot.py <Image> <out.img>
"""
import gzip, hashlib, struct, sys, zipfile

ZIP = r"D:\repositories\willowios\EvolutionX-15.0-20250507-ginkgo-10.6-Official.zip"
PAGE = 4096


def pad(d):
    r = len(d) % PAGE
    return d if r == 0 else d + b"\0" * (PAGE - r)


def main():
    img, out = sys.argv[1], sys.argv[2]
    with zipfile.ZipFile(ZIP) as z:
        boot = z.read("boot.img")
    hdr = struct.unpack("<8s10I16s512s32s1024s", boot[:48 + 16 + 512 + 32 + 1024])
    ksz, rsz = hdr[1], hdr[3]
    cmdline = hdr[12].split(b"\0")[0]
    kern = boot[PAGE:PAGE + ksz]
    pos = kern.find(b"\xd0\x0d\xfe\xed")
    dtb = kern[pos:]
    ramdisk = boot[PAGE + len(pad(kern)):][:rsz]
    kp = gzip.compress(open(img, "rb").read(), 9, mtime=0) + dtb
    sha = hashlib.sha1()
    for b in (kp, ramdisk, b""):
        sha.update(b)
        sha.update(struct.pack("<I", len(b)))
    h = struct.pack("<8s10I16s512s32s1024s", b"ANDROID!", len(kp), 0x8000,
                    len(ramdisk), 0x01000000, 0, 0, 0x100, PAGE, 0, hdr[10],
                    b"\0" * 16, cmdline.ljust(512, b"\0"),
                    sha.digest().ljust(32, b"\0"), b"\0" * 1024)
    open(out, "wb").write(pad(h) + pad(kp) + pad(ramdisk))
    print("wrote", out)


main()
