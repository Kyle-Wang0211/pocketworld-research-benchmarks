#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轨迹相邻位姿的相对旋转 vs 陀螺积分(分段线性 ⇒ 梯形,无半采样偏差)。
拟合:θ_i ≈ g · X · (∫_{t0+s}^{t1+s} ω − b·Δt),X 为自由旋转(Kabsch),扫 s。
s 的口径:轨迹以录制帧 t_ns 键控;s>0 ⇒ 该位姿对应 IMU 时钟 t_ns+s。
另给抖动:最优 s 下残差的 RMS(°/增量)。
轨迹:ARKit、API 输出(cam.tum)、后端 latest(每次后端求解后的最新帧)、后端 kf_final(关键帧边缘化前的最终状态)。
"""
import json
import sys

import numpy as np

sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob  # noqa: E402
from rotcal import logm  # noqa: E402

D = np.diag([1.0, -1.0, -1.0])


class GyroInt:
    def __init__(self, sc):
        imu = wob.load_imu(sc)
        self.t = imu['t']; self.w = imu['w']
        dt = np.diff(self.t)
        self.cum = np.vstack([np.zeros(3), np.cumsum(0.5 * (self.w[1:] + self.w[:-1]) * dt[:, None], 0)])

    def F(self, x):
        i = np.clip(np.searchsorted(self.t, x) - 1, 0, len(self.t) - 2)
        h = x - self.t[i]; T = self.t[i + 1] - self.t[i]
        w0, w1 = self.w[i], self.w[i + 1]
        return self.cum[i] + w0 * h[:, None] + 0.5 * (w1 - w0) * (h ** 2 / T)[:, None]


def kabsch(src, dst):
    U, S, Vt = np.linalg.svd(src.T @ dst)
    Dd = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
    return Vt.T @ Dd @ U.T


def fit(G, t0, t1, th, grid):
    best = None
    dt = t1 - t0
    for s in grid:
        Gi = G.F(t1 + s) - G.F(t0 + s)
        b = np.zeros(3)
        for _ in range(3):
            src = Gi - b * dt[:, None]
            X = kabsch(src, th)
            r = th @ X  # 轨迹增量转到 IMU 系:X^T θ
            g = np.sum(r * src) / np.sum(src * src)
            b = np.sum((Gi - r / g) * dt[:, None], 0) / np.sum(dt ** 2)
        src = Gi - b * dt[:, None]
        X = kabsch(src, th); r = th @ X; g = np.sum(r * src) / np.sum(src * src)
        c = np.mean(np.sum((r - g * src) ** 2, 1))
        if best is None or c < best[0]:
            best = (c, s, g, X)
    c, s, g, X = best
    return dict(s_ms=1e3 * s, g=g, jitter_deg=float(np.degrees(np.sqrt(c))), n=len(t0))


def increments(tns, Rs, max_gap=0.2):
    t = tns * 1e-9
    o = np.argsort(t); t = t[o]; Rs = Rs[o]
    keep = np.nonzero(np.diff(t) < max_gap)[0]
    th = np.array([logm(Rs[i].T @ Rs[i + 1]) for i in keep])
    return t[keep], t[keep + 1], th


def backend_traj(tag, ev_name):
    mp = {}
    for ln in open(wob.W + '/runs/%s.map' % tag):
        a, b = ln.split(); mp[a] = int(b)
    tns, R, P = [], [], []
    seen = set()
    for ln in open(wob.W + '/runs/%s.jsonl' % tag):
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if d['ev'] != ev_name:
            continue
        k = '%.9f' % d['t']
        if k not in mp or k in seen:
            continue
        seen.add(k)
        tns.append(mp[k]); R.append(wob.qmat(np.array([d['q']]))[0]); P.append(d['p'])
    return np.array(tns, dtype=np.int64), np.array(R), np.array(P)


def run(sc, tag, grid=np.arange(-0.03, 0.0301, 0.0005)):
    G = GyroInt(sc)
    out = {}
    ark = wob.load_arkit(sc)
    out['arkit'] = fit(G, *increments(ark['tns'], wob.qmat(ark['Q']) @ D), grid)
    xr = wob.load_xr_mac(tag)
    out['api_out'] = fit(G, *increments(xr['tns'], wob.qmat(xr['Q'])), grid)
    # API 输出降采样到后端帧(10 Hz),与后端同口径比较
    tl, Rl, _ = backend_traj(tag, 'latest')
    sel = np.isin(xr['tns'], tl)
    out['api_out@10Hz'] = fit(G, *increments(xr['tns'][sel], wob.qmat(xr['Q'][sel]), 0.4), grid)
    out['backend_latest'] = fit(G, *increments(tl, Rl, 0.4), grid)
    tk, Rk, _ = backend_traj(tag, 'kf_final')
    out['backend_kf_final'] = fit(G, *increments(tk, Rk, 0.4), grid)
    return out


if __name__ == '__main__':
    for a in sys.argv[1:] or ['13f5:13f5_log_r1', '6d18:6d18_log_r1', '7353:7353_log_r1', 'fb5d:fb5d_log_r1']:
        sc, tag = a.split(':')
        r = run(sc, tag)
        for k, v in r.items():
            print('%-5s %-18s s %+6.2f ms  幅度比 g %.4f  抖动 %.3f°/增量  n %d' % (sc, k, v['s_ms'], v['g'], v['jitter_deg'], v['n']))
