#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后端帧上 0.5 s 帧对的相对位姿误差(对 ARKit):相对旋转误差、基线长度比(除以全局 k)、基线方向误差。"""
import sys
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob
from rotcal import logm
from gyrofit import backend_traj
from backend_eval import yaml_ext
D = np.diag([1.0, -1.0, -1.0])

def relerr(xr_t, xr_R, xr_C, ark, lag=0.5):
    ia = {int(t): i for i, t in enumerate(ark['tns'])}
    RA = wob.qmat(ark['Q']) @ D
    idx = [i for i, t in enumerate(xr_t) if int(t) in ia]
    t = xr_t[idx] * 1e-9; R = xr_R[idx]; C = xr_C[idx]
    A = np.array([ia[int(x)] for x in xr_t[idx]])
    X = C.T; Y = ark['P'][A].T
    kg = 1 / wob.umeyama(X, Y)[0]
    out = []
    for i in range(len(t)):
        j = np.searchsorted(t, t[i] + lag)
        if j >= len(t) or abs(t[j] - t[i] - lag) > 0.06:
            continue
        Ra, Rb = RA[A[i]], RA[A[j]]; dA = ark['P'][A[j]] - ark['P'][A[i]]
        ra, rb = R[i], R[j]; dX = C[j] - C[i]
        LA, LX = np.linalg.norm(dA), np.linalg.norm(dX)
        if LA < 0.02:
            continue
        rot = np.degrees(np.linalg.norm(logm((Ra.T @ Rb).T @ (ra.T @ rb))))
        dire = np.degrees(np.arccos(np.clip(np.dot(Ra.T @ dA / LA, ra.T @ dX / LX), -1, 1)))
        out.append((rot, LX / kg / LA, dire))
    return np.array(out)

if __name__ == '__main__':
    for a in sys.argv[1:]:
        sc, tag = a.split(':')
        Rbc, pbc = yaml_ext(tag)
        ark = wob.load_arkit(sc)
        api = wob.load_xr_mac(tag)
        tl, Rl, Pl = backend_traj(tag, 'latest'); tk, Rk, Pk = backend_traj(tag, 'kf_final')
        sel = np.isin(api['tns'], tk)
        rows = {
            'api@kf帧': (api['tns'][sel], wob.qmat(api['Q'][sel]), api['P'][sel]),
            '后端latest': (tl, Rl @ Rbc, Pl + np.einsum('nij,j->ni', Rl, pbc)),
            '后端kf_final': (tk, Rk @ Rbc, Pk + np.einsum('nij,j->ni', Rk, pbc)),
        }
        for name, (t, R, C) in rows.items():
            e = relerr(t, R, C, ark)
            print('%-5s %-12s n %3d  相对旋转误差 中位 %.3f° p90 %.3f° | 基线长度比 IQR %.4f  |偏差| 中位 %.1f%% | 方向误差 中位 %.2f°' % (
                sc, name, len(e), np.median(e[:, 0]), np.percentile(e[:, 0], 90), np.subtract(*np.percentile(e[:, 1], [75, 25])),
                100 * np.median(np.abs(e[:, 1] - np.median(e[:, 1]))), np.median(e[:, 2])))
