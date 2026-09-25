#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 诊断交叉核对:只用 IMU 自己(不用 ARKit、不用相机)量加计相对陀螺的延迟。
陀螺逐段复合姿态 R(t)(IMU 系,段内梯形)。在 2 s 窗内,重力在世界系恒定 ⇒ a_imu(t_k) ≈ R(t_k − d)^T g0 + 线加速度;
g0 每窗线性最小二乘求出,扫 d 取各窗残差和最小(线加速度当噪声)。d > 0 ⇒ 加计样本比陀螺晚。
用法:acc_delay_imu.py <scene> ..."""
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/wobble/tools')
import wob  # noqa: E402
from rotcal import expm  # noqa: E402


def attitude(t, w):
    R = [np.eye(3)]
    for k in range(len(t) - 1):
        R.append(R[-1] @ expm(0.5 * (w[k] + w[k + 1]) * (t[k + 1] - t[k])))
    return np.array(R)


def R_at(t, R, w, x):
    k = int(np.clip(np.searchsorted(t, x) - 1, 0, len(t) - 2))
    h = x - t[k]; T = t[k + 1] - t[k]
    wx = w[k] + (w[k + 1] - w[k]) * h / T
    return R[k] @ expm(0.5 * (w[k] + wx) * h)


def main(sc):
    imu = wob.load_imu(sc)
    t, w, a = imu['t'], imu['w'], imu['a']
    R = attitude(t, w)
    grid = np.arange(-0.025, 0.04001, 0.001)
    win = 2.0
    cost = np.zeros(len(grid))
    starts = np.arange(t[0] + 0.1, t[-1] - win - 0.1, win)
    for j, d in enumerate(grid):
        c = 0.0
        for s0 in starts:
            m = np.nonzero((t >= s0) & (t < s0 + win))[0]
            Rs = np.array([R_at(t, R, w, t[k] - d) for k in m])
            A = Rs.transpose(0, 2, 1).reshape(-1, 3)        # a ≈ R^T g0 ⇒ 堆叠成 (3n × 3)·g0
            y = a[m].reshape(-1)
            g0, *_ = np.linalg.lstsq(A, y, rcond=None)
            c += np.sum((A @ g0 - y) ** 2)
        cost[j] = c
    i = int(np.argmin(cost))
    if 0 < i < len(grid) - 1:
        y0, y1, y2 = cost[i - 1], cost[i], cost[i + 1]
        dd = grid[i] + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2) * (grid[1] - grid[0])
    else:
        dd = grid[i]
    rms = np.sqrt(cost / (len(starts) * 3 * win * 100))
    print('%s  只用 IMU:加计相对陀螺延迟 d = %+.1f ms(残差 RMS %.3f m/s²;d=0 时 %.3f)' % (
        sc, 1e3 * dd, rms[i], rms[int(np.argmin(np.abs(grid)))]))


if __name__ == '__main__':
    for sc in sys.argv[1:]:
        main(sc)
