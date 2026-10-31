#!/usr/bin/env python3
"""Build the minimal Apple Device Tree that the WILLOW (Redmi Note 8T, SM6125 trinket) XNU needs to boot.

Every MMIO and DDR address comes from the Xiaomi Redmi Note 8T (willow) live device
and stock V12.5.6.0.RCXMIXM FDT (rom-8.dtb + dtbo-11.dtb).
Usage:
  mkadt.py OUT.adt [--dump] [--qemu] [--highmem] [--midmem] [--lowmem] [--native]
  mkadt.py -o OUT.adt [...]
"""
import hashlib, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402

# Kernel-managed RAM on willow (4 GB DDR: 0x40000000..0x100000000 + 0x100000000..0x140000000).
# Every Qualcomm reserved-memory carve-out (0x45700000..0x61a00000, including cont_splash@5c000000
# and ramoops@61600000) sits below 0x62000000.
# 0x80000000 + 3 GiB (0xc0000000 -> 0x80000000..0x140000000) is 100% contiguous RAM with 2 GiB
# below 4 GiB (for 32-bit MDP scanout & Adreno 610 DMA) and 1 GiB above 4 GiB.
PHYS_BASE = 0x80000000
MEM_SIZE = 0xC0000000
HIGH_PHYS_BASE = 0x80000000
HIGH_MEM_SIZE = 0xC0000000
MID_PHYS_BASE = int(os.environ.get("MIDBASE", "0x80000000"), 16)
MID_MEM_SIZE = int(os.environ.get("MIDSIZE", "0xC0000000"), 16)
LOW_PHYS_BASE = 0x80000000
LOW_MEM_SIZE = 0x80000000

# /arm-io children are relative to this; it must not be 0 (serial_init bails)
SOC_BASE = 0x01000000

# intc@f200000 (redistributor-stride 0x20000, 8 cores: Silver 0..3, Gold 4..7)
GICD, GICD_SIZE = 0x0F200000, 0x10000
GICR, GICR_SIZE = 0x0F300000, 0x100000
# cont_splash_region @ 0x5c000000 left lit by ABL (1080x2340 BGRX8888)
FB, FB_SIZE = 0x5C000000, 0xF00000
SWEET_ECID = 0x57494C4C4F573854  # 'WILLOW8T', synthetic
FB_W, FB_H, FB_STRIDE = 1080, 2340, 1080 * 4
# Internal eMMC 5.1 host on willow (sdhci@4744000: hc_mem 0x4744000, cmdq_mem 0x4745000)
UFS, UFS_SIZE = 0x04744000, 0x2000
TIMEBASE = 19200000
VTIMER_INTID = 19
# QEMU virt (-M virt,gic-version=3 -cpu cortex-a76): GICD/GICR and the generic timer's CNTFRQ
QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE = 0x08000000, 0x080A0000, 62500000
QEMU_VTIMER_INTID = 27

BOOT_MANIFEST_HASH = hashlib.sha384(b"willow boot manifest").digest()

D22AP_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../research/ipsw-x/d22ap.adt")

D22AP_PRODUCT_FALLBACK = [
    ("sandman-support", b"\x01\x00\x00\x00"),
    ("display-mirroring", b"\x01\x00\x00\x00"),
    ("car-integration", b"\x01\x00\x00\x00"),
    ("assistant", b"\x01\x00\x00\x00"),
    ("lockdown-certtype", b"\x01\x00\x00\x00"),
    ("ui-pip", b"\x01\x00\x00\x00"),
    ("wifi-chipset", b"4357\x00"),
    ("product-name", b"iPhone X\x00"),
    ("hearingaid-audio-equalization", b"\x01\x00\x00\x00"),
    ("RF-exposure-separation-distance", b"\x05\x00\x00\x00"),
    ("mobiledevice-min-ver", b"1400\x00"),
    ("product-id", b"\xfd\x07\x9b)\x81D\xa7\xde\xb4\xd7\xc8\x7f\xef>\xb4t\xd8\xf0\xe7\xeb"),
    ("gps-capable", b"\x01\x00\x00\x00"),
    ("product-description", b"iPhone X\x00"),
    ("allow-32bit-apps", b"\x01\x00\x00\x00"),
    ("low-power-wallet-mode", b"\x01\x00\x00\x00"),
    ("builtin-mics", b"\x04\x00\x00\x00"),
    ("has-boot-chime", b"\x00\x00\x00\x00"),
    ("supports-burnin-mitigation", b"\x01\x00\x00\x00"),
    ("compatible-device-fallback", b"iPhone9,2\x00"),
    ("device-perf-memory-class", b"\x04\x00\x00\x00"),
    ("artwork-scale-factor", b"\x03\x00\x00\x00"),
    ("baseband-chipset", b"mav17\x00"),
    ("hearingaid-low-energy-audio", b"\x01\x00\x00\x00"),
    ("ui-background-quality", b"d\x00\x00\x00"),
    ("supports-avatars", b""),
    ("public-key-accelerator", b"\x01\x00\x00\x00"),
    ("disable-globe-map", b""),
    ("artwork-device-idiom", b"phone\x00"),
    ("device-color-policy", b"\x00\x00\x00\x00"),
    ("graphics-featureset-class", b"APPLE4\x00"),
    ("siri-gesture", b"\x01\x00\x00\x00"),
    ("supports-maps-optical-heading", b""),
    ("compatible-app-variant", b"0\x00"),
    ("artwork-dynamic-displaymode", b"0\x00"),
    ("bluetooth-le", b"\x01\x00\x00\x00"),
    ("watch-companion", b"\x01\x00\x00\x00"),
    ("has-applelpm", b"\x00\x00\x00\x00"),
    ("iap2-protocol-supported", b"\x01\x00\x00\x00"),
    ("ephemeral-data-mode", b"\x00\x00\x00\x00"),
    ("activation-protocol-version", b"\x02\x00\x00\x00"),
    ("volume-up-button-location", b"x\xb0\t\x00\xff\x96\x14\x000\xe0\x03\x00\xca\x9d\x01\x00\x10'\x00\x00"),
    ("ptp-large-files", b"\x01\x00\x00\x00"),
    ("udid-version", b"\x01\x00\x00\x00"),
    ("offline-dictation", b"\x01\x00\x00\x00"),
    ("location-reminders", b"\x01\x00\x00\x00"),
    ("ui-weather-quality", b"d\x00\x00\x00"),
    ("graphics-featureset-fallbacks", b"APPLE3:APPLE3v1:APPLE2:APPLE1:GLES2,0\x00"),
    ("dictation", b"\x01\x00\x00\x00"),
    ("itunes-min-ver", b"\x03\x07\x0c\x00"),
    ("artwork-display-gamut", b"sRGB\x00"),
    ("front-cam-offset-from-center", b"\xd0\x01\x01\x00\x9e\x1d\x00\x00\xe8\x03\x00\x00\x00\x00\x00\x00"),
    ("ui-reachability", b"\x01\x00\x00\x00"),
    ("volume-down-button-location", b"x\xb0\t\x00\xff\x96\x14\x00H\xd0\x05\x00\xca\x9d\x01\x00\x10'\x00\x00"),
    ("personal-hotspot", b"\x01\x00\x00\x00"),
    ("single-stage-boot", b"\x01\x00\x00\x00"),
    ("mobiledevice-beta-min-ver", b"1190.100.2\x00"),
    ("oled-display", b"\x01\x00\x00\x00"),
    ("thin-bezel", b"\x01\x00\x00\x00"),
    ("artwork-device-subtype", b"\x84\t\x00\x00"),
    ("side-button-location", b"u\xf3\x00\x00*\x0f\x02\x00\x00q\x00\x00\xea?\x00\x00\xe8\x03\x00\x00"),
]


def d22ap_product(path=D22AP_ADT):
    """/product properties of the real D22AP tree, without the syscfg placeholders."""
    if not os.path.exists(path):
        return list(D22AP_PRODUCT_FALLBACK)
    root, _ = adt.parse(open(path, "rb").read())
    for c in root.children:
        if dict((k, v) for k, f, v in c.props).get("name") == b"product\0":
            return [(k, v) for k, f, v in c.props if not f and k not in ("name", "AAPL,phandle")]
    raise SystemExit(f"{path}: no /product node")


u32 = lambda *v: struct.pack("<%dI" % len(v), *v)
u64 = lambda *v: struct.pack("<%dQ" % len(v), *v)
cstr = lambda s: s.encode() + b"\0"


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [("name", 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


def build(seed=None, qemu=False, highmem=False, native=False, midmem=False, lowmem=False, blobs=None):
    """qemu=True: same tree, but with QEMU virt's GIC addresses and CNTFRQ (tools/qemu-sweet.py)."""
    phys_base, mem_size = (
        (LOW_PHYS_BASE, LOW_MEM_SIZE)
        if lowmem
        else (MID_PHYS_BASE, MID_MEM_SIZE)
        if midmem
        else (HIGH_PHYS_BASE, HIGH_MEM_SIZE)
        if highmem
        else (PHYS_BASE, MEM_SIZE)
    )
    gicd, gicr, timebase = (QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE) if qemu else (GICD, GICR, TIMEBASE)
    seed = seed if seed is not None else os.urandom(64)
    phandle = iter(range(1, 1000))
    ph = lambda: ("AAPL,phandle", u32(next(phandle)))

    chosen = node(
        "chosen",
        [
            ph(),
            ("dram-base", u64(phys_base)),
            ("dram-size", u64(mem_size)),
            ("random-seed", seed),
            ("debug-enabled", u32(1)),
            ("firmware-version", cstr("willow-shim")),
            ("system-firmware-version", cstr("willow-shim")),
            ("boot-manifest-hash", BOOT_MANIFEST_HASH),
            ("crypto-hash-method", cstr("sha2-384")),
            ("display-scale", u32(3)),
            ("display-rotation", u32(0)),
            ("unique-chip-id", struct.pack("<Q", SWEET_ECID)),
            ("chip-id", u32(0x8015)),
            ("board-id", u32(0x06)),
            ("mac-address-wifi0", b"\x02\x57\x49\x4c\x00\x01"),
            ("mac-address-bluetooth0", b"\x02\x57\x49\x4c\x00\x02"),
            ("software-behavior", b"\x00" * 16),
            ("certificate-production-status", u32(0)),
            ("effective-production-status-ap", u32(0)),
            ("certificate-security-mode", u32(1)),
            ("effective-security-mode-sep", u32(1)),
        ]
        + ([] if blobs is None else [("topaz-blobs", blobs)]),
        [
            node("memory-map", [ph()]),
            node("asmb", [ph(), ("lp-sip0", u64(0x6F)), ("lp-sip1", u32(1))]),
        ],
    )

    # WILLOW SMP: the four Cortex-A73 (Kryo 260 Gold) cores, MPIDR 0x100-0x103:
    # the Kryo 260 Silver cores (0x0..0x3) have no 16K granule, so the shim boots xnu
    # on gold CPU 0x100 and parks the silver cluster.
    cpu_nodes = []
    for core in range(1 if qemu else 4):
        cpu_nodes.append(
            node(
                f"cpu{core}",
                [
                    ph(),
                    ("device_type", cstr("cpu")),
                    ("compatible", cstr("qcom,kryo260") + cstr("qcom,kryo470") + cstr("ARM,v8")),
                    ("reg", u32(core if qemu else 0x100 | core)),
                    ("cpu-id", u32(core)),
                    ("cluster-id", u32(0)),
                    ("cluster-type", u32(0)),
                    ("die-cluster-id", u32(0)),
                    ("cluster-core-id", u32(core)),
                    ("l2-cache-id", u32(0)),
                    ("l3-cache-id", u32(0)),
                    ("state", cstr("running" if core == 0 else "stopped")),
                    ("timebase-frequency", u32(timebase)),
                    ("clock-frequency", u32(2016000000)),
                    ("bus-frequency", u32(100000000)),
                    ("memory-frequency", u32(1866000000)),
                    ("peripheral-frequency", u32(timebase)),
                    ("fixed-frequency", u32(timebase)),
                ],
            )
        )
    cpus = node("cpus", [ph(), ("#address-cells", u32(1)), ("#size-cells", u32(0))], cpu_nodes)

    gic = node(
        "gic",
        [
            ph(),
            ("compatible", cstr("arm,gic-v3")),
            ("interrupt-controller", b""),
            ("virtual-timer-intid", u32(QEMU_VTIMER_INTID if qemu else VTIMER_INTID)),
            ("reg", u64(gicd - SOC_BASE, GICD_SIZE, gicr - SOC_BASE, GICR_SIZE)),
        ],
    )
    arm_io = node(
        "arm-io",
        [
            ph(),
            ("device_type", cstr("sweet-io")),
            ("compatible", cstr("sweet-io") + cstr("arm-io")),
            ("#address-cells", u32(2)),
            ("#size-cells", u32(2)),
            ("ranges", u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
        ],
        [
            gic,
            node("wdt", [ph(), ("no-pmu", u32(1))]),
            node(
                "wlan",
                [
                    ph(),
                    ("device_type", cstr("wlan")),
                    ("compatible", cstr("topaz,wcn3988") + cstr("willow,wcn3990")),
                ],
            ),
            node(
                "disp0",
                [
                    ph(),
                    ("device_type", cstr("display-subsystem")),
                    ("compatible", cstr("sweet,display")),
                    ("canvas-width", u32(1080 if native else 1125)),
                    ("canvas-height", u32(2340 if native else 2436)),
                ],
            ),
        ],
    )

    fbcon = node(
        "sweet-fbcon",
        [
            ph(),
            ("reg", u64(FB, FB_SIZE)),
            ("width", u32(FB_W)),
            ("height", u32(FB_H)),
            ("stride", u32(FB_STRIDE)),
        ],
    )

    # bsd/dev/sweet_ufs.c (patch 0952): willow sdhci@4744000 eMMC 5.1 host
    ufs = node(
        "sweet-ufs",
        [
            ph(),
            ("compatible", cstr("willow,sdhci") + cstr("qcom,sdhci-msm-v5") + cstr("qcom,ufshc")),
            ("reg", u64(UFS, UFS_SIZE)),
        ],
    )

    defaults = node("defaults", [ph(), ("no-effaceable-storage", u32(1))])

    buttons = node(
        "buttons",
        [
            ph(),
            ("button-names", cstr("volup") + cstr("voldown") + cstr("hold")),
            ("home-button-type", u32(2)),
            ("opposed-power-vol-buttons", u32(1)),
        ],
    )

    product_props = d22ap_product()
    if product_props:
        product_props = [(k, cstr("sRGB") if k == "artwork-display-gamut" else v) for k, v in product_props]
    haptics = node(
        "haptics",
        [
            ph(),
            ("closed-loop", u32(1)),
            ("supports-3rd-party-haptics", u32(1)),
        ],
    )
    product = [node("product", [ph()] + product_props, [haptics])] if product_props else []
    padded32 = lambda s: s.encode().ljust(32, b"\0")[:32]

    return node(
        "device-tree",
        [
            ph(),
            (
                "compatible",
                cstr("D22AP")
                + cstr("iPhone10,3")
                + cstr("xiaomi,willow")
                + cstr("xiaomi,ginkgo")
                + cstr("xiaomi,topaz")
                + cstr("xiaomi,sweet")
                + cstr("qcom,trinket")
                + cstr("AppleARM"),
            ),
            ("model", cstr("iPhone10,3")),
            ("target-type", cstr("D22")),
            ("target-sub-type", cstr("D22AP")),
            ("manufacturer", cstr("Apple Inc.")),
            ("platform-name", cstr("t8015")),
            ("serial-number", padded32("WIL00REDMI8T")),
            ("mlb-serial-number", padded32("WIL00REDMI8TMLB00")),
            ("model-number", padded32("MQAC2")),
            ("region-info", padded32("LL/A")),
            ("regulatory-model-number", padded32("A1865")),
            ("#address-cells", u32(2)),
            ("#size-cells", u32(2)),
        ],
        [chosen, defaults, cpus, arm_io, fbcon, buttons] + product + ([] if qemu else [ufs]),
    )


if __name__ == "__main__":
    out_path = None
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a in ("-o", "--output") and i + 1 < len(argv):
            out_path = argv[i + 1]
            break
    if out_path is None:
        pos = [a for a in argv if not a.startswith("-")]
        if not pos:
            raise SystemExit("Usage: mkadt.py [-o] OUT.adt [--dump] [--qemu] [--highmem] [--midmem] [--lowmem] [--native]")
        out_path = pos[0]

    blobs_path = None
    for i, a in enumerate(argv):
        if a == "--blobs" and i + 1 < len(argv):
            blobs_path = argv[i + 1]
    root = build(
        blobs=open(blobs_path, "rb").read() if blobs_path else None,
        qemu="--qemu" in argv,
        highmem="--highmem" in argv,
        native="--native" in argv,
        midmem="--midmem" in argv,
        lowmem="--lowmem" in argv,
    )
    blob = adt.serialize(root)
    open(out_path, "wb").write(blob)
    if "--dump" in argv:
        adt.dump(adt.parse(blob)[0])
    print(f"{out_path}: {len(blob)} bytes (dram=0x{PHYS_BASE:x}+0x{MEM_SIZE:x}, fb={FB_W}x{FB_H}@0x{FB:x}, sdhci@0x{UFS:x})", file=sys.stderr)
