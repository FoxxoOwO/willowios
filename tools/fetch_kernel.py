#!/usr/bin/env python3
"""Download the kernel of a xnu build into xnu/out.

  fetch_kernel.py RUN_ID                 the xnu-kernel artifact of that run
  fetch_kernel.py --release xnu-latest   the tar.gz the xnu workflow publishes

The release is the one that works while the Actions artifact storage is over quota.
"""
import io
import json
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

REPO = 'FoxxoOwO/willowios'


def from_release(tag):
    out = subprocess.run(['gh', 'release', 'download', tag, '--repo', REPO, '--pattern', 'xnu-latest.tar.gz',
                          '--dir', 'xnu/out', '--clobber'], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f'fetch_kernel: gh release download {tag}: {out.stderr.strip()}')
    with tarfile.open('xnu/out/xnu-latest.tar.gz') as t:
        t.extractall('xnu/out')
    print('extracted', tag, 'into xnu/out')


def from_artifact(run):
    arts = json.loads(subprocess.check_output(['gh', 'api', f'/repos/{REPO}/actions/runs/{run}/artifacts'], text=True))
    aid = next(a['id'] for a in arts['artifacts'] if a['name'] == 'xnu-kernel')
    token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
    req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip',
                                 headers={'Authorization': f'Bearer {token}',
                                          'Accept': 'application/vnd.github+json'})
    red = []

    class H(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            red.append(newurl)
            return None

    try:
        urllib.request.build_opener(H).open(req)
    except Exception:
        pass
    data = urllib.request.urlopen(red[0]).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall('xnu/out')
    print('extracted artifact', aid, 'to xnu/out')


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--release':
        from_release(sys.argv[2])
    elif len(sys.argv) >= 2:
        from_artifact(sys.argv[1])
    else:
        raise SystemExit((__doc__ or '').strip())


if __name__ == '__main__':
    main()