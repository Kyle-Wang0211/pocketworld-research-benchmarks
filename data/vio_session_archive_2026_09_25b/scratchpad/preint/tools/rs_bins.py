#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 任务二:逐增量旋转残差 vs 角速度(只诊断)。
残差 = gyrofit.fit 在最优 s 下的 r_i − g·src_i(°),角速度 = |陀螺积分增量| / Δt(rad/s)。
按角速度分箱给 RMS 残差;同一批后端帧上的 ARKit 同口径对照。再给残差 = a + b·ω 的最小二乘。
用法:rs_bins.py <scene> <tag> [--json out]
"""
import json
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
sys.path.insert(0, SP + '/wobble/tools')
import gyrofit  # noqa: E402
import preint_eval as PE  # noqa: E402
import wob  # noqa: E402
from rotcal import logm  # noqa: E402

BINS = [0.0, 0.3, 0.6, 1.0, 1.5, 2.5, 10.0]


def fit_resid(G, t0, t1, th, grid):
    f = gyrofit.fit(G, t0, t1, th, grid)
    s = f['s_ms'] * 1e-3
    dt = t1 - t0
    Gi = G.F(t1 + s) - G.F(t0 + s)
    b = np.zeros(3)
    for _ in range(3):
        src = Gi - b * dt[:, None]
        X = gyrofit.kabsch(src, th)
        r = th @ X
        g = np.sum(r * src) / np.sum(src * src)
        b = np.sum((Gi - r / g) * dt[:, None], 0) / np.sum(dt ** 2)
    src = Gi - b * dt[:, None]
    X = gyrofit.kabsch(src, th)
    r = th @ X
    g = np.sum(r * src) / np.sum(src * src)
    res = np.degrees(np.linalg.norm(r - g * src, axis=1))
    w = np.linalg.norm(src, axis=1) / dt
    return f, res, w


def incr(est, key, gap):
    ts = sorted(est)
    t = np.array([est[k][2] if key == 'engine' else k * 1e-9 for k in ts])
    R = np.array([est[k][0] for k in ts])
    keep = np.nonzero(np.diff(t) < gap)[0]
    th = np.array([logm(R[i].T @ R[i + 1]) for i in keep])
    return t[keep], t[keep + 1], th


def table(res, w):
    out = []
    for a, b in zip(BINS[:-1], BINS[1:]):
        m = (w >= a) & (w < b)
        out.append([a, b, int(m.sum()), float(np.sqrt(np.mean(res[m] ** 2))) if m.sum() >= 3 else None])
    A = np.stack([np.ones_like(w), w], 1)
    coef, *_ = np.linalg.lstsq(A, res, rcond=None)
    rho = float(np.corrcoef(w, res)[0, 1])
    return dict(bins=out, a_deg=float(coef[0]), b_deg_per_rads=float(coef[1]), pearson=rho,
                rms=float(np.sqrt(np.mean(res ** 2))), med=float(np.median(res)),
                p90=float(np.percentile(res, 90)), n=int(len(res)))


def run(sc, tag, grid=np.arange(-0.03, 0.0301, 0.0005)):
    G = gyrofit.GyroInt(sc)
    first, final = PE.load_backend_full(PE.W + tag + '.backend.csv')
    A = wob.load_arkit(sc)
    RA = wob.qmat(A['Q']) @ PE.D
    ark_b = {int(t): (RA[i], A['P'][i], int(t) * 1e-9) for i, t in enumerate(A['tns']) if int(t) in first}
    out = {}
    for name, est, key in (('backend_final', final, 'engine'), ('backend_first', first, 'engine'),
                           ('arkit@backend', ark_b, 'pts')):
        f, res, w = fit_resid(G, *incr(est, key, 0.4), grid)
        out[name] = dict(fit=f, **table(res, w))
    return out


if __name__ == '__main__':
    sc, tag = sys.argv[1], sys.argv[2]
    r = run(sc, tag)
    for name, d in r.items():
        cells = '  '.join('[%.1f,%.1f) n%3d %s' % (a, b, n, '%.3f°' % v if v is not None else '  —  ') for a, b, n, v in d['bins'])
        print('%-5s %-20s %-14s RMS %.4f° 中位 %.4f° p90 %.4f°  拟合 残差≈%.4f°+%.4f°/(rad/s)·ω  r=%.2f | %s' % (
            sc, tag, name, d['rms'], d['med'], d['p90'], d['a_deg'], d['b_deg_per_rads'], d['pearson'], cells))
    if len(sys.argv) > 4 and sys.argv[3] == '--json':
        json.dump(r, open(sys.argv[4], 'w'), indent=1, ensure_ascii=False)
