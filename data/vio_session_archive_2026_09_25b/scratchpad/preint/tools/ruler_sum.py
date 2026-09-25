#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] LiDAR 米尺汇总(照 wobble/tools/ruler_sum.py 的口径):全场 k、5 s 段中位 k、质量闸、判定。
k = 轨迹尺度 / 米(k>1 轨迹偏大)。只作研发量尺。用法:ruler_sum.py <scene> [...]"""
import json
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint/ruler/'
NAMES = ['arkit'] + ['%s_%s_%s' % (a, d, k) for a in ('none', 'all') for d in ('p0', 'm5') for k in ('final', 'front')]

import os
PFX = os.environ.get('RULER_OUT', 'out')
out = {}
for sc in sys.argv[1:]:
    J = json.load(open(SP + '%s_%s/lidar_ruler_report.json' % (PFX, sc)))
    T = J['trajectories']
    names = NAMES if PFX == 'out' else list(T.keys())
    t0 = min(p['t_a'] for p in T['arkit']['pairs'] if 'scale_to_metric' in p)
    print('== %s' % sc)
    for n in names:
        if n not in T:
            continue
        tr = T[n]; e = tr['estimate']
        ok = [p for p in tr['pairs'] if 'scale_to_metric' in p]
        t = np.array([p['t_a'] - t0 for p in ok]); k = 1 / np.array([p['scale_to_metric'] for p in ok])
        seg = []
        for a in np.arange(0, 30, 5.0):
            m = (t >= a) & (t < a + 5)
            if m.sum() >= 3:
                seg.append((a, float(np.median(k[m])), int(m.sum())))
        rel = np.array([s[1] for s in seg]) / e['k']
        g = e.get('gates', {})
        print('  %-14s k %.4f (%+.2f%%) 有效对 %2d/%d 闸 %s → %-7s | 5 s 段 k %s | 段/全场 %+.1f…%+.1f%% sd %.1f%%' % (
            n, e['k'], 100 * (e['k'] - 1), e['pairs_with_scale'], e['pairs_attempted'],
            ''.join('✓' if g.get(x) else '✗' for x in ['G1_pairs', 'G2_between_rel_iqr', 'G3_within_rel_iqr', 'G4_alignment_minimum_at_0']),
            tr['verdict'], ' '.join('%.3f' % s[1] for s in seg), 100 * (rel.min() - 1), 100 * (rel.max() - 1), 100 * rel.std()))
        out['%s:%s' % (sc, n)] = dict(k=e['k'], seg5=seg, verdict=tr['verdict'], gates=g)
json.dump(out, open(SP + 'ruler_summary_%s.json' % PFX, 'w'), indent=1, default=float)
