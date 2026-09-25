#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] ATE 差距的时间分布(诊断,只读)。
两条后端定稿轨迹各自对 ARKit 做全局 Sim3(同 eval3/scale_eval 估计器),得逐帧位置误差 e(t);
按 5 s 分箱给 MSE 与两者之差,并把差距归到「初始化后头 5 s」「高角速度(> p75)」等子集。
另给每个 5 s 窗各自 Sim3 的局部 ATE(去掉全局尺度 / 漂移后的局部形状误差)。
用法:ate_time.py <scene> <tagA> <tagB>(A = 旧,B = 新)"""
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
sys.path.insert(0, SP + '/wobble/tools')
import eval3  # noqa: E402
import gyrofit  # noqa: E402
import preint_eval as PE  # noqa: E402


def errors(sc, tag, ark):
    _, fin = PE.load_backend_full(PE.W + tag + '.backend.csv')
    ts = sorted(set(fin) & set(ark))
    X = np.array([fin[t][1] for t in ts]).T
    Y = np.array([ark[t][1] for t in ts]).T
    s, R, t, _ = eval3.SE['sim3'](X, Y)
    Z = s * R @ X + t[:, None] if t.ndim == 1 else s * R @ X + t
    e = np.linalg.norm(Z - Y, axis=0)
    return np.array(ts), e, X, Y


def local_ate(t, X, Y, win=5.0):
    out = []
    a = t[0]
    while a < t[-1]:
        m = (t >= a) & (t < a + win)
        if m.sum() >= 10:
            s, R, tt, _ = eval3.SE['sim3'](X[:, m], Y[:, m])
            Z = s * R @ X[:, m] + (tt[:, None] if tt.ndim == 1 else tt)
            out.append((a, 100 * float(np.sqrt(np.mean(np.sum((Z - Y[:, m]) ** 2, 0))))))
        a += win
    return out


def main(sc, ta, tb):
    rec = PE.REC[sc]
    frame_ts = [int(l.split(',')[0]) for l in open(rec + '/camera_index.csv').read().split('\n')[1:] if l]
    ark, _ = eval3.LR.arkit_poses(rec, rec + '/arkit_poses.tum', frame_ts)
    tA, eA, XA, YA = errors(sc, ta, ark)
    tB, eB, XB, YB = errors(sc, tb, ark)
    com = sorted(set(tA) & set(tB))
    iA = {t: i for i, t in enumerate(tA)}
    iB = {t: i for i, t in enumerate(tB)}
    t = np.array(com) * 1e-9
    a = np.array([eA[iA[x]] for x in com]) * 100
    b = np.array([eB[iB[x]] for x in com]) * 100
    t0 = t[0]
    G = gyrofit.GyroInt(sc)
    tt = t  # 录制 PTS;角速度用该时刻前后 50 ms 的陀螺均值
    w = np.linalg.norm(G.F(tt + 0.05) - G.F(tt - 0.05), axis=1) / 0.1
    print('%s  共同帧 %d  ATE 旧 %.2f cm 新 %.2f cm(差 %+.2f);MSE 差 %+.3f cm²' % (
        sc, len(t), np.sqrt(np.mean(a ** 2)), np.sqrt(np.mean(b ** 2)), np.sqrt(np.mean(b ** 2)) - np.sqrt(np.mean(a ** 2)),
        np.mean(b ** 2) - np.mean(a ** 2)))
    dm = b ** 2 - a ** 2
    tot = dm.sum()
    cells = []
    for s0 in np.arange(0, t[-1] - t0 + 1e-9, 5.0):
        m = (t - t0 >= s0) & (t - t0 < s0 + 5)
        if m.sum() == 0:
            continue
        cells.append('[%2.0f,%2.0f) 旧 %.2f 新 %.2f 占差距 %+4.0f%%' % (
            s0, s0 + 5, np.sqrt(np.mean(a[m] ** 2)), np.sqrt(np.mean(b[m] ** 2)), 100 * dm[m].sum() / tot))
    print('  5 s 分箱(全局对齐下 RMS cm;占 = 该箱 Σ(新²−旧²)/总差):')
    for c in cells:
        print('   ', c)
    hi = w > np.percentile(w, 75)
    print('  高角速度帧(> p75 = %.2f rad/s)占帧 25%%,占差距 %+.0f%%;头 5 s 占差距 %+.0f%%' % (
        np.percentile(w, 75), 100 * dm[hi].sum() / tot, 100 * dm[t - t0 < 5].sum() / tot))
    la = local_ate(np.array(tA) * 1e-9, XA, YA)
    lb = local_ate(np.array(tB) * 1e-9, XB, YB)
    print('  5 s 窗各自 Sim3 的局部 ATE(cm):旧 %s | 新 %s | 均值 旧 %.2f 新 %.2f' % (
        ' '.join('%.2f' % x[1] for x in la), ' '.join('%.2f' % x[1] for x in lb),
        np.mean([x[1] for x in la]), np.mean([x[1] for x in lb])))


if __name__ == '__main__':
    main(*sys.argv[1:4])
