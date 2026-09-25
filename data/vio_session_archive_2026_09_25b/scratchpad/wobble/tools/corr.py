#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分窗尺度误差(XR/ARKit,窗内 Sim3 与免对齐位移比,除以全局)与协变量的相关。
窗口 2 s 不重叠(相关的显著性按独立样本近似)+ 4 s 步长 0.5 s(画时间序列)。
"""
import json
import sys

import numpy as np

sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob  # noqa: E402

COV = ['gyro_mean', 'speed', 'lin_acc', 'acc_norm_std', 'fx_mean', 'fx_range_pct', 'fx_tv_pct', 'exp_ms', 'blur_px']


def table(sc, xr, win=2.0, step=2.0, extra=None):
    ark = wob.load_arkit(sc); imu = wob.load_imu(sc); intr = wob.load_intr(sc)
    J = wob.join(xr, ark)
    kg = wob.k_sim3(J['X'], J['Y'])
    kdg, _ = wob.disp_ratio(J['t'], J['X'], J['Y'], 0.5)
    rows = []
    for w in wob.windows(J, win, step, lag=0.5):
        c = wob.covariates(sc, w['t0'], w['t1'], ark, imu, intr)
        c['rot_over_speed'] = c['gyro_mean'] / max(c['speed'], 1e-3)
        r = dict(tc=w['tc'], e_sim3=w['k_sim3'] / kg - 1, e_disp=w['k_disp'] / kdg - 1, **c)
        if extra is not None:
            r.update(extra(w['t0'], w['t1']))
        rows.append(r)
    return rows, kg


def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return np.corrcoef(ra, rb)[0, 1]


if __name__ == '__main__':
    allr = []
    for sc in sys.argv[1:] or ['13f5', '6d18', '7353', 'fb5d']:
        rows, kg = table(sc, wob.load_xr_phone(sc))
        for r in rows:
            r['sc'] = sc
        allr += rows
        e = np.array([r['e_disp'] for r in rows])
        print('== %s  全局 k %.4f  2s 窗 %d 个  |误差| 中位 %.1f%%  最大 %.1f%%' % (
            sc, kg, len(rows), 100 * np.median(np.abs(e)), 100 * np.max(np.abs(e))))
        for c in COV + ['rot_over_speed']:
            x = np.array([r[c] for r in rows])
            f = np.isfinite(x) & np.isfinite(e)
            print('   %-15s  spearman(|e|) %+.2f   spearman(e) %+.2f' % (c, spearman(x[f], np.abs(e[f])), spearman(x[f], e[f])))
    json.dump(allr, open(wob.W + '/stats/corr_phone_2s.json', 'w'), indent=0)
    e = np.array([r['e_disp'] for r in allr])
    print('== 合并 %d 窗' % len(allr))
    for c in COV + ['rot_over_speed']:
        x = np.array([r[c] for r in allr])
        f = np.isfinite(x) & np.isfinite(e)
        print('   %-15s  spearman(|e|) %+.2f   spearman(e) %+.2f' % (c, spearman(x[f], np.abs(e[f])), spearman(x[f], e[f])))
