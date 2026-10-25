#!/usr/bin/env python3
"""Download the xnu-kernel artifact of a GitHub Actions run into xnu/out.

  fetch_kernel.py RUN_ID
"""
import io, json, subprocess, sys, urllib.request, zipfile

REPO = 'FoxxoOwO/willowios'
run = sys.argv[1]
arts = json.loads(subprocess.check_output(['gh', 'api', f'/repos/{REPO}/actions/runs/{run}/artifacts'], text=True))
aid = next(a['id'] for a in arts['artifacts'] if a['name'] == 'xnu-kernel')
token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip',
                             headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'})
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
