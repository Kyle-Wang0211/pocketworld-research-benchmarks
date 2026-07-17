#!/usr/bin/env python3
"""#3 DSO-style inverse-depth interval maturity gate — cap50 prototype (diagnostic only).

WHAT THIS IS
    A research prototype that replaces the production fixed "triangulation angle
    >= 2 deg" birth gate with a DSO-style inverse-depth *interval* maturity gate.
    In DSO every point carries an inverse-depth interval [idepth_min, idepth_max];
    a point only "activates" (is born into the optimisation) once that interval
    has converged.  The interval half-width is, to first order,

        w_rel = (sigma_px / f) / sin(alpha_max)          (relative inverse-depth)

    i.e. proportional to 1/parallax (DSO, Engel et al. 2016, ImmaturePoint epipolar
    search).  A point is MATURE (born) iff w_rel <= tau, otherwise IMMATURE (held).

WHAT THIS IS NOT
    Not a production candidate, not a threshold decision, not a "fix".  It emits
    scripts / numbers / a viewer / a manifest with SHA-256 only.  It never claims
    a ghost was fixed; the orchestrator + user adjudicate.  No production code is
    touched; all outputs land under 03_dso_interval/.

METHOD
    The delivered sparse cloud (sfm_sparse.ply) carries no per-point track, so we
    reconstruct tracks independently from the COLMAP database's *verified* inlier
    matches (two_view_geometries), triangulate each track with the SfM-refined
    poses (sfm_sparse_meta.json), and measure per-track max parallax. This is a
    reconstruction, not the exact production track set (temporal_detail points,
    created in finalize outside the two-view graph, are under-represented -- see
    the honest LIMITATIONS block in the manifest).  Mapping image_id-1 == frame_id
    is verified by <1px reprojection before use.
"""
from __future__ import annotations

import hashlib
import json
import os
import resource
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
CAP = BASE / "data/pocketworld_captures/cap50/device_full_pull_2026-07-17"
DB = CAP / "sfm_live.db"
PLY = CAP / "sfm_sparse.ply"
META = CAP / "sfm_sparse_meta.json"

NKP = 8192
# Chair/treadmill flattened-ghost ROI (top-down right corner), from task brief.
ROI_X = (0.25, 1.05)
ROI_Z = (-1.70, -0.55)
# Fixed production birth gate: triangulation angle >= 2 deg (temporal_detail create).
FIXED_ANGLE_DEG = 2.0
# DSO interval parameters. sigma_px = epipolar pixel-localisation uncertainty.
#   1 px  -> well-refined correspondence
#   3 px  -> temporal_detail regime (born at 3px reproj tolerance, never refined)
SIGMA_PX_SET = (1.0, 3.0)
# Relative inverse-depth half-width maturity thresholds (fraction of idepth).
TAU_SET = (0.05, 0.10, 0.20)
REPROJ_KEEP_PX = 4.0  # track triangulation inlier ceiling


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def load_ply_xyzrgb(path: Path):
    with path.open("rb") as fh:
        hdr = b""
        while not hdr.endswith(b"end_header\n"):
            hdr += fh.read(1)
        n = int([l.split()[-1] for l in hdr.decode().splitlines() if l.startswith("element vertex")][0])
        dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
        a = np.frombuffer(fh.read(n * dt.itemsize), dtype=dt)
    xyz = np.stack([a["x"], a["y"], a["z"]], 1).astype(np.float64)
    rgb = np.stack([a["r"], a["g"], a["b"]], 1).astype(np.uint8)
    return xyz, rgb


def build_tracks(con, K, R_, t_, C_, P_, Kinv):
    KP = {}
    for img_id, r, cols, blob in con.execute("SELECT image_id,rows,cols,data FROM keypoints"):
        KP[img_id] = np.frombuffer(blob, np.float32).reshape(r, cols)[:, :2].astype(np.float64)
    parent = np.arange(140 * NKP, dtype=np.int64)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    seen = set()
    for pair_id, r, blob in con.execute("SELECT pair_id,rows,data FROM two_view_geometries WHERE rows>0"):
        id2 = pair_id % 2147483647
        id1 = (pair_id - id2) // 2147483647
        m = np.frombuffer(blob, np.uint32).reshape(r, 2)
        b1, b2 = id1 * NKP, id2 * NKP
        for a, b in m:
            na, nb = b1 + int(a), b2 + int(b)
            ra, rb = find(na), find(nb)
            if ra != rb:
                parent[ra] = rb
            seen.add(na)
            seen.add(nb)
    groups = defaultdict(list)
    for node in seen:
        groups[find(node)].append(node)

    def triang(obs):
        A = []
        for fid, uv in obs:
            x = Kinv @ np.array([uv[0], uv[1], 1.0])
            P = P_[fid]
            A.append(x[0] * P[2] - x[2] * P[0])
            A.append(x[1] * P[2] - x[2] * P[1])
        _, _, Vt = np.linalg.svd(np.array(A))
        X = Vt[-1]
        return X[:3] / X[3]

    recs = []  # x,y,z,nviews,maxpar_deg,ref_depth,mean_reproj
    for nodes in groups.values():
        byimg = {}
        for n in nodes:
            img = n // NKP
            if img not in byimg:
                byimg[img] = n % NKP
        obs = []
        for img, kp in byimg.items():
            fid = img - 1
            if fid in R_:
                obs.append((fid, KP[img][kp]))
        if len(obs) < 2:
            continue
        X = triang(obs)
        errs, fronts, Cs = [], [], []
        for fid, uv in obs:
            cam = R_[fid] @ X + t_[fid]
            fronts.append(cam[2] > 0)
            p = K @ cam
            p = p[:2] / p[2]
            errs.append(float(np.hypot(*(p - uv))))
            Cs.append(C_[fid])
        errs = np.array(errs)
        if not all(fronts) or np.median(errs) > REPROJ_KEEP_PX:
            continue
        Cs = np.array(Cs)
        rays = X - Cs
        rays /= np.linalg.norm(rays, axis=1, keepdims=True) + 1e-12
        cos = np.clip(rays @ rays.T, -1, 1)
        par = np.degrees(np.arccos(cos))
        maxpar = float(par[np.triu_indices(len(obs), 1)].max())
        depth = float(np.median([(R_[fid] @ X + t_[fid])[2] for fid, _ in obs]))
        recs.append((X[0], X[1], X[2], len(obs), maxpar, depth, float(errs.mean())))
    return np.array(recs)


def w_rel(maxpar_deg, sigma_px, f):
    """Relative inverse-depth interval half-width (DSO first-order model)."""
    s = np.sin(np.radians(maxpar_deg))
    s = np.maximum(s, 1e-9)
    return (sigma_px / f) / s


def gate_partition(nv, par, w, tau, fixed_deg):
    fixed_born = par >= fixed_deg
    dso_born = w <= tau
    return {
        "fixed_born": int(fixed_born.sum()),
        "fixed_held": int((~fixed_born).sum()),
        "dso_born": int(dso_born.sum()),
        "dso_held": int((~dso_born).sum()),
        # points the fixed 2deg gate BORNS but DSO HOLDS immature (extra caution)
        "dso_only_held": int((fixed_born & ~dso_born).sum()),
        # points DSO borns but fixed 2deg holds (DSO more permissive here)
        "dso_only_born": int((~fixed_born & dso_born).sum()),
        "agree_born": int((fixed_born & dso_born).sum()),
        "agree_held": int((~fixed_born & ~dso_born).sum()),
    }


def quality(mask, par, dep, reproj):
    if mask.sum() == 0:
        return {"n": 0}
    return {
        "n": int(mask.sum()),
        "parallax_deg_median": round(float(np.median(par[mask])), 4),
        "parallax_deg_p10": round(float(np.percentile(par[mask], 10)), 4),
        "mean_reproj_px_median": round(float(np.median(reproj[mask])), 4),
        "mean_reproj_px_p90": round(float(np.percentile(reproj[mask], 90)), 4),
        "depth_m_median": round(float(np.median(dep[mask])), 4),
    }


def main():
    t0 = time.time()
    out = HERE
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "run.stdout.log", "w")

    def pr(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        log.write(s + "\n")
        log.flush()

    inputs = {p.name: sha256_file(p) for p in (DB, PLY, META)}
    pr("input SHA256:", json.dumps(inputs, indent=0))

    meta = json.loads(META.read_text())
    poses = {p["frame_id"]: p for p in meta["poses"]}
    con = sqlite3.connect(str(DB))
    ff, cx, cy = np.frombuffer(con.execute("SELECT params FROM cameras").fetchone()[0], np.float64)
    K = np.array([[ff, 0, cx], [0, ff, cy], [0, 0, 1]])
    Kinv = np.linalg.inv(K)
    R_, t_, C_, P_ = {}, {}, {}, {}
    for fid, p in poses.items():
        R = quat_to_R(p["quat_wxyz"])
        t = np.array(p["t"])
        R_[fid], t_[fid], C_[fid], P_[fid] = R, t, -R.T @ t, np.hstack([R, t[:, None]])

    # --- verify image_id-1 == frame_id mapping via a large verified pair (<1px) ---
    pid, r, blob = con.execute(
        "SELECT pair_id,rows,data FROM two_view_geometries ORDER BY rows DESC LIMIT 1"
    ).fetchone()
    id2 = pid % 2147483647
    id1 = (pid - id2) // 2147483647
    m = np.frombuffer(blob, np.uint32).reshape(r, 2)
    kpq = {i: np.frombuffer(
        con.execute("SELECT data FROM keypoints WHERE image_id=?", (i,)).fetchone()[0],
        np.float32).reshape(-1, 6)[:, :2].astype(np.float64) for i in (id1, id2)}
    f1, f2 = id1 - 1, id2 - 1
    verr = []
    for a, b in m[:200]:
        u1, u2 = kpq[id1][a], kpq[id2][b]
        x1 = Kinv @ np.r_[u1, 1]
        x2 = Kinv @ np.r_[u2, 1]
        A = np.array([x1[0] * P_[f1][2] - x1[2] * P_[f1][0], x1[1] * P_[f1][2] - x1[2] * P_[f1][1],
                      x2[0] * P_[f2][2] - x2[2] * P_[f2][0], x2[1] * P_[f2][2] - x2[2] * P_[f2][1]])
        _, _, Vt = np.linalg.svd(A)
        X = Vt[-1][:3] / Vt[-1][3]
        p = K @ (R_[f1] @ X + t_[f1])
        verr.append(np.hypot(*(p[:2] / p[2] - u1)))
    map_reproj_med = float(np.median(verr))
    pr("mapping-check median reproj px:", round(map_reproj_med, 3))
    assert map_reproj_med < 1.5, "image_id-1==frame_id mapping failed"

    pr("building verified-match tracks ...")
    tr = build_tracks(con, K, R_, t_, C_, P_, Kinv)
    xyz = tr[:, :3]
    nv = tr[:, 3].astype(int)
    par = tr[:, 4]
    dep = tr[:, 5]
    reproj = tr[:, 6]
    pr(f"kept tracks: {len(tr)}  (2view={int((nv==2).sum())} 3-4={int(((nv>=3)&(nv<=4)).sum())} >=5={int((nv>=5).sum())})")
    np.savez_compressed(out / "tracks.npz", xyz=xyz.astype(np.float32),
                        nviews=nv.astype(np.int16), max_parallax_deg=par.astype(np.float32),
                        ref_depth_m=dep.astype(np.float32), mean_reproj_px=reproj.astype(np.float32))

    f_px = float(ff)
    # populations
    pop = {
        "all": np.ones(len(tr), bool),
        "two_view": nv == 2,
        "short_track_le2": nv <= 2,
        "short_track_le3": nv <= 3,
    }
    roi = (xyz[:, 0] >= ROI_X[0]) & (xyz[:, 0] <= ROI_X[1]) & (xyz[:, 2] >= ROI_Z[0]) & (xyz[:, 2] <= ROI_Z[1])
    pop["chair_roi"] = roi
    pop["chair_roi_two_view"] = roi & (nv == 2)

    # ghost proxy in the SfM cloud: floaters -- implausible depth or high reproj.
    # (Honest proxy; the SfM cloud legitimately contains the real chair, so this is
    #  a geometric-instability proxy, NOT a labelled ghost set.)
    ghost_proxy = (reproj > 2.0) | (dep < 0.10) | (dep > 6.0)
    pop["floater_proxy"] = ghost_proxy

    results = {"populations": {}, "gate_grid": {}, "distributions": {}}
    for name, mask in pop.items():
        results["populations"][name] = {
            "n": int(mask.sum()),
            "parallax_deg": {q: round(float(np.percentile(par[mask], q)), 3) for q in (5, 10, 25, 50, 75, 90)} if mask.sum() else {},
            "frac_below_2deg": round(float((par[mask] < 2).mean()), 4) if mask.sum() else None,
            "frac_below_1deg": round(float((par[mask] < 1).mean()), 4) if mask.sum() else None,
        }

    # gate grid: fixed 2deg vs DSO(sigma_px, tau); report on key populations
    for sigma in SIGMA_PX_SET:
        w = w_rel(par, sigma, f_px)
        # equivalent DSO angle for each tau: alpha = arcsin(sigma/(f*tau))
        for tau in TAU_SET:
            eq_sin = sigma / (f_px * tau)
            eq_ang = float(np.degrees(np.arcsin(np.clip(eq_sin, -1, 1)))) if eq_sin <= 1 else None
            key = f"sigma{sigma}_tau{tau}"
            entry = {"sigma_px": sigma, "tau": tau, "equiv_angle_deg": None if eq_ang is None else round(eq_ang, 4), "by_population": {}}
            for name, mask in pop.items():
                if mask.sum() == 0:
                    continue
                gp = gate_partition(nv[mask], par[mask], w[mask], tau, FIXED_ANGLE_DEG)
                # quality of the two disagreement sets
                fixed_born = par >= FIXED_ANGLE_DEG
                dso_born = w <= tau
                dso_only_held = mask & fixed_born & ~dso_born
                dso_only_born = mask & ~fixed_born & dso_born
                gp["dso_only_held_quality"] = quality(dso_only_held, par, dep, reproj)
                gp["dso_only_born_quality"] = quality(dso_only_born, par, dep, reproj)
                # ghost-proxy catch: of floater-proxy pts in this pop, what frac each gate HOLDS
                gm = mask & ghost_proxy
                if gm.sum():
                    gp["floater_proxy_n"] = int(gm.sum())
                    gp["floater_proxy_held_by_fixed"] = round(float((~(par[gm] >= FIXED_ANGLE_DEG)).mean()), 4)
                    gp["floater_proxy_held_by_dso"] = round(float((~(w[gm] <= tau)).mean()), 4)
                entry["by_population"][name] = gp
            results["gate_grid"][key] = entry

    # save gate stats
    (out / "gate_stats.json").write_text(json.dumps(results, indent=2, sort_keys=True))

    # ---------- viewer ----------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # use the sigma3/tau0.10 gate for the visual (temporal_detail regime)
    sigma_v, tau_v = 3.0, 0.10
    w_v = w_rel(par, sigma_v, f_px)
    fixed_born = par >= FIXED_ANGLE_DEG
    dso_born = w_v <= tau_v
    cat = np.zeros(len(tr), int)  # 0 agree-born
    cat[~fixed_born & ~dso_born] = 1  # agree-held
    cat[fixed_born & ~dso_born] = 2   # DSO-only held (extra caution)
    cat[~fixed_born & dso_born] = 3   # DSO-only born (DSO more permissive)
    colors = {0: "#3a86ff", 1: "#8d99ae", 2: "#e63946", 3: "#ffb703"}
    labels = {0: "born by both", 1: "held by both", 2: "DSO-only held (2deg borns, DSO holds)", 3: "DSO-only born"}

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    for ax, (title, xr, zr) in zip(axes, [("top-down (X-Z), full cloud", None, None),
                                          ("chair/treadmill ROI", ROI_X, ROI_Z)]):
        order = [1, 0, 3, 2]
        for cc in order:
            mm = cat == cc
            if xr:
                mm = mm & (xyz[:, 0] >= xr[0]) & (xyz[:, 0] <= xr[1]) & (xyz[:, 2] >= zr[0]) & (xyz[:, 2] <= zr[1])
            ax.scatter(xyz[mm, 0], xyz[mm, 2], s=(6 if xr else 1.2), c=colors[cc], label=f"{labels[cc]} ({int(mm.sum())})", linewidths=0)
        if xr:
            ax.add_patch(plt.Rectangle((xr[0], zr[0]), xr[1] - xr[0], zr[1] - zr[0], fill=False, ec="k", ls="--"))
            ax.set_xlim(xr[0] - 0.1, xr[1] + 0.1)
            ax.set_ylim(zr[0] - 0.1, zr[1] + 0.1)
        else:
            # clip to plausible room extent; a few degenerate floaters lie far outside
            ax.set_xlim(np.percentile(xyz[:, 0], 0.5), np.percentile(xyz[:, 0], 99.5))
            ax.set_ylim(np.percentile(xyz[:, 2], 0.5), np.percentile(xyz[:, 2], 99.5))
            ax.add_patch(plt.Rectangle((ROI_X[0], ROI_Z[0]), ROI_X[1] - ROI_X[0], ROI_Z[1] - ROI_Z[0], fill=False, ec="k", ls="--", lw=0.8))
        ax.set_title(title)
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Z (m)")
        ax.set_aspect("equal")
        ax.legend(fontsize=7, loc="upper right", markerscale=3)
    fig.suptitle(f"DSO interval gate vs fixed {FIXED_ANGLE_DEG}deg  (sigma_px={sigma_v}, tau={tau_v})  cap50 verified-match tracks", fontsize=12)
    fig.tight_layout()
    fig.savefig(out / "viewer_gate_topdown_and_roi.png", dpi=110)
    plt.close(fig)

    # ---------- manifest ----------
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    manifest = {
        "schema": "pocketworld_dso_interval_gate_prototype_v1",
        "kind": "diagnostic_only__not_a_production_candidate__no_self_approval",
        "capture": "cap50",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs_sha256": inputs,
        "mapping_check_median_reproj_px": round(map_reproj_med, 4),
        "camera": {"model": "SIMPLE_PINHOLE", "f_px": f_px, "cx": float(cx), "cy": float(cy), "res": [3840, 2160]},
        "interval_model": "w_rel = (sigma_px / f) / sin(alpha_max)  [DSO ImmaturePoint first-order, prop to 1/parallax]",
        "gates": {
            "fixed": f"parallax >= {FIXED_ANGLE_DEG} deg (production temporal_detail create gate)",
            "dso": "w_rel <= tau  (mature=born, else immature=held)",
        },
        "params": {"sigma_px_set": list(SIGMA_PX_SET), "tau_set": list(TAU_SET),
                   "fixed_angle_deg": FIXED_ANGLE_DEG, "reproj_keep_px": REPROJ_KEEP_PX,
                   "roi_x": ROI_X, "roi_z": ROI_Z},
        "track_count": int(len(tr)),
        "outputs": {},
        "elapsed_s": round(time.time() - t0, 2),
        "peak_rss_bytes": int(peak),
        "peak_rss_gb": round(peak / (1024**3 if sys.platform == "darwin" else 1024**2 * 1024), 3),
        "LIMITATIONS": [
            "Tracks are reconstructed from verified two_view_geometries, not the exact "
            "production track set. temporal_detail points (created in finalize outside "
            "the two-view graph) are UNDER-REPRESENTED here; treat 2-view/short-track "
            "counts as a lower bound on the low-parallax population.",
            "The geometric interval model reduces exactly to a parallax threshold "
            "(w_rel<=tau <=> alpha>=arcsin(sigma/(f*tau))). With 4K imagery (f=2559px) "
            "and sigma=1px, even 2deg parallax gives ~1.1% inverse-depth precision, so "
            "the geometric-only DSO gate does NOT hold most sub-2deg points at reasonable "
            "tau; it only bites for sub-1deg points or when sigma_px reflects the "
            "unrefined 3px temporal_detail regime. See gate_stats.json.",
            "floater_proxy is a geometric-instability proxy (reproj>2px or implausible "
            "depth), NOT a labelled ghost set. The SfM cloud legitimately contains the "
            "real chair; the flattened-chair GHOST is a plane-sweep artifact (union_baseline), "
            "adjudicated separately in #5/section 7.5. The geometric interval gate is "
            "expected NOT to catch the 17deg-parallax plane-sweep ghosts (they are "
            "photometrically consistent at floor depth); that requires the PHOTOMETRIC "
            "interval -- see photometric_interval_probe.py.",
        ],
    }
    for fn in ("tracks.npz", "gate_stats.json", "viewer_gate_topdown_and_roi.png"):
        manifest["outputs"][fn] = sha256_file(out / fn)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    pr("peak RSS GB:", manifest["peak_rss_gb"], "elapsed_s:", manifest["elapsed_s"])
    log.close()


if __name__ == "__main__":
    main()
