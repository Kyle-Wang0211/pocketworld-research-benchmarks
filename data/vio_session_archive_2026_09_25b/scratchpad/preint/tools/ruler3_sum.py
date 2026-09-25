#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 米尺第三批汇总:四种帧对间隔 × 三场 × {ARKit, 新引擎 Δ−4 加计 0/−16, 旧引擎 Δ0 加计 0/−16}(后端定稿)。
只统计全部闸(G1–G4)都过的测量;同一组帧对上「修正 / 不修正」的逐对比值中位数(两条轨迹共用帧对 ⇒ LiDAR 误差抵消)。"""
import json
import os

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint/ruler3/'
SC = ['13f5', '6d18', '7353']
DT = ['0.35', '0.5', '0.75', '1.0']
TR = [('arkit', 'ARKit'), ('scall_ap0_swm4', '新 Δ−4 不修正'), ('scall_am16_swm4', '新 Δ−4 加计−16'),
      ('scnone_ap0_swp0', '旧 Δ0 不修正'), ('scnone_am16_swp0', '旧 Δ0 加计−16')]
GATES = ['G1_pairs', 'G2_between_rel_iqr', 'G3_within_rel_iqr', 'G4_alignment_minimum_at_0']
valid = {}
for sc in SC:
    print('== %s' % sc)
    for dt in DT:
        f = SP + 'out_%s_dt%s/lidar_ruler_report.json' % (sc, dt)
        if not os.path.exists(f):
            continue
        T = json.load(open(f))['trajectories']
        cells = []
        for n, lab in TR:
            if n not in T:
                continue
            e = T[n]['estimate']; g = e.get('gates', {})
            ok = all(g.get(x) for x in GATES)
            cells.append('%s %+.2f%%%s' % (lab, 100 * (e['k'] - 1), '' if ok else '(未过闸:' + ''.join(x[:2] for x in GATES if not g.get(x)) + ')'))
            if ok:
                valid.setdefault((sc, n), []).append(e['k'])
        # 同帧对的逐对比值:修正 / 不修正
        def per_pair(n):
            return {(p['t_a'], p['t_b']): 1 / p['scale_to_metric'] for p in T[n]['pairs'] if 'scale_to_metric' in p}
        rat = []
        for a, b in (('scall_am16_swm4', 'scall_ap0_swm4'), ('scnone_am16_swp0', 'scnone_ap0_swp0')):
            pa, pb = per_pair(a), per_pair(b)
            com = set(pa) & set(pb)
            rat.append(np.median([pa[k] / pb[k] for k in com]) if com else np.nan)
        print('  帧对间隔 %ss:%s | 同帧对 修正/不修正:新 %+.2f%% 旧 %+.2f%%' % (dt, ' | '.join(cells), 100 * (rat[0] - 1), 100 * (rat[1] - 1)))
print('\n只用过闸测量的均值(k−1,%):')
for sc in SC:
    print('  %s ' % sc + ' | '.join('%s %s' % (lab, ('%+.2f%%(%d 组)' % (100 * (np.mean(valid[(sc, n)]) - 1), len(valid[(sc, n)]))) if (sc, n) in valid else '无过闸') for n, lab in TR))
