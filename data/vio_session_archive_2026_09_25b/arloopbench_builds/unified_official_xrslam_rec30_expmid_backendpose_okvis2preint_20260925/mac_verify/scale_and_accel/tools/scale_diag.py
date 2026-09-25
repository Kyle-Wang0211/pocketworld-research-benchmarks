#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 加计修正后尺度缩小的诊断(只读):
① 加计平移量扫描(新引擎 Δ=−4):后端定稿 对 ARKit k、链式 LiDAR、ATE、5 s 分段;初始化尺度 / 零偏(诊断日志);
   后端 ba 均值与稳定性(出口 v/bg/ba);前 5 s 与其余段的分段 k(看尺度是否在初始化时定下)。
② 旧引擎 Δ=0 加计 0 / −16 同上。用法:scale_diag.py"""
import csv
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
import eval3  # noqa: E402
import preint_eval as PE  # noqa: E402
from trackdiff import load  # noqa: E402

SC = ['13f5', '6d18', '7353']


def ba_stats(tag):
    rows = [r for r in csv.DictReader(open(PE.W + tag + '.backend.csv')) if r['kind'] in ('2', '3') and int(r['t_ns']) > 0]
    t = np.array([float(r['engine_t']) for r in rows]); o = np.argsort(t)
    ba = np.array([[float(r['ba' + c]) for c in 'xyz'] for r in rows])[o]
    bg = np.array([[float(r['bg' + c]) for c in 'xyz'] for r in rows])[o]
    return ba, bg


def seg_first(sc, tag):
    rec = PE.REC[sc]
    frame_ts = [int(l.split(',')[0]) for l in open(rec + '/camera_index.csv').read().split('\n')[1:] if l]
    ark, _ = eval3.LR.arkit_poses(rec, rec + '/arkit_poses.tum', frame_ts)
    _, fin = PE.load_backend_full(PE.W + tag + '.backend.csv')
    m = eval3.metrics({k: (v[0], v[1]) for k, v in fin.items()}, ark, 10)
    return m['seg5'], m['k']


def row(sc, tag, lab):
    p = PE.run(sc, tag)['rows']['backend_final']
    ft, sw, ini = load(tag)
    ba, bg = ba_stats(tag)
    seg, k = seg_first(sc, tag)
    s5 = ' '.join('%+.1f' % x[2] for x in seg)
    print('  %-22s k_ARKit %+.2f%% k_LiDAR %+.2f%% ATE %.2f | 初始化尺度 %.5f bg0 %s | ba 定稿均值 %s |ba| %.3f 末值 %s | 5 s 段相对全场 %s' % (
        lab, 100 * (p['k_ark'] - 1), 100 * (p['k_lidar'] - 1), p['ate_cm'], ini['scale'], np.round(ini['bg'], 4),
        np.round(ba.mean(0), 3), np.linalg.norm(ba.mean(0)), np.round(ba[-1], 3), s5))
    return dict(k=p['k_ark'], init=ini['scale'], ba=ba.mean(0))


def main():
    tag = lambda sc, mix, a, d: '%s_sc%s_a%s_sw%s' % (sc, mix, ('m%d' % -a) if a < 0 else ('p%d' % a), ('m%d' % -d) if d < 0 else ('p%d' % d))  # noqa: E731
    out = {}
    for sc in SC:
        print('== %s  新引擎 Δ=−4,加计时间戳平移扫描' % sc)
        for a in (0, -4, -8, -12, -16, -20, -24):
            out[(sc, 'all', a)] = row(sc, tag(sc, 'all', a, -4), '新 加计平移 %+d ms' % a)
        print('== %s  旧引擎 Δ=0' % sc)
        for a in (0, -16):
            out[(sc, 'none', a)] = row(sc, tag(sc, 'none', a, 0), '旧 加计平移 %+d ms' % a)
    print('\n初始化尺度随加计平移的相对变化 vs 全场 k_ARKit 的相对变化(新引擎,相对平移 0):')
    for sc in SC:
        b = out[(sc, 'all', 0)]
        print('  %s ' % sc + ' | '.join('%+d ms: 初始化 %+.2f%% 全场 %+.2f%%' % (
            a, 100 * (out[(sc, 'all', a)]['init'] / b['init'] - 1), 100 * (out[(sc, 'all', a)]['k'] / b['k'] - 1))
            for a in (-8, -16, -24)))


if __name__ == '__main__':
    main()
