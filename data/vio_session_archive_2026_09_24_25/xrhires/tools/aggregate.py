#!/usr/bin/env python3
"""[xrhires] Aggregate results.jsonl: scale k vs ARKit (6e2d divided by 1.0974 = ARKit's own cross-session error,
scaleS1 results_xsession.json), ATE, repeats, perturbations, IMU consistency."""
import json, os, sys, re, subprocess
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORR = {'6e2d': 1.0974, '5966': 1.0, '4ad6': 1.0}
rows = {}
for ln in open(W + '/runs/results.jsonl'):
    d = json.loads(ln)
    if d.get('rc') != 0 or 'k_sim3_fwd' not in d: continue
    rows[d['tag']] = d   # last wins
sys.path.insert(0, W + '/tools')
import imu_consistency as ic
IMU = {}
cache_f = W + '/runs/imu_consistency_cache.json'
cache = json.load(open(cache_f)) if os.path.exists(cache_f) else {}
for tag in rows:
    if tag not in cache:
        sc = tag[:4]
        try: cache[tag] = ic.analyse(W + '/runs/' + tag + '.body.tum', sc)
        except Exception as e: cache[tag] = {'err': repr(e)}
json.dump(cache, open(cache_f, 'w'))
def kdev(tag):
    d = rows[tag]; return (d['k_sim3_fwd'] / CORR[tag[:4]] - 1) * 100
def arm_of(tag):
    return tag[5:]
arms = {}
for tag in rows:
    arms.setdefault(arm_of(tag), {})[tag[:4]] = tag
order = sorted(arms, key=lambda a: (int(re.match(r'(\d+)', a).group(1)), a))
print('%-26s | %-22s %-22s %-22s | %8s %8s | %s' % ('arm', '4ad6 k%/ATEcm/zstd', '5966', '6e2d(/1.0974)', 'mean|k|', 'meanATE', 'k-CI95 width 4ad6/5966/6e2d'))
for a in order:
    cells, ks, ates, cis = [], [], [], []
    for sc in ['4ad6', '5966', '6e2d']:
        t = arms[a].get(sc)
        if not t: cells.append('%-22s' % '-'); continue
        d = rows[t]; kd = kdev(t); ks.append(abs(kd)); ates.append(d['ate_sim3_cm'])
        z = cache.get(t, {}).get('z_std', float('nan'))
        cells.append('%-22s' % ('%+6.2f / %5.2f / %4.1f' % (kd, d['ate_sim3_cm'], z)))
        ci = d.get('k_sim3_fwd_ci95') or [np.nan, np.nan]; cis.append('%.3f' % ((ci[1] - ci[0]) / CORR[sc]))
    print('%-26s | %s | %8.2f %8.2f | %s' % (a, ' '.join(cells), np.mean(ks) if ks else np.nan, np.mean(ates) if ates else np.nan, '/'.join(cis)))
