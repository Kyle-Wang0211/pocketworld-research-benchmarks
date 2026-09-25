#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 位姿对陀螺的一致性(不依赖 ARKit 平移),跨度 H = 0.1 / 1 / 5 s。
先用 0.1 s 增量按 gyrofit.fit 的做法拟合 时间偏移 s、外参旋转 X、常值零偏 b(每条轨迹各自拟合);
再把陀螺按段内梯形逐段**复合**成姿态 R_g(t)(大转角时 ∫ω ≠ log ΔR,不能直接用向量积分),
比较 ΔR_pose = R_i^T R_j 与 X^T R_g(t_i+s)^T R_g(t_j+s) X,报残差角 RMS(°)。
ARKit 同一批帧作参照。用法:gyro_horizon.py <scene> <tag> [<tag> ...]"""
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
sys.path.insert(0, SP + '/wobble/tools')
import gyrofit  # noqa: E402
import preint_eval as PE  # noqa: E402
import wob  # noqa: E402
from rotcal import logm, expm  # noqa: E402

GRID = np.arange(-0.03, 0.0301, 0.0005)


def fit_sxb(G, t0, t1, th):
    f = gyrofit.fit(G, t0, t1, th, GRID)
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
    X = gyrofit.kabsch(Gi - b * dt[:, None], th)
    return s, X, b


class GyroAtt:
    """陀螺逐段复合姿态(IMU 系),段内梯形;任意时刻在所在段内按比例插值。"""

    def __init__(self, imu, b):
        self.t = imu['t']
        w = imu['w'] - b
        self.R = [np.eye(3)]
        for k in range(len(self.t) - 1):
            dt = self.t[k + 1] - self.t[k]
            self.R.append(self.R[-1] @ expm(0.5 * (w[k] + w[k + 1]) * dt))
        self.w = w

    def at(self, x):
        k = int(np.clip(np.searchsorted(self.t, x) - 1, 0, len(self.t) - 2))
        h = x - self.t[k]
        T = self.t[k + 1] - self.t[k]
        wm = self.w[k] + 0.5 * (self.w[k + 1] - self.w[k]) * h / T   # 段首到 x 的平均角速度(线性插值下)
        return self.R[k] @ expm(0.5 * (self.w[k] + (self.w[k] + (self.w[k + 1] - self.w[k]) * h / T)) * h)


def resid(t, R, s, X, att, H):
    e = []
    for i in range(len(t)):
        j = np.searchsorted(t, t[i] + H)
        if j >= len(t) or abs(t[j] - t[i] - H) > 0.06:
            continue
        dRg = att.at(t[i] + s).T @ att.at(t[j] + s)
        # 约定同 gyrofit:th(位姿增量) @ X ≈ 陀螺增量 ⇒ 位姿系 = X · IMU 系 · X^T
        dRp = R[i].T @ R[j]
        e.append(np.linalg.norm(logm((X @ dRg @ X.T).T @ dRp)))
    e = np.degrees(np.array(e))
    return float(np.sqrt(np.mean(e ** 2))), len(e)


def traj_stats(G, imu, t, R):
    keep = np.nonzero(np.diff(t) < 0.4)[0]
    th = np.array([logm(R[i].T @ R[i + 1]) for i in keep])
    s, X, b = fit_sxb(G, t[keep], t[keep + 1], th)
    att = GyroAtt(imu, b)
    return [resid(t, R, s, X, att, H) for H in (0.1, 1.0, 5.0)]


def run(sc, tag, G, imu):
    _, fin = PE.load_backend_full(PE.W + tag + '.backend.csv')
    ks = sorted(fin)
    t = np.array([fin[k][2] for k in ks]); R = np.array([fin[k][0] for k in ks])
    A = wob.load_arkit(sc); RA = wob.qmat(A['Q']) @ PE.D
    ia = {int(x): i for i, x in enumerate(A['tns'])}
    kk = [k for k in ks if k in ia]
    ta = np.array([k * 1e-9 for k in kk]); Ra = np.array([RA[ia[k]] for k in kk])
    return traj_stats(G, imu, t, R), traj_stats(G, imu, ta, Ra)


if __name__ == '__main__':
    sc = sys.argv[1]
    G = gyrofit.GyroInt(sc)
    imu = wob.load_imu(sc)
    for tag in sys.argv[2:]:
        a, b = run(sc, tag, G, imu)
        print('%-5s %-22s ' % (sc, tag) + ' | '.join('H=%.1fs 残差 %.4f°(ARKit 同帧 %.4f°)n %d' % (h, x[0], y[0], x[1])
                                                  for h, x, y in zip((0.1, 1.0, 5.0), a, b)))
