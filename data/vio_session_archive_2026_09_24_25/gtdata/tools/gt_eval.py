#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scale / ATE evaluation of an XRSLAM trajectory against METRIC ground truth (mocap / laser / survey).

Estimator = the canonical S1 suite (scaleS1/scale_eval.py: Umeyama Sim3, signed k = est/ref,
reverse & pair-median cross-checks, 4-segment k) + S1 noise_floor.py (circular-shift residual
negative/positive control).  Only the I/O differs: both trajectories are TUM files in the SAME
body frame (we convert GT to the frame XRSLAM reports), so no phone lever arm is applied here.

  k > 1  => XRSLAM trajectory BIGGER than truth.   scale error % = 100 (k-1).

usage: gt_eval.py est.tum gt.tum [--max-dt 0.005] [--t0-trim S] [--first S] [--imu imu0.csv] [--json out.json]
"""
import json
import os
import sys

import numpy as np

S1 = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/scaleS1"
sys.path.insert(0, S1)
from scale_eval import load_full, associate, sim3, se3_ate, pair_median, segments  # noqa: E402


def interp_gt(tq, tr, Pr):
    """linear interpolation of GT positions at query times (GT is 100–400 Hz)."""
    out = np.empty((len(tq), 3))
    for d in range(3):
        out[:, d] = np.interp(tq, tr, Pr[:, d])
    return out


def pair(est, gt, max_dt=0.005, interp=True):
    te, Pe, Qe = load_full(est)
    k = te > 1e-6  # the S runner emits one identity pose stamped t=0 when a stream starts at t=0 (ADVIO): drop it
    te, Pe, Qe = te[k], Pe[k], Qe[k]
    tr, Pr, Qr = load_full(gt)
    o = np.argsort(tr); tr, Pr = tr[o], Pr[o]
    if interp:
        # keep est samples that fall inside GT coverage and have a GT sample within max_dt
        ok, pick = associate(te, tr, max_dt)
        inside = (te >= tr[0]) & (te <= tr[-1])
        m = ok & inside
        return te[m], Pe[m].T, interp_gt(te[m], tr, Pr).T
    ok, pick = associate(te, tr, max_dt)
    return te[ok], Pe[ok].T, Pr[pick[ok]].T


def noise_floor(t, X, Y, n=300, seed=7):
    s, Rm, tt, ate = sim3(X, Y)
    k = 1 / s
    res = Y - (s * Rm @ X + tt)
    Yc = Y - Y.mean(1, keepdims=True)
    rng = np.random.default_rng(seed)
    out = {}
    for k0 in (1.00, 1.05):
        ks = []
        for _ in range(n):
            lag = rng.integers(len(t) // 10, len(t) - len(t) // 10)
            Xs = k0 * Yc + np.roll(res, lag, axis=1)
            ks.append(1 / sim3(Xs, Y)[0])
        out[k0] = np.array(ks)
    lo, hi = np.percentile(out[1.00], [2.5, 97.5])
    return dict(k=k, nc_mean=float(out[1.00].mean()), nc_sd=float(out[1.00].std()), nc_band=[float(lo), float(hi)],
                pc_mean=float(out[1.05].mean()), pc_sd=float(out[1.05].std()),
                pc_recovered=bool(abs(out[1.05].mean() - 1.05) < 0.005),
                k_ci95=[float(k * lo), float(k * hi)])


def excitation(t_gt, P_gt, t_a, t_b):
    """GT-derived motion excitation inside [t_a, t_b]: path length, net displacement,
    RMS linear acceleration (2nd diff of 50 Hz-resampled GT, 0.1 s smoothing), mean speed."""
    m = (t_gt >= t_a) & (t_gt <= t_b)
    if m.sum() < 10:
        return None
    tt = np.arange(t_a, t_b, 0.02)
    P = np.stack([np.interp(tt, t_gt, P_gt[:, d]) for d in range(3)], 1)
    ker = np.ones(5) / 5
    Ps = np.stack([np.convolve(P[:, d], ker, mode='same') for d in range(3)], 1)[3:-3]
    v = np.diff(Ps, axis=0) / 0.02
    a = np.diff(v, axis=0) / 0.02
    step = np.linalg.norm(np.diff(P, axis=0), axis=1)
    return dict(path_m=float(step.sum()), disp_m=float(np.linalg.norm(P[-1] - P[0])),
                speed_mps=float(step.sum() / (t_b - t_a)),
                acc_rms=float(np.sqrt((np.linalg.norm(a, axis=1) ** 2).mean())) if len(a) else float('nan'))


def imu_excitation(imu_csv, t_a, t_b):
    """raw accelerometer excitation: std of |a| and of each axis (gravity-free proxy) in [t_a,t_b];
    gyro RMS.  imu csv = EuRoC layout: t_ns, wx, wy, wz, ax, ay, az."""
    A = []
    for ln in open(imu_csv):
        if ln.startswith('#') or not ln.strip():
            continue
        f = ln.replace(',', ' ').split()
        A.append([float(x) for x in f[:7]])
    A = np.array(A); t = A[:, 0] * 1e-9
    m = (t >= t_a) & (t <= t_b)
    if m.sum() < 10:
        return None
    w = A[m, 1:4]; a = A[m, 4:7]
    return dict(acc_axis_std=float(np.sqrt((a.std(0) ** 2).sum())), acc_norm_std=float(np.linalg.norm(a, axis=1).std()),
                gyro_rms=float(np.sqrt((np.linalg.norm(w, axis=1) ** 2).mean())))


def evaluate(est, gt, max_dt=0.005, t0_trim=0.0, first=None, imu=None, init_win=(2.0, 1.0)):
    t, X, Y = pair(est, gt, max_dt)
    te_all, _, _ = load_full(est)
    t_first_pose = float(te_all[te_all > 1e-6][0])
    if t0_trim > 0:
        m = t >= t[0] + t0_trim
        t, X, Y = t[m], X[:, m], Y[:, m]
    r = {}
    s, _, _, a_sim3 = sim3(X, Y)
    s_r, _, _, _ = sim3(Y, X)
    r.update(n=int(X.shape[1]), duration_s=float(t[-1] - t[0]), k=float(1 / s), k_rev=float(s_r),
             k_sym=float(np.sqrt(s_r / s)), ate_sim3_m=float(a_sim3), ate_se3_m=float(se3_ate(X, Y)),
             gt_extent_m=float(np.linalg.norm(Y.max(1) - Y.min(1))))
    pm, npair = pair_median(X, Y, 0.10)
    r.update(k_pair_med=pm, n_pairs=npair)
    r["noise_floor"] = noise_floor(t, X, Y)
    r["seg_k"] = segments(X, Y, t, 4) if X.shape[1] >= 120 else None
    if first:
        fk = {}
        for F in first:
            m = t <= t[0] + F
            if m.sum() >= 30 and np.linalg.norm(Y[:, m].max(1) - Y[:, m].min(1)) > 0.2:
                s_f, _, _, a_f = sim3(X[:, m], Y[:, m])
                fk[str(F)] = dict(k=float(1 / s_f), ate_sim3_m=float(a_f), n=int(m.sum()),
                                  gt_extent_m=float(np.linalg.norm(Y[:, m].max(1) - Y[:, m].min(1))))
            else:
                fk[str(F)] = None
        r["first_k"] = fk
    # initialisation window = the last init_win[0] s before the first pose XRSLAM emits
    tr, Pr, _ = load_full(gt)
    o = np.argsort(tr); tr, Pr = tr[o], Pr[o]
    r["t_first_pose_rel_gt0"] = t_first_pose - float(tr[0])
    t_a = max(t_first_pose - init_win[0], float(tr[0]))  # window clipped to GT coverage
    r["init_window_s"] = t_first_pose - t_a
    r["init_excitation_gt"] = excitation(tr, Pr, t_a, t_first_pose)
    r["post_init_excitation_gt"] = excitation(tr, Pr, t_first_pose, t_first_pose + 5.0)
    if imu:
        r["init_excitation_imu"] = imu_excitation(imu, t_a, t_first_pose)
    return r


if __name__ == "__main__":
    a = sys.argv[1:]
    est, gt = a[0], a[1]
    def opt(name, cast=float, default=None):
        return cast(a[a.index(name) + 1]) if name in a else default
    res = evaluate(est, gt, max_dt=opt("--max-dt", float, 0.005), t0_trim=opt("--t0-trim", float, 0.0),
                   first=[10, 20, 30, 60], imu=opt("--imu", str, None))
    js = opt("--json", str, None)
    if js:
        json.dump(res, open(js, "w"), indent=1)
    print(json.dumps(res, indent=1))
