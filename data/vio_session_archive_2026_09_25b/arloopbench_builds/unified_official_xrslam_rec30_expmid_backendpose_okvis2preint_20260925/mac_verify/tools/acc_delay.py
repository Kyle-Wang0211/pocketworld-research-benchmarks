#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 诊断:加计相对陀螺的时间延迟(与引擎无关;ARKit 只作参照)。
ARKit 位姿(PTS)→ 相机系角速度 ω_c(t)(相邻姿态差)与比力 f_c(t) = R_wc^T (a_w − g_w)(位置二阶差分,重力 y 向上)。
对候选延迟 d:陀螺 ω_imu(t_k) 与 ω_c(t_k − d)、加计 a_imu(t_k) 与 f_c(t_k − d) 各自做 Kabsch(自由外参旋转)+ 常值零偏,
取残差最小的 d_g、d_a;d_a − d_g > 0 ⇒ 加计样本比陀螺样本晚。IMU 原始样本,不做任何积分。
用法:acc_delay.py <scene> ..."""
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/wobble/tools')
import wob  # noqa: E402
from rotcal import logm  # noqa: E402

D = np.diag([1.0, -1.0, -1.0])


def smooth(x, n):
    k = np.ones(n) / n
    return np.stack([np.convolve(x[:, c], k, mode='same') for c in range(x.shape[1])], 1)


def kabsch_fit(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    U, S, Vt = np.linalg.svd((src - ms).T @ (dst - md))
    Dd = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
    R = Vt.T @ Dd @ U.T
    r = dst - md - (src - ms) @ R.T
    return float(np.sqrt(np.mean(np.sum(r ** 2, 1))))


def main(sc):
    A = np.loadtxt(wob.rdir(sc) + '/arkit_poses.tum')
    good = np.abs(A[:, 1:4]).sum(1) > 0
    A = A[good]
    t = A[:, 0]
    P = A[:, 1:4]
    R = wob.qmat(A[:, 4:8]) @ D
    # 相机系角速度:中心差分
    wc = np.array([logm(R[i - 1].T @ R[i + 1]) / (t[i + 1] - t[i - 1]) for i in range(1, len(t) - 1)])
    tw = t[1:-1]
    # 世界系加速度:平滑后二阶差分(ARKit 60 Hz 位置抖动大 ⇒ 5 点平滑两次)
    Ps = smooth(smooth(P, 5), 5)
    v = np.gradient(Ps, t, axis=0)
    a = np.gradient(smooth(v, 5), t, axis=0)
    g = np.array([0.0, -9.81, 0.0])
    fc = np.einsum('nji,nj->ni', R, a - g)
    imu = wob.load_imu(sc)
    ti, wi, ai = imu['t'], imu['w'], imu['a']
    m = (ti > t[20]) & (ti < t[-20])
    ti, wi, ai = ti[m], wi[m], ai[m]
    grid = np.arange(-0.025, 0.02501, 0.0005)

    def interp(tq, ts, X):
        return np.stack([np.interp(tq, ts, X[:, c]) for c in range(3)], 1)

    import os
    mode = os.environ.get('ACC_MODE', 'full')
    if mode == 'gravity':      # 只用重力方向随姿态的变化,不用 ARKit 位置、不平滑
        fc = np.einsum('nji,nj->ni', R, np.tile(-g, (len(t), 1)))
    elif mode == 'light':      # 平滑减半:位置 3 点一次、速度 3 点
        Ps2 = smooth(P, 3); v2 = np.gradient(Ps2, t, axis=0); a2 = np.gradient(smooth(v2, 3), t, axis=0)
        fc = np.einsum('nji,nj->ni', R, a2 - g)
    rg = [kabsch_fit(interp(ti - d, tw, wc), wi) for d in grid]
    ra = [kabsch_fit(interp(ti - d, t, fc), ai) for d in grid]
    dg = grid[int(np.argmin(rg))]; da = grid[int(np.argmin(ra))]

    def para(r, i):   # 抛物线细化
        if 0 < i < len(r) - 1:
            y0, y1, y2 = r[i - 1], r[i], r[i + 1]
            return grid[i] + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) * (grid[1] - grid[0])
        return grid[i]
    dgp = para(rg, int(np.argmin(rg))); dap = para(ra, int(np.argmin(ra)))
    print('[%s] ' % mode + '%s  陀螺对 ARKit 角速度:最优 d_g %+.2f ms(残差 %.4f rad/s)| 加计对 ARKit 比力:最优 d_a %+.2f ms(残差 %.3f m/s²)| d_a − d_g = %+.2f ms' % (
        sc, 1e3 * dgp, min(rg), 1e3 * dap, min(ra), 1e3 * (dap - dgp)))


if __name__ == '__main__':
    for sc in sys.argv[1:]:
        main(sc)
