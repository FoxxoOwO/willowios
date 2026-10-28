#!/usr/bin/env python3
"""Pack files into the container the kernel installs from /chosen ("topaz-blobs").

  mkblobs.py OUT.bin FILE [FILE ...]

The container (see xnu/patches/0962-sweet-blobs-from-the-device-tree.patch):

  "TOPAZBLB", u32 version = 1, u32 count,
  count x { char name[128]; u32 mode; u32 pad; u64 size },
  then the contents of each file, 16-byte aligned.

Only the base name travels: the kernel picks the directory (the first writable one of
/private/var/tmp, /private/var, /tmp, /) and logs where it put them.
"""
import os
import struct
import sys

MAGIC = b"TOPAZBLB"
VERSION = 1


def build(paths):
    entries = []
    data = bytearray()
    for path in paths:
        name = os.path.basename(path)
        if len(name) > 127:
            raise SystemExit(f"mkblobs: {name}: name too long")
        with open(path, "rb") as f:
            body = f.read()
        entries.append(struct.pack("<128sIIQ", name.encode(), 0o755, 0, len(body)))
        data += body
        data += b"\0" * (-len(body) & 15)
    out = MAGIC + struct.pack("<II", VERSION, len(entries)) + b"".join(entries) + bytes(data)
    return out


def main():
    if len(sys.argv) < 3:
        raise SystemExit((__doc__ or "").strip())
    out = build(sys.argv[2:])
    with open(sys.argv[1], "wb") as f:
        f.write(out)
    print(f"mkblobs: {len(sys.argv) - 2} files, {len(out)} bytes -> {sys.argv[1]}")


if __name__ == "__main__":
    main()