import json, glob, os, re, sys, numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = {}
for f in sorted(glob.glob(W + '/runs/*.zones.jsonl')):
    tag = os.path.basename(f)[:-len('.zones.jsonl')]
    m = re.match(r'(\w{4})_(\d+)_([A-Za-z0-9]+)_(p1|p025)_r(\d)$', tag)
    if not m: continue
    sc, res, arm, pace, r = m.groups()
    if pace != 'p1': continue
    z = {j['zone']: j for j in map(json.loads, open(f))}
    if 'frontend.work' not in z: continue
    rows.setdefault((int(res), arm), []).append(z)
def agg(zs, zone, key):
    v = [z[zone][key] for z in zs if zone in z]
    return np.mean(v) if v else float('nan')
print('%-14s %3s | %-26s | %-8s %-8s %-8s | %-20s | %s' % ('res/arm', 'n', 'frontend.work mean/p95/p99', 'prep', 'LK', 'detect', 'backend.work mean/p95', 'f1-equiv per frame (prep+LK+detect)'))
for (res, arm), zs in sorted(rows.items()):
    fw = [agg(zs, 'frontend.work', k) for k in ('mean', 'p95', 'p99')]
    pre = agg(zs, 'frontend.preprocess_call', 'mean'); lk = agg(zs, 'frontend.track_call', 'mean'); det = agg(zs, 'frontend.detect_call', 'mean')
    bw = [agg(zs, 'backend.work', k) for k in ('mean', 'p95')]
    print('%-14s %3d | %6.2f %6.2f %6.2f        | %6.2f   %6.2f   %6.2f   | %6.2f %6.2f        | %6.2f' % (f'{res}/{arm}', len(zs), *fw, pre, lk, det, *bw, pre + lk + det))
