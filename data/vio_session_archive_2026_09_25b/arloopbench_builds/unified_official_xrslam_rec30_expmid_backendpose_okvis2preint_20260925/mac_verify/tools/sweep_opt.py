#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] td 扫描的最优点分析(只读 stats/sweep.json)。
判据:ATE(越小越好)、对 LiDAR 尺度 |k−1|(越小越好)、同口径旋转抖动(后端;越小越好)。
每个引擎 × 位姿:① 各场原始 argmin;② 各场 3 点平滑后 argmin;③ 三场共同 Δ(ATE 求和 / 尺度 RMS / 抖动均值)。
噪声底:同一曲线相邻 1 ms 两点之差的中位数(单线程逐位可复现,所以这是「对输入的混沌敏感度」,不是运行噪声)。"""
import json

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint/stats/'
R = json.load(open(SP + 'sweep.json'))
SC = ['13f5', '6d18', '7353']
DS = sorted({r['delta_ms'] for r in R})
ENG = [('base', '改前 8ebac9a'), ('okvis', '改后 bdf9080')]


def curve(e, pose, sc, key):
    d = {r['delta_ms']: r[key] for r in R if r['engine'] == e and r['pose'] == pose and r['scene'] == sc}
    return np.array([d[x] for x in DS], dtype=float)


def smooth(y):
    z = y.copy()
    z[1:-1] = (y[:-2] + y[1:-1] + y[2:]) / 3
    return z


out = []
P = out.append
P('Δ 范围 %d…%+d ms(t_feed = PTS + 曝光/2 + 3 ms + Δ)' % (DS[0], DS[-1]))
for pose, jkey in (('backend_final', 'same_rms_deg'), ('front', 'jitter_deg')):
    P('')
    P('==== %s ====' % ('后端定稿' if pose == 'backend_final' else '前端(回放按时间戳投递)'))
    crit = [('ate_cm', 'ATE cm', lambda v: v), ('k_lidar_pct', '对 LiDAR |k−1| %', np.abs), (jkey, '旋转抖动 °', lambda v: v)]
    for key, lab, f in crit:
        P('-- 判据 %s' % lab)
        best = {}
        for e, el in ENG:
            cells, vals, noise = [], [], []
            for sc in SC:
                y = f(curve(e, pose, sc, key))
                i = int(np.argmin(y))
                s = smooth(y)
                j = int(np.argmin(s[1:-1])) + 1
                edge = ' (边界)' if i in (0, len(DS) - 1) else ''
                cells.append('%s: 原始 Δ=%+d → %.3f%s;平滑 Δ=%+d → %.3f' % (sc, DS[i], y[i], edge, DS[j], s[j]))
                vals.append(y[i])
                noise.append(np.median(np.abs(np.diff(y))))
            if key == 'ate_cm':
                agg = sum(f(curve(e, pose, sc, key)) for sc in SC)
                aggl = 'ATE 三场和'
            elif key == 'k_lidar_pct':
                agg = np.sqrt(sum(curve(e, pose, sc, key) ** 2 for sc in SC) / 3)
                aggl = '尺度 RMS %'
            else:
                agg = sum(curve(e, pose, sc, key) for sc in SC) / 3
                aggl = '抖动三场均值'
            k = int(np.argmin(agg))
            best[e] = (vals, agg[k], DS[k])
            P('  %s | %s' % (el, ' | '.join(cells)))
            P('  %s | 三场共同 Δ=%+d:%s %.3f;相邻 1 ms 跳动中位 %s' % (
                el, DS[k], aggl, agg[k], ' / '.join('%.3f' % n for n in noise)))
        vb, ab, db = best['base']
        vo, ao, do = best['okvis']
        P('  ⇒ 各场自身最优:改后 − 改前 = %s;共同最优:改后 %.3f(Δ=%+d)vs 改前 %.3f(Δ=%+d)' % (
            ' / '.join('%+.3f' % (o - b) for o, b in zip(vo, vb)), ao, do, ab, db))
    # 共同最优点上的整行
P('')
P('==== 各引擎在「ATE 三场和」共同最优 Δ 上的全部指标(后端定稿)====')
for e, el in ENG:
    agg = sum(curve(e, 'backend_final', sc, 'ate_cm') for sc in SC)
    d = DS[int(np.argmin(agg))]
    for sc in SC:
        r = [x for x in R if x['engine'] == e and x['pose'] == 'backend_final' and x['scene'] == sc and x['delta_ms'] == d][0]
        P('  %s Δ=%+d %s | 对 ARKit %+.2f%% 对 LiDAR %+.2f%% | ATE %.2f cm | 5 s %+.1f…%+.1f (sd %.1f) | 2 s sd %.1f%% | 抖动 %.4f°(ARKit 同帧 %.4f°)| 陀螺偏移 %+.1f ms' % (
            el, d, sc, r['k_ark_pct'], r['k_lidar_pct'], r['ate_cm'], r['seg5_min'], r['seg5_max'], r['seg5_sd'], r['win2_sd'],
            r['same_rms_deg'], r['ark_same_rms_deg'], r['s_engine_ms']))
txt = '\n'.join(out)
open(SP + 'sweep_opt.txt', 'w').write(txt)
print(txt)
