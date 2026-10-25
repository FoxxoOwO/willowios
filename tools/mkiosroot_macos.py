#!/usr/bin/env python3
"""Build the SWEET iOS root on macOS using native hdiutil and rsync.

Usage:
  python3 tools/mkiosroot_macos.py OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.raw [SIZE]
"""
import os
import plistlib
import subprocess
import sys


def attach_dmg(dmg_path):
    print(f"Attaching {dmg_path}...")
    out = subprocess.check_output(['hdiutil', 'attach', '-plist', '-nobrowse', '-readonly', dmg_path])
    pl = plistlib.loads(out)
    for entity in pl.get('system-entities', []):
        mp = entity.get('mount-point')
        if mp:
            print(f"  Mounted at: {mp}")
            return mp
    raise RuntimeError(f"No mount point found for {dmg_path}")


def detach(mount_point):
    if os.path.exists(mount_point):
        print(f"Detaching {mount_point}...")
        subprocess.run(['hdiutil', 'detach', mount_point, '-force'], check=False)


def main():
    if len(sys.argv) < 5:
        print("Usage: mkiosroot_macos.py OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.raw [SIZE]")
        sys.exit(1)

    os_dmg = os.path.abspath(sys.argv[1])
    sysos_dmg = os.path.abspath(sys.argv[2])
    appos_dmg = os.path.abspath(sys.argv[3])
    out_raw = os.path.abspath(sys.argv[4])
    size = sys.argv[5] if len(sys.argv) > 5 else "16g"

    mounts_to_cleanup = []

    try:
        os_mnt = attach_dmg(os_dmg)
        mounts_to_cleanup.append(os_mnt)

        sysos_mnt = attach_dmg(sysos_dmg)
        mounts_to_cleanup.append(sysos_mnt)

        appos_mnt = attach_dmg(appos_dmg)
        mounts_to_cleanup.append(appos_mnt)

        # Create target HFS+ image
        if os.path.exists(out_raw):
            os.remove(out_raw)
        dmg_temp = out_raw + ".dmg"
        if os.path.exists(dmg_temp):
            os.remove(dmg_temp)

        print(f"Creating case-sensitive Journaled HFS+ image ({size})...")
        subprocess.check_call([
            'hdiutil', 'create', '-size', size,
            '-fs', 'Case-sensitive Journaled HFS+',
            '-volname', 'iOSRoot',
            '-layout', 'NONE',
            dmg_temp
        ])
        os.rename(dmg_temp, out_raw)

        print("Attaching target HFS+ image...")
        out = subprocess.check_output(['hdiutil', 'attach', '-plist', '-nobrowse', out_raw])
        pl = plistlib.loads(out)
        root_mnt = None
        for entity in pl.get('system-entities', []):
            mp = entity.get('mount-point')
            if mp:
                root_mnt = mp
                break
        if not root_mnt:
            raise RuntimeError(f"Failed to mount target image {out_raw}")
        mounts_to_cleanup.append(root_mnt)
        print(f"Target mounted at {root_mnt}")

        print("Copying OS root...")
        subprocess.check_call(['sudo', 'rsync', '-aH', '--numeric-ids', f"{os_mnt}/", f"{root_mnt}/"])

        print("Copying SystemOS cryptex...")
        target_sys = f"{root_mnt}/private/preboot/Cryptexes/OS"
        subprocess.check_call(['sudo', 'mkdir', '-p', target_sys])
        subprocess.check_call(['sudo', 'rsync', '-aH', '--numeric-ids', f"{sysos_mnt}/", f"{target_sys}/"])

        print("Copying AppOS cryptex...")
        target_app = f"{root_mnt}/private/preboot/Cryptexes/App"
        subprocess.check_call(['sudo', 'mkdir', '-p', target_app])
        subprocess.check_call(['sudo', 'rsync', '-aH', '--numeric-ids', f"{appos_mnt}/", f"{target_app}/"])

        print("Hard-linking dyld shared cache...")
        dsc = f"{target_sys}/System/Library/Caches/com.apple.dyld"
        cache_dest = f"{root_mnt}/System/Library/Caches/com.apple.dyld"
        subprocess.check_call(['sudo', 'mkdir', '-p', cache_dest])
        if os.path.exists(dsc):
            for f in os.listdir(dsc):
                src_file = os.path.join(dsc, f)
                if os.path.isfile(src_file):
                    subprocess.check_call(['sudo', 'ln', src_file, os.path.join(cache_dest, f)])

        print("Hard-linking cryptex files to root...")
        for c in ('OS', 'App'):
            base = f"{root_mnt}/private/preboot/Cryptexes/{c}"
            if not os.path.exists(base):
                continue
            for dirpath, _, filenames in os.walk(base):
                if 'System/Library/Caches/com.apple.dyld' in dirpath:
                    continue
                for fname in filenames:
                    src = os.path.join(dirpath, fname)
                    rel = os.path.relpath(src, base)
                    dst = os.path.join(root_mnt, rel)
                    if not os.path.exists(dst) and not os.path.islink(dst):
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        if os.path.islink(src):
                            subprocess.check_call(['sudo', 'cp', '-P', src, dst])
                        else:
                            subprocess.check_call(['sudo', 'ln', src, dst])

        print("Setting up diagnostics and uuidtext...")
        db = f"{root_mnt}/private/var/db"
        subprocess.check_call(['sudo', 'install', '-d', '-o', '272', '-g', '272', '-m', '0751', f"{db}/diagnostics"])
        subprocess.check_call(['sudo', 'install', '-d', '-o', '272', '-g', '272', '-m', '0755', f"{db}/uuidtext", f"{db}/diagnostics/timesync"])
        for d in ('diagnostics', 'uuidtext', 'diagnostics/timesync'):
            subprocess.check_call(['sudo', 'install', '-o', '272', '-g', '272', '-m', '0644', '/dev/null', f"{db}/{d}/.migrated"])

        print("Creating system keybag...")
        kb_dir = f"{root_mnt}/private/var/keybags"
        subprocess.check_call(['sudo', 'install', '-d', '-m', '0700', '-o', '0', '-g', '0', kb_dir])
        kb_path = f"{kb_dir}/systembag.kb"
        kb_content = (
            b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            b'<plist version="1.0"><dict><key>KeyBagKeys</key><data>U1dFRVQ=</data></dict></plist>\n'
        )
        with open('/tmp/systembag.kb', 'wb') as f:
            f.write(kb_content)
        subprocess.check_call(['sudo', 'install', '-m', '0600', '-o', '0', '-g', '0', '/tmp/systembag.kb', kb_path])

        print("Applying sweet root tweaks...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        tweaks_script = os.path.join(script_dir, 'sweet-root-tweaks.py')
        subprocess.check_call(['sudo', 'python3', tweaks_script, root_mnt])

        print("Syncing...")
        subprocess.run(['sync'])

    finally:
        for mp in reversed(mounts_to_cleanup):
            detach(mp)

    print(f"SUCCESS: Built {out_raw}")


if __name__ == '__main__':
    main()
