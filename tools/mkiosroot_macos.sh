#!/bin/bash
set -euo pipefail

# mkiosroot_macos.sh OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.raw [SIZE]
if [ $# -lt 4 ]; then
    echo "Usage: $0 OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.raw [SIZE]"
    exit 1
fi

os=$(realpath "$1")
sysos=$(realpath "$2")
appos=$(realpath "$3")
out=$(realpath "$4")
size=${5:-16g}

work=$(mktemp -d /tmp/mkiosroot.XXXXXX)

cleanup() {
    echo "Cleaning up mounts..."
    hdiutil detach "$work/root" 2>/dev/null || true
    hdiutil detach "$work/os_mnt" 2>/dev/null || true
    hdiutil detach "$work/sysos_mnt" 2>/dev/null || true
    hdiutil detach "$work/appos_mnt" 2>/dev/null || true
    rm -rf "$work"
}
trap cleanup EXIT

mkdir -p "$work/os_mnt" "$work/sysos_mnt" "$work/appos_mnt" "$work/root"

echo "Attaching APFS DMGs..."
hdiutil attach -nobrowse -readonly -mountpoint "$work/os_mnt" "$os"
hdiutil attach -nobrowse -readonly -mountpoint "$work/sysos_mnt" "$sysos"
hdiutil attach -nobrowse -readonly -mountpoint "$work/appos_mnt" "$appos"

echo "Creating case-sensitive HFS+ disk image ($size)..."
rm -f "$out" "$out.dmg"
hdiutil create -size "$size" -fs "Case-sensitive Journaled HFS+" -volname "iOSRoot" -layout NONE "$out.dmg"
mv "$out.dmg" "$out"

echo "Attaching target HFS+ image..."
hdiutil attach -nobrowse -mountpoint "$work/root" "$out"
echo "Target mounted at $work/root"

echo "Copying OS root..."
sudo rsync -aH --numeric-ids "$work/os_mnt/" "$work/root/"

echo "Copying SystemOS cryptex..."
sudo mkdir -p "$work/root/private/preboot/Cryptexes/OS"
sudo rsync -aH --numeric-ids "$work/sysos_mnt/" "$work/root/private/preboot/Cryptexes/OS/"

echo "Copying AppOS cryptex..."
sudo mkdir -p "$work/root/private/preboot/Cryptexes/App"
sudo rsync -aH --numeric-ids "$work/appos_mnt/" "$work/root/private/preboot/Cryptexes/App/"

echo "Hard-linking shared cache..."
dsc="private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld"
sudo mkdir -p "$work/root/System/Library/Caches/com.apple.dyld"
for f in "$work/root/$dsc"/*; do
    if [ -f "$f" ]; then
        sudo ln "$f" "$work/root/System/Library/Caches/com.apple.dyld/${f##*/}"
    fi
done

echo "Hard-linking cryptex files to root..."
for c in OS App; do
    (cd "$work/root/private/preboot/Cryptexes/$c" && sudo find . ! -type d ! -path './System/Library/Caches/com.apple.dyld/*') |
    while IFS= read -r f; do
        f=${f#./}
        if ! sudo test -e "$work/root/$f" && ! sudo test -L "$work/root/$f"; then
            sudo mkdir -p "$work/root/$(dirname "$f")"
            src="$work/root/private/preboot/Cryptexes/$c/$f"
            if sudo test -L "$src"; then
                sudo cp -P "$src" "$work/root/$f"
            else
                sudo ln "$src" "$work/root/$f"
            fi
        fi
    done
done

echo "Setting up diagnostics / uuidtext..."
db="$work/root/private/var/db"
sudo install -d -o 272 -g 272 -m 0751 "$db/diagnostics"
sudo install -d -o 272 -g 272 -m 0755 "$db/uuidtext" "$db/diagnostics/timesync"
for d in diagnostics uuidtext diagnostics/timesync; do
    sudo install -o 272 -g 272 -m 0644 /dev/null "$db/$d/.migrated"
done

echo "Creating system keybag..."
sudo install -d -m 0700 -o 0 -g 0 "$work/root/private/var/keybags"
printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' \
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
    '<plist version="1.0"><dict><key>KeyBagKeys</key><data>U1dFRVQ=</data></dict></plist>' |
    sudo install -m 0600 -o 0 -g 0 /dev/stdin "$work/root/private/var/keybags/systembag.kb"

echo "Applying sweet root tweaks..."
DIR=$(dirname "$0")
sudo python3 "$DIR/sweet-root-tweaks.py" "$work/root"

echo "Syncing and unmounting..."
sync
hdiutil detach "$work/root"
hdiutil detach "$work/os_mnt"
hdiutil detach "$work/sysos_mnt"
hdiutil detach "$work/appos_mnt"
trap - EXIT
rm -rf "$work"

echo "Done! Target image: $out"
