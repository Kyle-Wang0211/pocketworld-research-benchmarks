#!/usr/bin/env python3
"""Evaluate every finished run under runs/ against its metric GT and write results.{json,md}."""
import glob
import json
import os
import sys

import numpy as np

W = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata"
sys.path.insert(0, W + "/tools")
sys.path.insert(0, "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/scaleS1")
from gt_eval import evaluate  # noqa: E402
from scale_eval import load_full, body_to_cam  # noqa: E402

# published XRSLAM(=SF-VIO, parsac off) / XRSLAM w/ RD numbers: xrslam docs/en/benchmark.md == RD-VIO TVCG'24 Table 1 (SE3-aligned RMSE, m, mean of 10 runs)
PUB = {"euroc/V1_01_easy": (0.056, 0.060), "euroc/V1_02_medium": (0.101, 0.091), "euroc/V1_03_difficult": (0.134, 0.168),
       "advio/15": (0.779, 0.780), "advio/09": (0.332, 2.281), "advio/07": (0.559, 0.548), "advio/16": (0.986, 0.991),
       "advio/08": (2.075, 2.151), "advio/12": (2.084, 1.951), "advio/10": (1.997, 2.128)}
DEV = {"euroc": "EuRoC MAV (VI-sensor, global shutter 20 Hz, ADIS16448 200 Hz)",
       "zju": "ZJU-SenseTime (phone 640x480@30, Vicon 400 Hz)", "advio": "ADVIO (iPhone 6s 60 fps, GT = IMU+fixpoints)"}


def write_tum(path, t, P, Q):
    with open(path, "w") as f:
        for a, p, q in zip(t, P, Q):
            f.write(f"{a:.9f} {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {q[0]:.9f} {q[1]:.9f} {q[2]:.9f} {q[3]:.9f}\n")


def fix_k(est_tum, fix_csv, up):
    """ADVIO fixpoints (t, x, y, 0 = floor-plan coordinates, 2-D): similarity of the est HORIZONTAL positions
    (est up axis dropped: XRSLAM z, ARKit y, ADVIO GT y) interpolated at fixpoint times onto the fixpoints
    -> k_fix (independent of the IMU-integrated GT between fixpoints; immune to floor changes)."""
    from scale_eval import sim3
    F = np.array([[float(v) for v in ln.split(',')[:4]] for ln in open(fix_csv) if ln.strip()])
    t, P, _ = load_full(est_tum)
    m = (F[:, 0] >= t[0]) & (F[:, 0] <= t[-1])
    if m.sum() < 4:
        return None
    X = np.stack([np.interp(F[m, 0], t, P[:, d]) for d in range(3)], 0)
    X[up, :] = 0.0
    s, R, tt, ate = sim3(X, F[m, 1:4].T)
    return dict(k_fix=float(1 / s), n_fix=int(m.sum()), rms_fix_m=float(ate),
                fix_extent_m=float(np.linalg.norm(F[m, 1:4].max(0) - F[m, 1:4].min(0))))


def nonzero_tum(src, dst):
    t, P, Q = load_full(src)
    m = np.abs(P).sum(1) > 0
    write_tum(dst, t[m], P[m], Q[m])


def main():
    out = []
    for tum in sorted(glob.glob(W + "/runs/*/*.tum")):
        if tum.endswith((".stream.tum", ".cam.tum")):
            continue
        ds = tum.split("/")[-2]; base = os.path.basename(tum)[:-4]
        seq, L = base.rsplit(".", 1)
        if os.path.getsize(tum) == 0:
            continue
        if ds == "euroc":
            gt = f"{W}/ds/euroc/{seq}.gt.tum"; imu = f"{os.path.expanduser('~')}/Developer/euroc/{seq}/mav0/imu0/data.csv"; est = tum
        elif ds == "zju":
            gt = f"{W}/ds/zju/{seq}/gt.tum"; imu = f"{W}/ds/zju/{seq}/mav0/imu0/data.csv"; est = tum
        elif ds == "advio":
            gt = f"{W}/ds/advio/{seq}/gt.tum"; imu = f"{W}/ds/advio/{seq}/mav0/imu0/data.csv"
            meta = json.load(open(f"{W}/ds/advio/{seq}/meta.json"))
            t, P, Q = load_full(tum)
            est = f"{W}/work/{seq}.{L}.cam.tum"
            write_tum(est, t, body_to_cam(P, Q, np.array(meta["p_bc"])), Q)
        else:
            continue
        r = evaluate(est, gt, max_dt=0.02 if ds == "advio" else 0.005, first=[10, 20, 30, 60], imu=imu)
        if ds == "advio":
            r["fix"] = fix_k(est, f"{W}/ds/advio/{seq}/ground-truth_fixpoints.csv", 2)
        r.update(dataset=ds, seq=seq, lineage=L, n_est=int(sum(1 for _ in open(tum))),
                 published_xrslam_ate_m=PUB.get(f"{ds}/{seq}"))
        out.append(r)
    # ARKit vs GT on ADVIO (bonus: same phone, same GT)
    for d in sorted(glob.glob(W + "/ds/advio/*/arkit.tum")):
        seq = d.split("/")[-2]
        nz = f"{W}/work/{seq}.arkit.nz.tum"; nonzero_tum(d, nz)
        r = evaluate(nz, f"{W}/ds/advio/{seq}/gt.tum", max_dt=0.02, first=[10, 20, 30, 60])
        r["fix"] = fix_k(nz, f"{W}/ds/advio/{seq}/ground-truth_fixpoints.csv", 1)
        r["fix_gt_selfcheck"] = fix_k(f"{W}/ds/advio/{seq}/gt.tum", f"{W}/ds/advio/{seq}/ground-truth_fixpoints.csv", 1)
        r.update(dataset="advio", seq=seq, lineage="ARKit(on-device)", published_xrslam_ate_m=None)
        out.append(r)
    json.dump(out, open(W + "/results.json", "w"), indent=1, default=float)
    f = lambda x: "—" if x is None else f"{x:.3f}"
    lines = ["| dataset/seq | lineage | n | dur s | **k** (scale err) | noise-floor 95% | k_rev / k_pair | first 10/30 s k | seg k (4) | ATE SE3 / Sim3 m | published XRSLAM ATE (SF / RD) | t_init s | init 2 s: path m / acc_rms / IMU acc std |",
             "|" + "---|" * 13]
    for r in out:
        nf = r["noise_floor"]; fk = r.get("first_k") or {}
        g = lambda k: f(fk[k]["k"]) if fk.get(k) else "—"
        ex = r.get("init_excitation_gt") or {}; ei = r.get("init_excitation_imu") or {}
        pub = r.get("published_xrslam_ate_m")
        lines.append(
            f"| {r['dataset']}/{r['seq']} | {r['lineage']} | {r['n']} | {r['duration_s']:.0f} | **{r['k']:.4f}** ({100*(r['k']-1):+.1f}%) | "
            f"{nf['k_ci95'][0]:.3f}–{nf['k_ci95'][1]:.3f} | {r['k_rev']:.3f} / {r['k_pair_med']:.3f} | {g('10')} / {g('30')} | "
            f"{' '.join(f'{x:.3f}' for x in r['seg_k']) if r.get('seg_k') else '—'} | {r['ate_se3_m']:.3f} / {r['ate_sim3_m']:.3f} | "
            f"{'—' if not pub else f'{pub[0]:.3f} / {pub[1]:.3f}'} | {r['t_first_pose_rel_gt0']:.1f} | "
            f"{ex.get('path_m', float('nan')):.2f} / {ex.get('acc_rms', float('nan')):.2f} / {ei.get('acc_axis_std', float('nan')):.2f} |")
    open(W + "/results.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
