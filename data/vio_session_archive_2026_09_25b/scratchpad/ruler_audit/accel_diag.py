#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计用:纯加计尺子(preint/tools/imu_scale.py)的敏感度扫描。只读,不改原脚本。
模型与 imu_scale.solve 逐项相同(全局 s、全局 b_a、每窗 v0,1 ms 细网格梯形双重积分),额外开关:
  bias   : 'global'(原版) | 'none' | 'block5'(每 5 s 一组 b_a)
  dg     : True ⇒ 再解一个世界系常值加速度 δg(3),吸收重力模长/加计刻度在重力上的误差
  gmag   : 重力模长(原版 9.81)
  lever  : False ⇒ 不做相机→IMU 杠杆臂换算(直接用相机中心)
  noise  : 给 ARKit 位置加白噪声(米),SIMEX 看「自变量有噪声」的衰减偏差
  tmask  : 只用窗起点落在 [a,b) 的窗(分段对比用)
输出 k_imu = 1/s(与 imu_scale 的「ARKit 尺度(加计估)」同口径:k>1 ⇒ ARKit 轨迹比真实大)。"""
import json
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/wobble/tools')
sys.dont_write_bytecode = True
import wob  # noqa: E402
from rotcal import logm, expm  # noqa: E402

D = np.diag([1.0, -1.0, -1.0])


def load(sc, lever=True):
    A = np.loadtxt(wob.rdir(sc) + '/arkit_poses.tum')
    A = A[np.abs(A[:, 1:4]).sum(1) > 0]
    t = A[:, 0]
    Rwc = wob.qmat(A[:, 4:8]) @ D
    E = json.load(open(SP + '/wobble/stats/extrinsic_from_arkit.json'))
    Rbc = wob.qmat(np.array([E['q_bc']]))[0]
    pbc = np.array(E['p_bc'])
    t_ci = -Rbc.T @ pbc
    Rwb = Rwc @ Rbc.T
    P = A[:, 1:4] + (np.einsum('nij,j->ni', Rwc, t_ci) if lever else 0.0)
    imu = wob.load_imu(sc)
    return t, Rwb, P, imu


def slerp_R(t, R, x):
    i = int(np.clip(np.searchsorted(t, x) - 1, 0, len(t) - 2))
    a = (x - t[i]) / (t[i + 1] - t[i])
    return R[i] @ expm(a * logm(R[i].T @ R[i + 1]))


_C = {}


def fine_R(sc, t, Rwb):
    if sc not in _C:
        tg = np.arange(t[0], t[-1], 0.001)
        _C[sc] = (tg, np.array([slerp_R(t, Rwb, x) for x in tg]))
    return _C[sc]


def solve(sc, t, Rwb, P, imu, d, T=1.0, step=0.5, chk=3, bias='global', dg=False, gmag=9.81,
          tmask=None, rng=None, noise=0.0, acc_scale=1.0):
    ti, fa = imu['t'], imu['a'] * acc_scale
    TG, RG = fine_R(sc, t, Rwb)
    Pn = P + (rng.normal(0, noise, P.shape) if noise > 0 else 0.0)
    G_W = np.array([0.0, -gmag, 0.0])
    fx = lambda x: np.stack([np.interp(x, ti, fa[:, c]) for c in range(3)], 1)  # noqa: E731
    starts = np.arange(t[5], t[-5] - T, step)
    if tmask is not None:
        starts = starts[(starts >= tmask[0]) & (starts < tmask[1])]
    nwin = len(starts)
    nb = {'global': 3, 'none': 0, 'block5': 3 * (int((t[-1] - t[0]) // 5) + 1)}[bias]
    ncol = 1 + nb + (3 if dg else 0) + 3 * nwin
    rows_A, rows_y, wid = [], [], []
    for w, s0 in enumerate(starts):
        i0 = int(np.searchsorted(t, s0))
        idx = [i0 + k for k in range(chk, 10 ** 6, chk) if i0 + k < len(t) and t[i0 + k] - t[i0] <= T]
        if len(idx) < 3:
            continue
        g0 = int(np.searchsorted(TG, t[i0])); g1 = int(np.searchsorted(TG, t[idx[-1]]))
        tg = TG[g0:g1 + 1]; Rg = RG[g0:g1 + 1]
        acc = np.einsum('nij,nj->ni', Rg, fx(tg + d)) + G_W
        h = np.diff(tg)
        vel = np.vstack([np.zeros(3), np.cumsum(0.5 * (acc[1:] + acc[:-1]) * h[:, None], 0)])
        pos = np.vstack([np.zeros(3), np.cumsum(0.5 * (vel[1:] + vel[:-1]) * h[:, None], 0)])
        Rv = np.concatenate([np.zeros((1, 3, 3)), np.cumsum(0.5 * (Rg[1:] + Rg[:-1]) * h[:, None, None], 0)])
        Rp = np.concatenate([np.zeros((1, 3, 3)), np.cumsum(0.5 * (Rv[1:] + Rv[:-1]) * h[:, None, None], 0)])
        blk = int((s0 - t[0]) // 5)
        for j in idx:
            k = min(int(np.searchsorted(tg, t[j])), len(tg) - 1)
            dt = tg[k] - tg[0]
            for c in range(3):
                row = np.zeros(ncol)
                row[0] = Pn[j, c] - Pn[i0, c]
                if bias == 'global':
                    row[1:4] = Rp[k][c, :]
                elif bias == 'block5':
                    row[1 + 3 * blk:1 + 3 * blk + 3] = Rp[k][c, :]
                o = 1 + nb
                if dg:
                    row[o + c] = -0.5 * dt * dt
                    o += 3
                row[o + 3 * w + c] = -dt
                rows_A.append(row)
                rows_y.append(pos[k, c])
                wid.append(w)
    A = np.array(rows_A); y = np.array(rows_y)
    keep = np.nonzero(np.abs(A).sum(0) > 0)[0]
    x, *_ = np.linalg.lstsq(A[:, keep], y, rcond=None)
    xs = np.zeros(ncol); xs[keep] = x
    res = A[:, keep] @ x - y
    out = {'s': xs[0], 'k': 1.0 / xs[0], 'rms': float(np.sqrt(np.mean(res ** 2))), 'nwin': nwin}
    if bias == 'global':
        out['b_a'] = xs[1:4].tolist()
    if dg:
        out['dg'] = xs[1 + nb:1 + nb + 3].tolist()
    return out


def boot(sc, t, Rwb, P, imu, d, nb=200, block=5.0, seed=1):
    """块 bootstrap:把 5 s 时间块整体重抽(保留块内相关),每次重解全局 s。"""
    rng = np.random.default_rng(seed)
    t0, t1 = t[5], t[-5] - 1.0
    edges = np.arange(t0, t1, block)
    # 先按块解出每块的法方程贡献,再重抽拼
    blocks = []
    for a in edges:
        blocks.append(normal_eq(sc, t, Rwb, P, imu, d, (a, a + block)))
    ks = []
    for _ in range(nb):
        pick = rng.integers(0, len(blocks), len(blocks))
        ks.append(combine([blocks[i] for i in pick]))
    return np.percentile(ks, [2.5, 50, 97.5]), np.std(ks)


def normal_eq(sc, t, Rwb, P, imu, d, tm):
    """一段时间内的窗:返回 (A_sb, y) 已消去每窗 v0 的 [s, b_a] 列 —— 便于块 bootstrap 拼接。"""
    ti, fa = imu['t'], imu['a']
    TG, RG = fine_R(sc, t, Rwb)
    G_W = np.array([0.0, -9.81, 0.0])
    fx = lambda x: np.stack([np.interp(x, ti, fa[:, c]) for c in range(3)], 1)  # noqa: E731
    starts = np.arange(t[5], t[-5] - 1.0, 0.5)
    starts = starts[(starts >= tm[0]) & (starts < tm[1])]
    As, ys = [], []
    for s0 in starts:
        i0 = int(np.searchsorted(t, s0))
        idx = [i0 + k for k in range(3, 10 ** 6, 3) if i0 + k < len(t) and t[i0 + k] - t[i0] <= 1.0]
        if len(idx) < 3:
            continue
        g0 = int(np.searchsorted(TG, t[i0])); g1 = int(np.searchsorted(TG, t[idx[-1]]))
        tg = TG[g0:g1 + 1]; Rg = RG[g0:g1 + 1]
        acc = np.einsum('nij,nj->ni', Rg, fx(tg + d)) + G_W
        h = np.diff(tg)
        vel = np.vstack([np.zeros(3), np.cumsum(0.5 * (acc[1:] + acc[:-1]) * h[:, None], 0)])
        pos = np.vstack([np.zeros(3), np.cumsum(0.5 * (vel[1:] + vel[:-1]) * h[:, None], 0)])
        Rv = np.concatenate([np.zeros((1, 3, 3)), np.cumsum(0.5 * (Rg[1:] + Rg[:-1]) * h[:, None, None], 0)])
        Rp = np.concatenate([np.zeros((1, 3, 3)), np.cumsum(0.5 * (Rv[1:] + Rv[:-1]) * h[:, None, None], 0)])
        for c in range(3):
            Aw, yw, dts = [], [], []
            for j in idx:
                k = min(int(np.searchsorted(tg, t[j])), len(tg) - 1)
                dts.append(tg[k] - tg[0])
                Aw.append(np.concatenate([[P[j, c] - P[i0, c]], Rp[k][c, :]]))
                yw.append(pos[k, c])
            Aw = np.array(Aw); yw = np.array(yw); dts = np.array(dts)[:, None]
            # 消去 v0(该轴一列 −dt):投影到 dt 的正交补
            Pj = np.eye(len(dts)) - dts @ dts.T / float(dts.T @ dts)
            As.append(Pj @ Aw); ys.append(Pj @ yw)
    return (np.vstack(As), np.concatenate(ys)) if As else None


def combine(blks):
    blks = [b for b in blks if b is not None]
    A = np.vstack([b[0] for b in blks]); y = np.concatenate([b[1] for b in blks])
    x, *_ = np.linalg.lstsq(A, y, rcond=None)
    return 1.0 / x[0]


if __name__ == '__main__':
    pass
