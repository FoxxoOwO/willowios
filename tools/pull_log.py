import subprocess, sys

DEV = "/dev/block/mmcblk0p87"
ADB = r"C:\RSL\platform-tools\adb.exe"

size_str = subprocess.check_output([ADB, "shell", "blockdev", "--getsize64", DEV], text=True).strip()
total_bytes = int(size_str)
skip = (total_bytes // 4096) - 1025
print(f"{DEV}: {total_bytes} bytes, skip={skip}")

with open("sweet-log-gui25.bin", "wb") as f:
    proc = subprocess.run([ADB, "exec-out", f"dd if={DEV} bs=4096 skip={skip} count=1025 2>/dev/null"], stdout=f, check=True)

print("Downloaded sweet-log-gui25.bin successfully")
subprocess.run([sys.executable, "tools/sweet-log.py", "sweet-log-gui25.bin", "sweet-log-gui25.txt"], check=True)
print("Decoded sweet-log-gui25.txt successfully")
