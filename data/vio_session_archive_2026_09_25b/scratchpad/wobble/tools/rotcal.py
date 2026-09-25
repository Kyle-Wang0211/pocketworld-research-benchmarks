#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""旋转幅度诊断:原始陀螺积分 vs ARKit vs XRSLAM(同一区间的相对旋转向量,body 系)。
  φ_ref ≈ M · φ_gyro + b·Δt     (M 3×3:对角=陀螺标度,反对称=相机-IMU 外参旋转失准;b=陀螺零偏)
区间:每帧起 0.5 s(可改);ARKit 需 normal 跟踪。ARKit 相机轴 → OpenCV:diag(1,-1,-1);R_wb = R_wc·R_bc^T。
"""
import sys

import numpy as np

sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob  # noqa: E402

Q_BC = np.array([-0.7071068, 0.7071068, 0.0, 0.0])
R_BC = wob.qmat(Q_BC[None])[0]
D = np.diag([1.0, -1.0, -1.0])


def logm(R):
    c = np.clip((np.trace(R) - 1) / 2, -1, 1)
    th = np.arccos(c)
    if th < 1e-9:
        return np.zeros(3)
    w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * np.sin(th))
    return w * th


def expm(v):
    th = np.linalg.norm(v)
    if th < 1e-12:
        return np.eye(3)
    k = v / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def gyro_integrate(imu, ta, tb, shift=0.0, bias=np.zeros(3)):
    t = imu['t'] + shift
    w = imu['w']
    i0 = np.searchsorted(t, ta) - 1
    i1 = np.searchsorted(t, tb) + 1
    R = np.eye(3)
    for i in range(max(i0, 0), min(i1, len(t) - 1)):
        a, b = max(t[i], ta), min(t[i + 1], tb)
        if b <= a:
            continue
        R = R @ expm((w[i] - bias) * (b - a))
    return R


def rel_body(Rwc_list, ia, ib):
    Ra = Rwc_list[ia] @ R_BC.T
    Rb = Rwc_list[ib] @ R_BC.T
    return Ra.T @ Rb


def run(sc, xr=None, lag=0.5, shift=0.0):
    imu = wob.load_imu(sc)
    ark = wob.load_arkit(sc)
    ta = ark['tns'] * 1e-9
    Rw = wob.qmat(ark['Q']) @ D  # ARKit → OpenCV 相机轴
    if xr is not None:
        J = wob.join(xr, ark)
        idx = {int(t): i for i, t in enumerate(xr['tns'])}
        Rx = wob.qmat(xr['Q'])
    rows = []
    for i in range(len(ta)):
        j = np.searchsorted(ta, ta[i] + lag)
        if j >= len(ta) or abs(ta[j] - ta[i] - lag) > 0.02:
            continue
        pa = logm(rel_body(Rw, i, j))
        pg = logm(gyro_integrate(imu, ta[i], ta[j], shift))
        r = [ta[i], ta[j] - ta[i], *pa, *pg]
        if xr is not None:
            ii, jj = idx.get(int(ark['tns'][i])), idx.get(int(ark['tns'][j]))
            if ii is None or jj is None:
                continue
            px = logm((Rx[ii] @ R_BC.T).T @ (Rx[jj] @ R_BC.T))
            r += list(px)
        rows.append(r)
    return np.array(rows)


def fit(A, G, dt):
    """A ≈ M G + b dt;逐轴最小二乘。返回 M, b, rms 残差(°)。"""
    X = np.hstack([G, dt[:, None]])
    M = np.zeros((3, 3)); b = np.zeros(3); res = []
    for k in range(3):
        c, *_ = np.linalg.lstsq(X, A[:, k], rcond=None)
        M[k] = c[:3]; b[k] = c[3]
        res.append(A[:, k] - X @ c)
    return M, b, np.degrees(np.sqrt(np.mean(np.array(res) ** 2)))


def decompose(M):
    """M = R·S 近似:极分解。返回(旋转角°、轴)与对称部分特征值(标度)。"""
    U, s, Vt = np.linalg.svd(M)
    Rm = U @ Vt
    S = Vt.T @ np.diag(s) @ Vt
    return np.degrees(np.linalg.norm(logm(Rm))), logm(Rm), np.linalg.eigvalsh(S), np.diag(M)


if __name__ == '__main__':
    for sc in sys.argv[1:] or ['13f5', '6d18', '7353', 'fb5d']:
        xr = wob.load_xr_phone(sc)
        A = run(sc, xr)
        dt = A[:, 1]; pa = A[:, 2:5]; pg = A[:, 5:8]; px = A[:, 8:11]
        print('== %s  区间 %d 个(0.5 s)' % (sc, len(A)))
        for name, P in (('ARKit', pa), ('XRSLAM', px)):
            M, b, rms = fit(P, pg, dt)
            ang, ax, eig, dg = decompose(M)
            print('  %-6s ≈ M·陀螺 + b:M 对角 %s  对称部分特征值 %s  失准旋转 %.2f°(轴 %s)  零偏 %s °/s  残差 %.3f°' % (
                name, np.round(dg, 4), np.round(eig, 4), ang, np.round(ax / (np.linalg.norm(ax) + 1e-12), 2),
                np.round(np.degrees(b), 3), rms))
        # 幅度比(大转角)
        na, ng, nx = [np.linalg.norm(P, axis=1) for P in (pa, pg, px)]
        big = na > np.radians(5)
        print('  幅度比(ARKit 转角>5°,%d 个):XR/ARKit 中位 %.4f  陀螺(未去零偏)/ARKit 中位 %.4f  XR/陀螺 %.4f' % (
            big.sum(), np.median(nx[big] / na[big]), np.median(ng[big] / na[big]), np.median(nx[big] / ng[big])))
