#!/usr/bin/env python3
"""[xrhires] Final tables: per (resolution, arm) x scene over the variant family {r1, r2, td+-4ms, rate-frac 0.8, pace 0.25}.
k% = (k_sim3_fwd / corr - 1)*100, corr 6e2d = 1.0974 (ARKit's own cross-session error), else 1.
A run is a FAILURE if it has no result, or initialises > 3 s later than the official-640 r1 run of the same scene,
or |k% | > 20. Failures are counted and excluded from the k/ATE statistics (never averaged in)."""
import json, os, re, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORR = {'6e2d': 1.0974, '5966': 1.0, '4ad6': 1.0}
res = {}
for ln in open(W + '/runs/results.jsonl'):
    d = json.loads(ln); res[d['tag']] = d
cache = json.load(open(W + '/runs/imu_consistency_cache.json')) if os.path.exists(W + '/runs/imu_consistency_cache.json') else {}
ALIAS = {'A3Sblock9': 'N'}   # A3 (S + GFTT blockSize 9) at 1920 == N at 1920


def first_t(tag):
    p = W + '/runs/' + tag + '.cam.tum'
    if not os.path.exists(p) or os.path.getsize(p) == 0: return None
    with open(p) as f: return float(f.readline().split()[0])


t0 = {sc: first_t(f'{sc}_640_O_p1_r1') for sc in CORR}
fam = {}
for tag, d in res.items():
    m = re.match(r'(\w{4})_(\d+)_([A-Za-z0-9]+)_(.+)$', tag)
    if not m: continue
    sc, r, arm, var = m.groups()
    arm = ALIAS.get(arm, arm)
    if var == 'p1_r1' or var == 'p1_r2' or var.startswith('td') or var in ('g08', 'p025'):
        fam.setdefault((int(r), arm), {}).setdefault(sc, []).append((var, tag, d))
print('%-10s | %-40s | %-40s | %-40s | %s' % ('res/arm', '4ad6: k% mean [min,max] ATE  fail/n', '5966', '6e2d (/1.0974)', 'mean|k%| meanATE  zstd'))
summary = {}
for key in sorted(fam):
    cells, allk, allate, zs = [], [], [], []
    for sc in ['4ad6', '5966', '6e2d']:
        L = fam[key].get(sc, [])
        ks, ates, fail = [], [], 0
        for var, tag, d in L:
            ft = first_t(tag)
            bad = d.get('rc') != 0 or 'k_sim3_fwd' not in d or ft is None or (t0[sc] and ft - t0[sc] > 3.0)
            if not bad:
                kp = (d['k_sim3_fwd'] / CORR[sc] - 1) * 100
                bad = abs(kp) > 20
            if bad: fail += 1; continue
            ks.append(kp); ates.append(d['ate_sim3_cm'])
            z = cache.get(tag, {}).get('z_std')
            if z: zs.append(z)
        if ks:
            cells.append('%+5.2f [%+5.2f,%+5.2f] %4.2f  %d/%d' % (np.mean(ks), min(ks), max(ks), np.mean(ates), fail, len(L)))
            allk.append(abs(np.mean(ks))); allate.append(np.mean(ates))
        else:
            cells.append('%-40s' % ('ALL FAIL %d/%d' % (fail, len(L))))
        summary.setdefault('%d/%s' % key, {})[sc] = {'k': ks, 'ate': ates, 'fail': fail, 'n': len(L)}
    print('%-10s | %-40s | %-40s | %-40s | %5.2f   %5.2f   %4.1f' % ('%d/%s' % key, *cells, np.mean(allk) if allk else np.nan, np.mean(allate) if allate else np.nan, np.mean(zs) if zs else np.nan))
json.dump(summary, open(W + '/runs/final_summary.json', 'w'), indent=1)
