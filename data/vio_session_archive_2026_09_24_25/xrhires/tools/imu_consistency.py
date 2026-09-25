#!/usr/bin/env python3
"""[xrhires] Offline IMU-vs-VIO scale consistency of an XRSLAM output trajectory (engine-independent).

Windows of T s (step S s) over the output BODY (=IMU) poses at frame times. Per window, with the VIO
rotation at the window start R0 and gyro-integrated relative rotation dR(tau) inside the window, solve
    lam * (p_k - p_0) = v0*tau_k + 0.5*g(theta)*tau_k^2 + R0*(alpha_k - J_k*ba)
for x = [lam, v0(3), ba(3), tilt(2)], g(theta) = (-g*ty, g*tx, -g) (XRSLAM world gravity (0,0,-9.80665),
preintegrator.cpp:103), alpha_k = double integral of dR*a_m, J_k = double integral of dR.
lam is the factor the VIO positions need to agree with the accelerometer (metric):
    k_imu = 1/lam  (>1 => VIO trajectory bigger than the IMU says; same sign convention as k vs ARKit).
Reported: ivw-mean k_imu, z-std = std over windows of (lam_w - lam_ivw)/se_w (se from LS residuals; residuals
are autocorrelated so absolute z-std is inflated -- use it only to COMPARE arms), windows used.
This is NOT S3's in-engine imu_gn metric; same idea, computed from the output trajectory.
"""
import sys, json, os
import numpy as np

G = 9.80665
REVERSE = True   # see analyse(): mu = k_imu directly; the forward form (lam) is kept for comparison
R = os.path.expanduser('~/Developer/viobench-recordings')
RUNS = {'6e2d': 'run-6e2d4b99-896b-4372-ae47-ac0b4679cf18', '5966': 'run-5966aec0-cbf1-4abc-af0e-c1fc559da44c',
        '4ad6': 'run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa'}


def qmat(q):
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def expm_so3(w):
    th = np.linalg.norm(w)
    K = np.array([[0, -w[2], w[1]], [w[2], 0, -w[0]], [-w[1], w[0], 0]])
    if th < 1e-12: return np.eye(3) + K
    return np.eye(3) + np.sin(th) / th * K + (1 - np.cos(th)) / th ** 2 * K @ K


_IMU = {}


def imu_of(sc):
    if sc not in _IMU:
        d = np.loadtxt(R + '/' + RUNS[sc] + '/imu.csv', delimiter=',', skiprows=1)
        d[:, 0] *= 1e-9
        _IMU[sc] = d
    return _IMU[sc]


def analyse(body_tum, sc, T=2.0, S=0.5, skip=3.0):
    tr = np.loadtxt(body_tum)
    t, P, Q = tr[:, 0], tr[:, 1:4], tr[:, 4:8]
    imu = imu_of(sc)
    ti, wi, ai = imu[:, 0], imu[:, 1:4], imu[:, 4:7]
    lams, ses = [], []
    t_start = t[0] + skip
    for a in np.arange(t_start, t[-1] - T, S):
        m = (t >= a) & (t <= a + T)
        idx = np.where(m)[0]
        if len(idx) < 30: continue
        if np.any(np.diff(t[idx]) > 0.1): continue   # gap
        t0 = t[idx[0]]
        R0 = qmat(Q[idx[0]])
        # integrate IMU from t0 to t_end at IMU rate (zero-order hold, midpoint rotation)
        mi = (ti >= t0 - 0.02) & (ti <= t[idx[-1]] + 0.02)
        tt, ww, aa = ti[mi], wi[mi], ai[mi]
        if len(tt) < 10: continue
        dR = np.eye(3); al = np.zeros(3); be = np.zeros(3); J = np.zeros((3, 3)); Jv = np.zeros((3, 3))
        cur = t0; j = np.searchsorted(tt, t0) - 1; j = max(j, 0)
        rows_A, rows_b = [], []
        targets = list(t[idx[1:]]); ki = 1
        while targets:
            nxt_imu = tt[j + 1] if j + 1 < len(tt) else np.inf
            tgt = targets[0]
            t_next = min(nxt_imu, tgt)
            dt = t_next - cur
            if dt > 0:
                w = ww[j]; acc = aa[j]
                Rm = dR @ expm_so3(0.5 * w * dt)
                al = al + be * dt + 0.5 * (Rm @ acc) * dt * dt
                J = J + Jv * dt + 0.5 * Rm * dt * dt
                be = be + (Rm @ acc) * dt
                Jv = Jv + Rm * dt
                dR = dR @ expm_so3(w * dt)
                cur = t_next
            if t_next == tgt:
                k = idx[ki]; tau = t[k] - t0
                dp = P[k] - P[idx[0]]
                # lam*dp - v0*tau - 0.5*tau^2*g(theta) + R0 J ba = R0 al + 0.5 tau^2 g0
                if REVERSE:
                    # VIO displacement is the dependent variable (its jitter does not dilute the slope):
                    # dp = u*tau + mu*(R0*al + 0.5 tau^2 g0) - R0 J c + 0.5 tau^2 (dg_x, dg_y, 0);  mu = k_imu
                    A = np.zeros((3, 9))
                    A[:, 0] = R0 @ al + 0.5 * tau * tau * np.array([0, 0, -G])
                    A[:, 1:4] = tau * np.eye(3)
                    A[:, 4:7] = -R0 @ J
                    A[0, 7] = 0.5 * tau * tau
                    A[1, 8] = 0.5 * tau * tau
                    b = dp
                else:
                    A = np.zeros((3, 9))
                    A[:, 0] = dp
                    A[:, 1:4] = -tau * np.eye(3)
                    A[:, 4:7] = R0 @ J
                    # g(theta) - g0 = (-G*ty, G*tx, 0) ; move -0.5 tau^2 * that to A
                    A[0, 8] = 0.5 * tau * tau * G      # -0.5tau^2*(-G*ty)
                    A[1, 7] = -0.5 * tau * tau * G     # -0.5tau^2*(G*tx)
                    b = R0 @ al + 0.5 * tau * tau * np.array([0, 0, -G])
                rows_A.append(A); rows_b.append(b)
                targets.pop(0); ki += 1
            if t_next == nxt_imu:
                j += 1
                if j + 1 >= len(tt) and targets:
                    break
        if len(rows_A) < 20: continue
        A = np.vstack(rows_A); b = np.concatenate(rows_b)
        x, res, rk, sv = np.linalg.lstsq(A, b, rcond=None)
        if rk < 9: continue
        r = b - A @ x
        s2 = r @ r / max(len(b) - 9, 1)
        cov = s2 * np.linalg.inv(A.T @ A)
        lams.append(x[0]); ses.append(np.sqrt(cov[0, 0]))
    lams, ses = np.array(lams), np.array(ses)
    ok = np.isfinite(lams) & np.isfinite(ses) & (ses > 0) & (ses < 0.5) & (lams > 0)
    lams, ses = lams[ok], ses[ok]
    if len(lams) < 5:
        return {'n_win': int(len(lams))}
    w = 1 / ses ** 2
    lam = float(np.sum(w * lams) / w.sum())
    z = (lams - lam) / ses
    if REVERSE:   # lams hold mu = k_imu
        return {'form': 'reverse', 'n_win': int(len(lams)), 'k_imu_ivw': lam, 'k_imu_median': float(np.median(lams)),
                'z_std': float(np.std(z)), 'z_mad': float(1.4826 * np.median(np.abs(z - np.median(z)))),
                'k_sd': float(np.std(lams)), 'se_med': float(np.median(ses))}
    return {'form': 'forward', 'n_win': int(len(lams)), 'k_imu_ivw': 1 / lam, 'k_imu_median': float(1 / np.median(lams)),
            'z_std': float(np.std(z)), 'z_mad': float(1.4826 * np.median(np.abs(z - np.median(z)))),
            'lam_sd': float(np.std(lams)), 'se_med': float(np.median(ses))}


if __name__ == '__main__':
    out = analyse(sys.argv[1], sys.argv[2])
    print(json.dumps(out))
