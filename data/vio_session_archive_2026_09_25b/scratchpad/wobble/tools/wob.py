#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wobble: 分窗尺度(XRSLAM 相对 ARKit)与协变量。
k 口径同 scale_eval.py:k = XR 尺度 / 参照尺度(k>1 ⇒ XR 轨迹更大)。
对齐:XR 位姿按录制帧 t_ns 整数键控(手机 poses_camera_by_recording_frame.csv;Mac = cam.tum + .map)。
"""
import json
import os
import sys

import numpy as np

R = os.path.expanduser('~/Developer/viobench-recordings')
SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
W = SP + '/wobble'
REC = {
    '13f5': 'run-13f53d2f-5935-4b1a-a499-4dc8367ea935',
    '6d18': 'run-6d187dff-403a-4882-b692-7bdc6c3cfa2a',
    '7353': 'run-73538ad6-8418-4eaf-8b75-a63c9d32af46',
    'fb5d': 'run-fb5d3a8f-6e31-463e-989d-bd73bb3a2def',
}
PHONE = {
    '13f5': R + '/replay_13f53d2f_pfk-on_paced_20260925_101612_expmid_default',
    '6d18': R + '/replay_6d187dff_pfk-on_paced_20260925_103521_expmid_default',
    '7353': R + '/replay_73538ad6_pfk-on_paced_20260925_103413_expmid_default',
    'fb5d': R + '/' + REC['fb5d'] + '/replay_fb5d3a8f_pfk-on_paced_20260925_095811_expmid17',
}


def rdir(sc):
    return R + '/' + REC[sc]


def umeyama(X, Y, with_scale=True):
    """Y ~ s R X + t ; X,Y (3,N)."""
    mx, my = X.mean(1, keepdims=True), Y.mean(1, keepdims=True)
    Xc, Yc = X - mx, Y - my
    n = X.shape[1]
    S = Yc @ Xc.T / n
    U, D, Vt = np.linalg.svd(S)
    C = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        C[2, 2] = -1
    Rm = U @ C @ Vt
    if with_scale:
        vx = (Xc ** 2).sum() / n
        s = np.trace(np.diag(D) @ C) / vx
    else:
        s = 1.0
    t = my - s * Rm @ mx
    return s, Rm, t


def qmat(q):
    x, y, z, w = q.T
    n = np.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / n, y / n, z / n, w / n
    Rm = np.empty((len(x), 3, 3))
    Rm[:, 0, 0] = 1 - 2 * (y * y + z * z); Rm[:, 0, 1] = 2 * (x * y - z * w); Rm[:, 0, 2] = 2 * (x * z + y * w)
    Rm[:, 1, 0] = 2 * (x * y + z * w); Rm[:, 1, 1] = 1 - 2 * (x * x + z * z); Rm[:, 1, 2] = 2 * (y * z - x * w)
    Rm[:, 2, 0] = 2 * (x * z - y * w); Rm[:, 2, 1] = 2 * (y * z + x * w); Rm[:, 2, 2] = 1 - 2 * (x * x + y * y)
    return Rm


def load_intr(sc):
    L = [json.loads(l) for l in open(rdir(sc) + '/ruler_subset/intrinsics.jsonl') if l.strip()]
    tns = np.array([int(round(x['t'] * 1e9)) for x in L], dtype=np.int64)
    fx = np.array([x['intrinsics_fxfycxcy'][0] for x in L])
    cx = np.array([x['intrinsics_fxfycxcy'][2] for x in L])
    cy = np.array([x['intrinsics_fxfycxcy'][3] for x in L])
    ex = np.array([x.get('exposure_s', np.nan) for x in L])
    trk = np.array([x.get('arkit_tracking', 'normal') for x in L])
    return dict(tns=tns, fx=fx, cx=cx, cy=cy, exp=ex, trk=trk)


def load_arkit(sc):
    A = np.loadtxt(rdir(sc) + '/ruler_subset/arkit_poses.tum')
    tns = np.round(A[:, 0] * 1e9).astype(np.int64)
    I = load_intr(sc)
    ok_trk = dict(zip(I['tns'].tolist(), (I['trk'] == 'normal').tolist()))
    good = np.array([ok_trk.get(int(t), True) for t in tns]) & (np.abs(A[:, 1:4]).sum(1) > 0)
    return dict(tns=tns[good], P=A[good, 1:4], Q=A[good, 4:8])


def load_imu(sc):
    M = np.loadtxt(rdir(sc) + '/ruler_subset/imu.csv', delimiter=',', skiprows=1)
    return dict(t=M[:, 0] * 1e-9, w=M[:, 1:4], a=M[:, 4:7])


def load_xr_phone(sc):
    d = PHONE[sc]
    M = np.genfromtxt(d + '/poses_camera_by_recording_frame.csv', delimiter=',', names=True)
    tns = M['t_ns'].astype(np.int64)
    P = np.stack([M['tx'], M['ty'], M['tz']], 1)
    Q = np.stack([M['qx'], M['qy'], M['qz'], M['qw']], 1)
    return dict(tns=tns, P=P, Q=Q)


def load_xr_mac(tag):
    C = np.loadtxt(W + '/runs/%s.cam.tum' % tag)
    mp = {}
    for ln in open(W + '/runs/%s.map' % tag):
        a, b = ln.split()
        mp[a] = int(b)
    tns, keep = [], []
    for i, t in enumerate(C[:, 0]):
        k = '%.9f' % t
        if k in mp:
            tns.append(mp[k]); keep.append(i)
    C = C[keep]
    good = np.linalg.norm(C[:, 4:8], axis=1) > 0.5
    return dict(tns=np.array(tns, dtype=np.int64)[good], P=C[good, 1:4], Q=C[good, 4:8])


def join(xr, ark):
    ia = {int(t): i for i, t in enumerate(ark['tns'])}
    pairs = [(i, ia[int(t)]) for i, t in enumerate(xr['tns']) if int(t) in ia]
    ix = np.array([p[0] for p in pairs]); jx = np.array([p[1] for p in pairs])
    return dict(t=xr['tns'][ix] * 1e-9, X=xr['P'][ix].T, Y=ark['P'][jx].T, QX=xr['Q'][ix], QY=ark['Q'][jx],
                tns=xr['tns'][ix])


def k_sim3(X, Y):
    s, _, _ = umeyama(X, Y)
    return 1.0 / s


def ate_sim3(X, Y):
    s, Rm, t = umeyama(X, Y)
    e = np.linalg.norm(s * Rm @ X + t - Y, axis=0)
    return float(np.sqrt((e ** 2).mean()))


def disp_ratio(t, X, Y, lag=0.5, min_d=0.02):
    """免对齐:间隔 lag 秒的帧对位移长度比 |ΔX|/|ΔY|(中位数)。返回 (中位数, 帧对数)。"""
    j = np.searchsorted(t, t + lag)
    ok = j < len(t)
    i = np.nonzero(ok)[0]; j = j[ok]
    dY = np.linalg.norm(Y[:, j] - Y[:, i], axis=0)
    dX = np.linalg.norm(X[:, j] - X[:, i], axis=0)
    m = dY > min_d
    if m.sum() < 5:
        return np.nan, int(m.sum())
    return float(np.median(dX[m] / dY[m])), int(m.sum())


def windows(J, win=4.0, step=0.5, lag=0.5, min_n=30):
    t, X, Y = J['t'], J['X'], J['Y']
    out = []
    a = t[0]
    while a + win <= t[-1] + 1e-9:
        m = (t >= a) & (t < a + win)
        if m.sum() >= min_n:
            ks = k_sim3(X[:, m], Y[:, m])
            kd, nd = disp_ratio(t[m], X[:, m], Y[:, m], lag)
            ext = float(np.sqrt(((Y[:, m] - Y[:, m].mean(1, keepdims=True)) ** 2).sum(0).mean()))
            out.append(dict(t0=a, t1=a + win, tc=a + win / 2, k_sim3=ks, k_disp=kd, n_disp=nd, n=int(m.sum()),
                            ref_rms_m=ext))
        a += step
    return out


def quarters(J, n=4):
    t, X, Y = J['t'], J['X'], J['Y']
    e = np.linspace(t[0], t[-1], n + 1)
    res = []
    for a, b in zip(e[:-1], e[1:]):
        m = (t >= a) & (t <= b)
        res.append(k_sim3(X[:, m], Y[:, m]))
    return res


def smooth(x, n):
    if n <= 1:
        return x
    k = np.ones(n) / n
    if x.ndim == 1:
        return np.convolve(x, k, mode='same')
    return np.stack([np.convolve(x[:, c], k, mode='same') for c in range(x.shape[1])], 1)


def covariates(sc, t0, t1, ark=None, imu=None, intr=None):
    """窗口 [t0,t1) 内的运动/激励/焦距/曝光协变量。"""
    imu = imu or load_imu(sc)
    intr = intr or load_intr(sc)
    ark = ark or load_arkit(sc)
    m = (imu['t'] >= t0) & (imu['t'] < t1)
    wn = np.linalg.norm(imu['w'][m], axis=1)
    an = np.linalg.norm(imu['a'][m], axis=1)
    ta = ark['tns'] * 1e-9
    P = ark['P']
    # ARKit 速度 / 线加速度(中心差分 + 0.1 s 平滑)
    v = np.gradient(P, ta, axis=0)
    vs = smooth(v, 3)
    acc = np.gradient(vs, ta, axis=0)
    accs = smooth(acc, 5)
    ma = (ta >= t0) & (ta < t1)
    mi = (intr['tns'] * 1e-9 >= t0) & (intr['tns'] * 1e-9 < t1)
    fx = intr['fx'][mi]
    ex = intr['exp'][mi]
    # ARKit 旋转速率(相机)
    Rm = qmat(ark['Q'][ma])
    tt = ta[ma]
    if len(tt) > 2:
        dR = np.einsum('nji,njk->nik', Rm[:-1], Rm[1:])
        ang = np.arccos(np.clip((np.trace(dR, axis1=1, axis2=2) - 1) / 2, -1, 1))
        rot_rate = ang / np.diff(tt)
    else:
        rot_rate = np.array([np.nan])
    return dict(
        gyro_mean=float(wn.mean()) if len(wn) else np.nan,
        gyro_rms=float(np.sqrt((wn ** 2).mean())) if len(wn) else np.nan,
        gyro_p90=float(np.percentile(wn, 90)) if len(wn) else np.nan,
        acc_norm_std=float(an.std()) if len(an) else np.nan,
        speed=float(np.linalg.norm(vs[ma], axis=1).mean()),
        lin_acc=float(np.linalg.norm(accs[ma], axis=1).mean()),
        lin_acc_rms=float(np.sqrt((np.linalg.norm(accs[ma], axis=1) ** 2).mean())),
        path_m=float(np.linalg.norm(np.diff(P[ma], axis=0), axis=1).sum()),
        fx_mean=float(fx.mean()) if len(fx) else np.nan,
        fx_range_pct=float(100 * (fx.max() - fx.min()) / fx.mean()) if len(fx) else np.nan,
        fx_tv_pct=float(100 * np.abs(np.diff(fx)).sum() / fx.mean()) if len(fx) > 1 else np.nan,
        exp_ms=float(1e3 * ex.mean()) if len(ex) else np.nan,
        blur_px=float(wn.mean() * (ex.mean() if len(ex) else np.nan) * (fx.mean() / 3 if len(fx) else np.nan)),
        arkit_rot_rate=float(np.nanmean(rot_rate)),
    )


def summarize(sc, xr, label, win=4.0, step=0.5):
    ark = load_arkit(sc)
    J = join(xr, ark)
    kg = k_sim3(J['X'], J['Y'])
    ws = windows(J, win, step)
    q = quarters(J)
    ks = np.array([w['k_sim3'] for w in ws]) / kg
    kd = np.array([w['k_disp'] for w in ws])
    kdg, _ = disp_ratio(J['t'], J['X'], J['Y'], 0.5)
    kd = kd / kdg
    return dict(label=label, n=len(J['t']), k_global=kg, ate_cm=100 * ate_sim3(J['X'], J['Y']),
                quarters=[x / kg for x in q], quarters_abs=q,
                win_sim3_rel_minmax=[float(np.nanmin(ks)), float(np.nanmax(ks))],
                win_sim3_rel_sd=float(np.nanstd(ks)),
                win_disp_rel_minmax=[float(np.nanmin(kd)), float(np.nanmax(kd))],
                win_disp_rel_sd=float(np.nanstd(kd)), windows=ws, J=J)


if __name__ == '__main__':
    for sc in sys.argv[1:] or ['13f5', '6d18', '7353', 'fb5d']:
        s = summarize(sc, load_xr_phone(sc), 'phone')
        print(sc, 'n', s['n'], 'k %.4f ATE %.2f cm' % (s['k_global'], s['ate_cm']),
              'Q(abs)', ' '.join('%.3f' % x for x in s['quarters_abs']),
              '| 4s-win sim3 rel sd %.3f [%.3f,%.3f]' % (s['win_sim3_rel_sd'], *s['win_sim3_rel_minmax']),
              '| disp sd %.3f [%.3f,%.3f]' % (s['win_disp_rel_sd'], *s['win_disp_rel_minmax']))
