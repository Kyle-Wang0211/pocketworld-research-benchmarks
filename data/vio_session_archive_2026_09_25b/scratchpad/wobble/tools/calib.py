#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断:ARKit 相机位姿 + 原始 IMU ⇒ ARKit 隐含的相机-IMU 外参(旋转 R_bc、杆臂 p_bc)与时间偏移。
只用于判断台架 yaml 的占位外参偏了多少,不是产品标定,不进任何产品路径。
旋转:α_b(陀螺在 [ta+τ,tb+τ] 的旋转向量,去零偏)≈ R_bc α_c(ARKit 相机相对旋转向量),Kabsch + 零偏交替。
平移:a_m = R_wbᵀ(C̈ + g_up) − ([ω̇]× + [ω]×²) p_bc + b_a,线性最小二乘(两边同样低通)。
"""
import sys

import numpy as np

sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob  # noqa: E402
from rotcal import logm, expm, gyro_integrate, R_BC, D  # noqa: E402

G = 9.81
P_BC0 = np.array([0.03290364, -0.00696553, -0.00286231])


def skew(v):
    return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])


def kabsch(A, B):
    """B ≈ R A (A,B: N×3)。"""
    H = A.T @ B
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1, 1, d]) @ U.T


def rot_calib(sc, lag=0.1, taus=np.arange(-0.03, 0.0301, 0.002)):
    imu = wob.load_imu(sc); ark = wob.load_arkit(sc)
    ta = ark['tns'] * 1e-9
    Rw = wob.qmat(ark['Q']) @ D
    idx = []
    for i in range(len(ta)):
        j = np.searchsorted(ta, ta[i] + lag)
        if j < len(ta) and abs(ta[j] - ta[i] - lag) < 0.01:
            idx.append((i, j))
    ac = np.array([logm(Rw[i].T @ Rw[j]) for i, j in idx])
    dt = np.array([ta[j] - ta[i] for i, j in idx])
    best = None
    for tau in taus:
        gb = np.array([logm(gyro_integrate(imu, ta[i] + tau, ta[j] + tau)) for i, j in idx])
        b = np.zeros(3)
        for _ in range(4):
            Rbc = kabsch(ac, gb - b[None] * dt[:, None])
            b = ((gb - ac @ Rbc.T) * dt[:, None]).sum(0) / (dt ** 2).sum()
        res = gb - b[None] * dt[:, None] - ac @ Rbc.T
        rms = np.sqrt((res ** 2).sum(1).mean())
        if best is None or rms < best[0]:
            best = (rms, tau, Rbc, b)
    rms, tau, Rbc, b = best
    dR = Rbc @ R_BC.T
    return dict(tau_ms=1e3 * tau, R_bc=Rbc, misalign_deg=np.degrees(np.linalg.norm(logm(dR))),
                misalign_axis=logm(dR), bias_dps=np.degrees(b), rms_deg=np.degrees(rms))


def lowpass(x, t, fc):
    """零相位一阶巴特沃斯式滑动:用高斯核近似(σ = 1/(2π fc))。"""
    s = 1.0 / (2 * np.pi * fc)
    dt = np.median(np.diff(t))
    n = int(np.ceil(4 * s / dt))
    k = np.exp(-0.5 * (np.arange(-n, n + 1) * dt / s) ** 2); k /= k.sum()
    if x.ndim == 1:
        return np.convolve(x, k, mode='same')
    return np.stack([np.convolve(x[:, c], k, mode='same') for c in range(x.shape[1])], 1)


def lever_calib(sc, Rbc, tau, fc=4.0, halves=False):
    imu = wob.load_imu(sc); ark = wob.load_arkit(sc)
    ta = ark['tns'] * 1e-9
    Rwc = wob.qmat(ark['Q']) @ D
    C = ark['P']
    # 均匀重采样到 200 Hz(ARKit 30 Hz 位置样条近似:三次插值 via numpy polyfit 局部太复杂 ⇒ 线性插值后低通)
    t = np.arange(ta[5], ta[-5], 0.005)
    Ci = np.stack([np.interp(t, ta, C[:, k]) for k in range(3)], 1)
    Cs = lowpass(Ci, t, fc)
    Cdd = np.gradient(np.gradient(Cs, t, axis=0), t, axis=0)
    # 旋转:在 ARKit 帧间 slerp 近似 —— 用最近帧 + 陀螺前推太复杂;4 Hz 低通下直接取最近帧
    k = np.clip(np.searchsorted(ta, t), 1, len(ta) - 1)
    k = np.where(np.abs(ta[k - 1] - t) < np.abs(ta[k] - t), k - 1, k)
    Rwb = Rwc[k] @ Rbc.T
    ti = imu['t'] + tau
    w = np.stack([np.interp(t, ti, imu['w'][:, c]) for c in range(3)], 1)
    am = np.stack([np.interp(t, ti, imu['a'][:, c]) for c in range(3)], 1)
    ws = lowpass(w, t, fc); ams = lowpass(am, t, fc)
    wd = np.gradient(ws, t, axis=0)
    g_up = np.array([0, G, 0])  # ARKit 世界 y 轴向上
    f_ark = np.einsum('nji,nj->ni', Rwb, Cdd + g_up)  # R_wbᵀ (C̈ + g_up)
    # a_m ≈ s⊙f_ark − (skew(wd)+skew(w)²) p + b    未知:p(3) b(3) s(3 对角标度)
    rows_A, rows_y = [], []
    m = slice(int(1.0 / 0.005), len(t) - int(1.0 / 0.005))
    for n in range(len(t))[m]:
        Mrot = skew(wd[n]) + skew(ws[n]) @ skew(ws[n])
        for c in range(3):
            a = np.zeros(9)
            a[0:3] = -Mrot[c]
            a[3 + c] = 1.0
            a[6 + c] = f_ark[n, c]
            rows_A.append(a); rows_y.append(ams[n, c])
    A = np.array(rows_A); y = np.array(rows_y)
    out = {}
    sel = {'all': np.arange(len(y))}
    if halves:
        h = len(y) // 2 // 3 * 3
        sel['first'] = np.arange(h); sel['second'] = np.arange(h, len(y))
    for name, s in sel.items():
        x, *_ = np.linalg.lstsq(A[s], y[s], rcond=None)
        r = y[s] - A[s] @ x
        cov = np.linalg.inv(A[s].T @ A[s]) * (r @ r) / (len(s) - 9)
        # 固定占位 p_bc 的残差对比
        x0 = x.copy(); x0[0:3] = P_BC0
        A2 = A[s][:, 3:]; y2 = y[s] - A[s][:, 0:3] @ P_BC0
        x2, *_ = np.linalg.lstsq(A2, y2, rcond=None)
        r0 = y2 - A2 @ x2
        out[name] = dict(p_bc=x[0:3], p_sd=np.sqrt(np.diag(cov)[0:3]), b_a=x[3:6], s_acc=x[6:9],
                         rms=np.sqrt(np.mean(r ** 2)), rms_placeholder=np.sqrt(np.mean(r0 ** 2)))
    return out


if __name__ == '__main__':
    for sc in sys.argv[1:] or ['13f5', '6d18', '7353', 'fb5d']:
        rc = rot_calib(sc)
        print('== %s  旋转:时间偏移 τ(IMU 相对 ARKit 帧时间)%+.1f ms  占位 q_bc 失准 %.2f°  轴 %s  陀螺零偏 %s °/s  残差 %.3f°' % (
            sc, rc['tau_ms'], rc['misalign_deg'], np.round(rc['misalign_axis'] / np.linalg.norm(rc['misalign_axis']), 2),
            np.round(rc['bias_dps'], 3), rc['rms_deg']))
        lv = lever_calib(sc, rc['R_bc'], rc['tau_ms'] * 1e-3, halves=True)
        for k, v in lv.items():
            print('   杆臂[%s] p_bc = %s mm ± %s  (占位 %s)  b_a %s  加计标度×ARKit %s  残差 %.4f vs 用占位 %.4f m/s²' % (
                k, np.round(1e3 * v['p_bc'], 1), np.round(1e3 * v['p_sd'], 1), np.round(1e3 * P_BC0, 1),
                np.round(v['b_a'], 3), np.round(v['s_acc'], 4), v['rms'], v['rms_placeholder']))
