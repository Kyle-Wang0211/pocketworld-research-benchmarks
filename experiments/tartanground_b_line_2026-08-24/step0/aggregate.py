#!/usr/bin/env python3.11
import json, glob, os, sys
import numpy as np

FILES = sys.argv[1:] or sorted(glob.glob('res_*.json'))
KEYS = ['f25', 'f50', 'f100', 'f200', 'c0.01', 'c0.02', 'c0.04', 'c0.08']

print('%-16s %5s %6s | %s' % ('group', 'n', 'meanI', '  '.join(
    '%s med/p90/>50%%' % k for k in ['f100', 'c0.04'])))
for f in FILES:
    r = json.load(open(f))
    rows = r['rows']
    mg = np.array([x['mean_gray'] for x in rows])
    out = []
    for k in ['f100', 'c0.04']:
        v = np.array([x[k] for x in rows])
        out.append('%.3f/%.3f/%.3f' % (np.median(v), np.percentile(v, 90), (v > 0.5).mean()))
    print('%-16s %5d %6.1f | %s' % (r['name'], len(rows), mg.mean(), '   '.join(out)))

print()
print('full table (median / p90 / frac>0.5) for every threshold')
for f in FILES:
    r = json.load(open(f)); rows = r['rows']
    print('== %s (n=%d, meanI=%.1f, noise_sigma=%.1f)' % (
        r['name'], len(rows), np.mean([x['mean_gray'] for x in rows]), r.get('noise_sigma', 0)))
    for k in KEYS:
        if k not in rows[0]:
            continue
        v = np.array([x[k] for x in rows])
        print('   %-6s med=%.3f p90=%.3f  frac>0.5=%.3f  frac>0.3=%.3f'
              % (k, np.median(v), np.percentile(v, 90), (v > 0.5).mean(), (v > 0.3).mean()))

print()
print('representative lowest-texture frames (top3 by f100):')
for f in FILES:
    r = json.load(open(f)); rows = r['rows']
    v = np.array([x['f100'] for x in rows]); o = np.argsort(-v)[:3]
    print('== %s' % r['name'])
    for i in o:
        print('   f100=%.3f c0.04=%.3f  %s' % (v[i], rows[i]['c0.04'], rows[i]['path']))
