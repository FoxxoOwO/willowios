#!/usr/bin/env python3
"""Resumable robust downloader for GitHub Actions iOSRoot artifact."""
import os
import sys
import time
import zipfile
import tarfile
import subprocess
import urllib.request

ARTIFACT_ID = 12594168279
REPO = "FoxxoOwO/willowios"
OUT_ZIP = os.path.abspath("scratch/iOSRoot-sparse-image.zip")
OUT_SIMG = os.path.abspath("scratch/iOSRoot.simg")

def get_download_url():
    token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
    api_url = f"https://api.github.com/repos/{REPO}/actions/artifacts/{ARTIFACT_ID}/zip"
    req = urllib.request.Request(api_url, headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json'
    })
    
    redirect_url = []
    class Handler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirect_url.append(newurl)
            return None
            
    opener = urllib.request.build_opener(Handler)
    try:
        opener.open(req)
    except Exception:
        pass
        
    if not redirect_url:
        raise RuntimeError("Failed to resolve artifact redirect URL")
    return redirect_url[0]

def download_file(url, target_path):
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    existing_bytes = os.path.getsize(target_path) if os.path.exists(target_path) else 0

    # Get total size
    req = urllib.request.Request(url, method='HEAD')
    with urllib.request.urlopen(req) as resp:
        total_size = int(resp.headers.get('Content-Length', 0))

    print(f"Target size: {total_size / (1024*1024):.1f} MB (Existing: {existing_bytes / (1024*1024):.1f} MB)")
    if existing_bytes >= total_size and total_size > 0:
        print("Download already complete.")
        return

    chunk_size = 1024 * 1024 * 4  # 4 MB chunks
    max_retries = 20
    retry = 0

    while existing_bytes < total_size and retry < max_retries:
        try:
            req = urllib.request.Request(url)
            if existing_bytes > 0:
                req.add_header('Range', f'bytes={existing_bytes}-')
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                with open(target_path, 'ab' if existing_bytes > 0 else 'wb') as f:
                    t_last = time.time()
                    bytes_last = existing_bytes
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        existing_bytes += len(chunk)
                        t_now = time.time()
                        if t_now - t_last >= 3.0:
                            speed = (existing_bytes - bytes_last) / (t_now - t_last) / (1024*1024)
                            pct = (existing_bytes / total_size) * 100
                            print(f"\rProgress: {existing_bytes/(1024*1024):.1f}/{total_size/(1024*1024):.1f} MB ({pct:.1f}%) @ {speed:.2f} MB/s", end="", flush=True)
                            t_last = t_now
                            bytes_last = existing_bytes
            print(f"\rProgress: {existing_bytes/(1024*1024):.1f}/{total_size/(1024*1024):.1f} MB (100.0%) - Download complete!")
            break
        except Exception as e:
            retry += 1
            print(f"\n[Retry {retry}/{max_retries}] Connection interrupted ({e}), resuming in 3s...")
            time.sleep(3)
            # Re-fetch redirect URL if needed (in case SAS token expired)
            url = get_download_url()

def extract_simg(zip_path):
    print(f"Extracting {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        namelist = z.namelist()
        print("Archive contents:", namelist)
        # Find tar.gz or simg
        tar_name = [n for n in namelist if 'tar.gz' in n]
        if tar_name:
            z.extract(tar_name[0], "scratch")
            tar_path = os.path.join("scratch", tar_name[0])
            print(f"Extracting {tar_path}...")
            with tarfile.open(tar_path, 'r:gz') as t:
                t.extractall("scratch")
            os.remove(tar_path)
        else:
            z.extractall("scratch")
            
    if os.path.exists(OUT_SIMG):
        sz = os.path.getsize(OUT_SIMG)
        print(f"SUCCESS: {OUT_SIMG} ready ({sz / (1024*1024):.1f} MB)")
        with open(OUT_SIMG, 'rb') as f:
            magic = f.read(4)
            if magic == b'\x3a\xff\x26\xed':
                print("Verified Android sparse image magic (0xed26ff3a)!")
            else:
                print(f"Note: magic is {magic.hex()}")
    else:
        print(f"Warning: {OUT_SIMG} not found after extraction. Checking scratch/:")
        for f in os.listdir("scratch"):
            print(" ", f)

if __name__ == '__main__':
    url = get_download_url()
    download_file(url, OUT_ZIP)
    extract_simg(OUT_ZIP)
