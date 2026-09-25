#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 与引擎无关的物理检验:只用加计(双重积分)给 ARKit 轨迹定米制尺度 s,扫加计延迟 d。
模型(IMU 系 b,ARKit 世界 w,y 向上,g_w = (0, −9.81, 0)):
  f_meas(t_k) = R_wb(t_k − d)^T (a_w(t_k − d) − g_w) + b_a        (加计样本比陀螺 / 姿态晚 d)
  ⇒ 在每个 1 s 窗 [t0, t0+T] 的检查点 t_j:  s·(p(t_j) − p(t0)) = v0·(t_j − t0) + ∬(R_wb(τ) f(τ + d) + g_w) − ∬R_wb(τ)·b_a
  未知量:全局 s、全局 b_a(3)、每窗 v0(3),线性最小二乘。p = IMU 位置 = ARKit 相机中心 + R_wc·t_ci。
外参用 ARKit 隐含值(wobble/stats/extrinsic_from_arkit.json;只作诊断参照)。旋转用 ARKit 姿态 slerp。
输出 s(d)、残差(d);ARKit 自身尺度误差的加计估计 = 1/s − 1,可与 LiDAR 米尺对同一条 ARKit 轨迹的 k 直接比。
用法:imu_scale.py <scene> ..."""
import json
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/wobble/tools')
import wob  # noqa: E402
from rotcal import logm, expm  # noqa: E402

D = np.diag([1.0, -1.0, -1.0])
G_W = np.array([0.0, -9.81, 0.0])


def load(sc):
    A = np.loadtxt(wob.rdir(sc) + '/arkit_poses.tum')
    A = A[np.abs(A[:, 1:4]).sum(1) > 0]
    t = A[:, 0]
    Rwc = wob.qmat(A[:, 4:8]) @ D                 # ARKit 相机 → OpenCV 轴
    E = json.load(open(SP + '/wobble/stats/extrinsic_from_arkit.json'))
    Rbc = wob.qmat(np.array([E['q_bc']]))[0]
    pbc = np.array(E['p_bc'])
    t_ci = -Rbc.T @ pbc                            # IMU 原点在相机系的坐标
    Rwb = Rwc @ Rbc.T
    P = A[:, 1:4] + np.einsum('nij,j->ni', Rwc, t_ci)
    imu = wob.load_imu(sc)
    return t, Rwb, P, imu


def slerp_R(t, R, x):
    i = int(np.clip(np.searchsorted(t, x) - 1, 0, len(t) - 2))
    a = (x - t[i]) / (t[i + 1] - t[i])
    return R[i] @ expm(a * logm(R[i].T @ R[i + 1]))


_CACHE = {}


def fine_R(t, Rwb):
    key = id(Rwb)
    if key not in _CACHE:
        tg = np.arange(t[0], t[-1], 0.001)
        _CACHE[key] = (tg, np.array([slerp_R(t, Rwb, x) for x in tg]))
    return _CACHE[key]


def solve(t, Rwb, P, imu, d, T=1.0, step=0.5, chk=3):
    ti, fa = imu['t'], imu['a']
    TG, RG = fine_R(t, Rwb)
    fx = lambda x: np.stack([np.interp(x, ti, fa[:, c]) for c in range(3)], 1)  # noqa: E731
    starts = np.arange(t[5], t[-5] - T, step)
    rows_A, rows_y = [], []
    nwin = len(starts)
    ncol = 1 + 3 + 3 * nwin
    for w, s0 in enumerate(starts):
        i0 = int(np.searchsorted(t, s0))
        idx = [i0 + k for k in range(chk, 10 ** 6, chk) if i0 + k < len(t) and t[i0 + k] - t[i0] <= T]
        if len(idx) < 3:
            continue
        # 细网格 1 ms 上积分:τ ∈ [t0, t_end]
        g0 = int(np.searchsorted(TG, t[i0])); g1 = int(np.searchsorted(TG, t[idx[-1]]))
        tg = TG[g0:g1 + 1]; Rg = RG[g0:g1 + 1]
        acc = np.einsum('nij,nj->ni', Rg, fx(tg + d)) + G_W        # 世界系加速度
        h = np.diff(tg)
        vel = np.vstack([np.zeros(3), np.cumsum(0.5 * (acc[1:] + acc[:-1]) * h[:, None], 0)])
        pos = np.vstack([np.zeros(3), np.cumsum(0.5 * (vel[1:] + vel[:-1]) * h[:, None], 0)])
        # 零偏项:∬ R_wb(τ) dτ dτ(3×3)
        Rv = np.concatenate([np.zeros((1, 3, 3)), np.cumsum(0.5 * (Rg[1:] + Rg[:-1]) * h[:, None, None], 0)])
        Rp = np.concatenate([np.zeros((1, 3, 3)), np.cumsum(0.5 * (Rv[1:] + Rv[:-1]) * h[:, None, None], 0)])
        for j in idx:
            k = min(int(np.searchsorted(tg, t[j])), len(tg) - 1)
            dt = tg[k] - tg[0]
            for c in range(3):
                row = np.zeros(ncol)
                row[0] = P[j, c] - P[i0, c]            # × s
                row[1:4] = Rp[k][c, :]                   # + ∬R·b_a
                row[4 + 3 * w + c] = -dt                 # − v0·dt
                rows_A.append(row)
                rows_y.append(pos[k, c])
    A = np.array(rows_A); y = np.array(rows_y)
    keep = np.nonzero(np.abs(A).sum(0) > 0)[0]
    x, *_ = np.linalg.lstsq(A[:, keep], y, rcond=None)
    res = A[:, keep] @ x - y
    xs = np.zeros(ncol); xs[keep] = x
    return xs[0], xs[1:4], float(np.sqrt(np.mean(res ** 2)))


def main(sc):
    t, Rwb, P, imu = load(sc)
    fn = np.linalg.norm(imu['a'], axis=1)
    out = []
    for d in np.arange(-0.010, 0.0401, 0.002):
        s, b, r = solve(t, Rwb, P, imu, d)
        out.append((d, s, b, r))
    ds = np.array([o[0] for o in out]); rr = np.array([o[3] for o in out])
    i = int(np.argmin(rr))
    if 0 < i < len(ds) - 1:
        y0, y1, y2 = rr[i - 1], rr[i], rr[i + 1]
        dopt = ds[i] + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) * (ds[1] - ds[0])
    else:
        dopt = ds[i]
    s_opt = np.interp(dopt, ds, [o[1] for o in out])
    s0 = [o[1] for o in out if abs(o[0]) < 1e-9][0]
    print('%s  |f| 中位 %.4f m/s²;残差最小 d = %+.1f ms' % (sc, np.median(fn), 1e3 * dopt))
    for d, s, b, r in out:
        if abs(round(1e3 * d) % 4) < 1e-9 or abs(d - dopt) < 0.0011:
            print('   d %+5.0f ms  s %.4f ⇒ ARKit 尺度(加计估) %+.2f%%  残差 %.4f m  b_a %s' % (1e3 * d, s, 100 * (1 / s - 1), r, np.round(b, 3)))
    print('   ⇒ d=0:ARKit 尺度(加计估) %+.2f%%;d=最优 %+.1f ms:%+.2f%%;差 %+.2f pp' % (
        100 * (1 / s0 - 1), 1e3 * dopt, 100 * (1 / s_opt - 1), 100 * (1 / s_opt - 1 / s0)))
    return dict(scene=sc, d_opt_ms=1e3 * dopt, arkit_k_imu_d0=1 / s0, arkit_k_imu_dopt=1 / s_opt,
                curve=[(1e3 * d, s, r) for d, s, b, r in out])


if __name__ == '__main__':
    res = [main(sc) for sc in sys.argv[1:]]
    json.dump(res, open(SP + '/preint/stats/imu_scale.json', 'w'), indent=1)
