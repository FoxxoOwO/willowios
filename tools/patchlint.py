#!/usr/bin/env python3
"""Structural lint/repair for the quilt-style .patch files in xnu/patches.

The CI loop (blacktop's build.sh) *silently skips* a patch it cannot parse:

    [warning] Skipping patch <file> (already upstream, previously applied, or
    malformed): error: corrupt patch at line N

so one broken hunk header removes a whole driver from the build without any
red X.  Two kinds of damage show up here:

  * hunk headers (``@@ -a,b +c,d @@``) whose counts disagree with the body
  * a file that does not end in a newline ("corrupt patch at line <last>")

Usage:
    python3 tools/patchlint.py            # report every damaged patch
    python3 tools/patchlint.py --fix      # rewrite the hunk headers
"""
import re
import sys
import glob

HUNK = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')


def is_terminator(lines, i):
    """True if lines[i] cannot be part of a hunk body."""
    line = lines[i]
    if line == '' or line.startswith('@@') or line.startswith('diff --git') \
            or line.startswith('index ') or line.startswith('-- ') \
            or line.startswith(r'\ No newline'):
        return True
    if line.startswith('--- ') and i + 1 < len(lines) \
            and lines[i + 1].startswith('+++ '):
        return True
    return False


def parse(text):
    """Split into hunks. Returns (lines, [(header_index, old_start, old_count,
    new_start, new_count, body_old, body_new)]).

    The body is delimited by the next terminator; its real counts are counted
    independently of the header, so a wrong header is detectable."""
    lines = text.split('\n')
    out = []
    i = 0
    while i < len(lines):
        m = HUNK.match(lines[i])
        if not m:
            i += 1
            continue
        old_start, old_count = int(m.group(1)), int(m.group(2) or 1)
        new_start, new_count = int(m.group(3)), int(m.group(4) or 1)
        body_old = body_new = 0
        j = i + 1
        while j < len(lines) and not is_terminator(lines, j):
            line = lines[j]
            if line.startswith('+'):
                body_new += 1
            elif line.startswith('-'):
                body_old += 1
            elif line.startswith(' '):
                body_old += 1
                body_new += 1
            else:
                break               # not diff content: end of the hunk
            j += 1
        out.append((i, old_start, old_count, new_start, new_count,
                    body_old, body_new))
        i = j
    return lines, out


def main(argv):
    fix = '--fix' in argv
    paths = [a for a in argv if not a.startswith('--')] or \
        sorted(glob.glob('xnu/patches/*.patch'))
    damaged = 0
    for path in paths:
        raw = open(path, 'rb').read()
        text = raw.decode('utf-8', 'surrogateescape')
        lines, hunks = parse(text)
        problems = []
        if not raw.endswith(b'\n'):
            problems.append('file does not end with a newline')
        for (i, os_, oc, ns, nc, bo, bn) in hunks:
            if oc != bo or nc != bn:
                problems.append(f'hunk at line {i + 1}: header -{os_},{oc} '
                                f'+{ns},{nc} but body is -{bo} +{bn}')
        if not problems:
            continue
        damaged += 1
        print(path)
        for p in problems:
            print('  ' + p)
        if not fix:
            continue
        # Repair the counts only.  The new-side start numbers are left alone:
        # git applies with the old-side positions, and rewriting the new side
        # would need a per-file delta (0955 holds hunks for two source files),
        # which is exactly how a "fix" turns into a corrupt patch again.
        for (i, os_, oc, ns, nc, bo, bn) in hunks:
            m = HUNK.match(lines[i])
            lines[i] = f'@@ -{os_},{bo} +{ns},{bn} @@{m.group(5)}'
        out = '\n'.join(lines).rstrip('\n') + '\n'
        open(path, 'w', encoding='utf-8', newline='').write(out)
        print('  -> repaired')
    print(f'{len(paths)} patch(es) checked, {damaged} with structural damage')
    return 1 if damaged and not fix else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
