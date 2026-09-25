#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 混合臂评分(诊断,只读)。全旧 = 扫描里的 base(已证与 mixnone 逐位相同),全新 = okvis(= mixall)。
每个臂 × Δ × 场:后端定稿 ATE / 对 LiDAR / 同口径抖动;汇总:三场 ATE 和的曲线、最小值与所在 Δ、
平台均值(三场和最小的连续 3 档平均),以及「该臂把全旧→全新的 ATE 差距搬走了多少」。
用法:mix_eval.py"""
import json
import os
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
import preint_eval as PE  # noqa: E402
import rs_bins as RS  # noqa: E402

SC = ['13f5', '6d18', '7353']
DS = list(range(-13, 3))
ARMS = [('old', '全旧(8ebac9a)'), ('backend', '只换后端残差'), ('front', '只换前端 predict'),
        ('init', '只换初始化'), ('holdboth', '后端 OKVIS2+右端保持(诊断)'), ('holdgyro', '后端 仅陀螺右端保持(诊断)'),
        ('holdacc', '后端 仅加计右端保持(诊断)'), ('as16old', '全旧 + 加计时间戳 −16 ms(输入)'),
        ('as16new', '全新 + 加计时间戳 −16 ms(输入)'), ('as11old', '全旧 + 加计 −11 ms(总建模 16)'),
        ('as21new', '全新 + 加计 −21 ms(总建模 21)'), ('new', '全新(4e8dda2)')]


def tag(arm, sc, d):
    n = ('m%d' % -d) if d < 0 else ('p%d' % d)
    if arm == 'old':
        return '%s_base_nothr_sw%s' % (sc, n)
    if arm == 'new':
        return '%s_okvis_nothr_sw%s' % (sc, n)
    if arm in ('as11old', 'as21new'):
        return '%s_%s_sw%s' % (sc, 'base_as11' if arm == 'as11old' else 'okvis_as21', n)
    if arm.startswith('as16'):
        return '%s_%s_as16_sw%s' % (sc, 'base' if arm == 'as16old' else 'okvis', n)
    if arm.startswith('hold'):
        return '%s_%s_sw%s' % (sc, arm, n)
    return '%s_mix%s_sw%s' % (sc, arm, n)


def main():
    res = {}
    for arm, _ in ARMS:
        for d in DS:
            for sc in SC:
                t = tag(arm, sc, d)
                lg = PE.W + t + '.log'
                if not os.path.exists(lg) or '=== s3 runner' not in open(lg).read():
                    continue   # 没跑或还在跑
                r = PE.run(sc, t)['rows']['backend_final']
                j = RS.run(sc, t)['backend_final']
                res[(arm, d, sc)] = (r['ate_cm'], r['k_lidar'] - 1, j['rms'])
    json.dump({'%s|%d|%s' % k: v for k, v in res.items()}, open(SP + '/preint/stats/mix_eval.json', 'w'), indent=1)
    print('后端定稿 ATE(cm),三场,Δ = %s' % ' '.join('%+d' % d for d in DS))
    summ = {}
    for arm, lab in ARMS:
        for sc in SC:
            print('  %-18s %s  %s' % (lab, sc, ' '.join('%5.2f' % res[(arm, d, sc)][0] if (arm, d, sc) in res else '  —  ' for d in DS)))
        tot = np.array([sum(res[(arm, d, sc)][0] for sc in SC) if all((arm, d, sc) in res for sc in SC) else np.nan for d in DS])
        if np.all(np.isnan(tot)):
            continue
        k = int(np.nanargmin(tot))
        plat = np.nanmin([np.mean(tot[i:i + 3]) for i in range(len(DS) - 2)])
        own = [min(res[(arm, d, sc)][0] for d in DS if (arm, d, sc) in res) for sc in SC]
        jit = np.array([np.mean([res[(arm, d, sc)][2] for sc in SC]) if all((arm, d, sc) in res for sc in SC) else np.nan for d in DS])
        kl = np.array([np.sqrt(np.mean([res[(arm, d, sc)][1] ** 2 for sc in SC])) if all((arm, d, sc) in res for sc in SC) else np.nan for d in DS])
        summ[arm] = dict(tot_min=tot[k], d=DS[k], plat=plat, own=own, jit_min=np.nanmin(jit), jit_d=DS[int(np.nanargmin(jit))],
                         kl_min=100 * np.nanmin(kl), kl_d=DS[int(np.nanargmin(kl))])
        print('  %-18s 三场和 %s | 最小 %.2f @Δ=%+d 平台(3 档均)%.2f | 各场自身最优 %s | 抖动最小 %.4f° @%+d | 尺度 RMS 最小 %.2f%% @%+d' % (
            lab, ' '.join('%5.2f' % x for x in tot), tot[k], DS[k], plat, '/'.join('%.2f' % x for x in own),
            summ[arm]['jit_min'], summ[arm]['jit_d'], summ[arm]['kl_min'], summ[arm]['kl_d']))
    gap = summ['new']['plat'] - summ['old']['plat']
    print('全旧→全新 平台 ATE 和 差距 %+.2f cm;各臂(只换一处)占差距:' % gap)
    for arm, lab in ARMS[1:-1]:
        if arm not in summ:
            continue
        print('  %-18s %+.2f cm = %+.0f%%(三场和最小值 %+.2f cm)' % (
            lab, summ[arm]['plat'] - summ['old']['plat'], 100 * (summ[arm]['plat'] - summ['old']['plat']) / gap,
            summ[arm]['tot_min'] - summ['old']['tot_min']))


if __name__ == '__main__':
    main()
