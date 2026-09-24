#!/usr/bin/python3
"""Within-run tracking-epoch breaks from the page's own tracking telemetry (telemetry_official_dart.jsonl,
'tracking' events are written by ar_capture_page's pose listener = exactly where the patch's tracker observes).
A break = normal -> limited_initializing / not_available / limited_relocalizing with >=1 accepted 12MP shot
before and after it inside the same capture window. Files are stat'ed for 'dataless' before opening."""
import json, os, subprocess, sys, glob, collections
F = sys.argv[1]
roots = ['/Users/kaidongwang/Developer/pw_backups', '/Users/kaidongwang/pw_device_backups',
         '/Users/kaidongwang/Developer/pocketworld_artifacts/device_backups', '/Users/kaidongwang/Developer/device-backups',
         '/Users/kaidongwang/Documents/progecttwo/_artifacts.nosync']
files = []
for r in roots:
    for dp, dn, fn in os.walk(r):
        if dp[len(r):].count('/') > 6: dn[:] = []; continue
        if 'telemetry_official_dart.jsonl' in fn: files.append(os.path.join(dp, 'telemetry_official_dart.jsonl'))
ev = set()
for f in files:
    fl = subprocess.run(['/usr/bin/stat', '-f', '%Sf', f], capture_output=True, text=True).stdout
    if 'dataless' in fl: continue
    for l in open(f, errors='replace'):
        if '"tracking"' not in l and '"hires_still"' not in l: continue
        try: j = json.loads(l)
        except Exception: continue
        if j.get('type') == 'tracking': ev.add((j['t'], 'tracking', j.get('state')))
        elif j.get('type') == 'hires_still' and j.get('outcome') == 'ok': ev.add((j['t'], 'shot', None))
ev = sorted(ev)
rows = json.load(open(F + '/results/scan_sessions.json'))['rows']
starts = sorted((int(r['cap'][4:]) // 1000, r['cap']) for r in rows)
out = []
for i, (s, cap) in enumerate(starts):
    e = starts[i + 1][0] if i + 1 < len(starts) else s + 3600_000
    w = [x for x in ev if s - 2000 <= x[0] < min(e, s + 3600_000)]
    shots = [x[0] for x in w if x[1] == 'shot']
    if not shots: continue
    state, breaks = None, []
    for t, k, st in w:
        if k != 'tracking': continue
        if state == 'normal' and st in ('limited_initializing', 'not_available', 'limited_relocalizing'):
            before = sum(1 for x in shots if x < t); after = sum(1 for x in shots if x > t)
            if before and after: breaks.append((round((t - s) / 1000, 1), st, before, after))
        state = st
    out.append(dict(cap=cap, shots=len(shots), breaks=breaks))
covered = [o for o in out]
brk = [o for o in out if o['breaks']]
print('telemetry files', len(files), '| captures with shots in telemetry', len(covered), '| with within-run break', len(brk))
for o in brk: print(' ', o['cap'], 'shots', o['shots'], 'breaks (s_after_start, state, shots_before, shots_after):', o['breaks'])
json.dump(out, open(F + '/results/scan_tracking_breaks.json', 'w'), indent=1)
