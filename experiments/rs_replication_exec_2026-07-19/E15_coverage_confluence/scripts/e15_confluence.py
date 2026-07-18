#!/usr/bin/env python3.11
"""E15 coverage confluence — can detector-free / rescue coverage occupy the ghost
no-man's-land (E13: ghost obs nearest true obs p50=190px)?

Pure analysis, read-only on all inputs. Outputs only to E15_coverage_confluence/analysis.

Metric ("可制造对手率"): for each ghost-band 3D point, min over its observations of the
nearest same-frame coverage-source observation (px, camera space 3840x2160); rate of
ghost points with a coverage obs within radius 8/16/32 px. Control = true-floor-band
points through the identical pipe (contrast ruler).

Coverage sources:
  cap51: E6 injected rescue points' observations (rescue_provenance_cap51.npz,
         injected_mask); plus full E6 LoFTR candidate pool (pre-gate upper bound).
         floor_rescue LoFTR: cap51 NOT AVAILABLE (experiment was cap50) -> marked.
         weaktex_recall: NOT FOUND in worktree -> marked.
  cap50: E6 injected + pool; floor_rescue raw LoFTR matches (fr_matches.npz,
         WORK 1024x576 -> x3.75 to camera space; fid -> image_id = fid+1, pose-verified).
"""
import json
import os
import subprocess
import sys

import numpy as np
from scipy.spatial import cKDTree

E15 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(E15), "E13_dual_birth_inventory", "scripts"))
import e13_lib as L  # noqa: E402

EXP = os.path.dirname(E15)
ANA = os.path.join(E15, "analysis")
os.makedirs(ANA, exist_ok=True)

TRUE_LO, TRUE_HI = -0.0075, 0.0125     # E13 step2 fixed production-plane bands
GHOST_LO, GHOST_HI = -0.045, -0.020
RADII = (8.0, 16.0, 32.0)
CAM_W = 3840
WORK_W = 1024
FR_SCALE = CAM_W / WORK_W               # 3.75, aspect-preserving (both 16:9)


def vm_avail_gb():
    out = subprocess.check_output(["vm_stat"]).decode()
    d = {}
    for ln in out.splitlines():
        if ":" in ln and "Pages" in ln:
            k, v = ln.split(":")
            d[k.strip()] = int(v.strip().rstrip("."))
    return (d.get("Pages free", 0) + d.get("Pages speculative", 0) + d.get("Pages inactive", 0)) * 16384 / 1e9


def load_band_obs(cap):
    """Return dict: band -> (pt_index_array, obs arrays (pt_row, iid, xy))."""
    z = np.load(f"{EXP}/E13_dual_birth_inventory/analysis/step1_cache_{cap}.npz")
    fh = z["fh"]
    obs_pt, obs_iid, obs_kp = z["obs_pt"], z["obs_iid"], z["obs_kp"]
    imgs = L.read_images_bin_full(L.OFF_RUN[cap] + "/images.bin")
    # pixel of every observation
    xy = np.empty((len(obs_pt), 2), np.float64)
    for iid in np.unique(obs_iid):
        m = obs_iid == iid
        xy[m] = imgs[int(iid)]["xys"][obs_kp[m]]
    bands = {
        "ghost": np.flatnonzero((fh >= GHOST_LO) & (fh < GHOST_HI)),
        "true": np.flatnonzero((fh >= TRUE_LO) & (fh < TRUE_HI)),
    }
    out = {}
    for name, rows in bands.items():
        sel = np.isin(obs_pt, rows)
        out[name] = dict(pt_rows=rows, obs_pt=obs_pt[sel], obs_iid=obs_iid[sel], obs_xy=xy[sel])
    return out, imgs


def cov_e6(cap, injected_only):
    d = np.load(f"{EXP}/E6_rescue_inject/{cap}/rescue_provenance_{cap}.npz")
    keep = d["injected_mask"] if injected_only else np.ones(len(d["f1"]), bool)
    iid = np.concatenate([d["f1"][keep] + 1, d["f2"][keep] + 1])  # E6 f = image_id-1
    xy = np.concatenate([d["xy1"][keep], d["xy2"][keep]])
    return iid.astype(np.int64), xy.astype(np.float64)


def cov_floor_loftr():
    """cap50 floor-rescue raw LoFTR matches (conf>=0.2, pre-geometry = coverage upper bound)."""
    fr = np.load(f"{os.path.dirname(EXP)}/floor_plane_sweep_densifier_2026-07-13/"
                 "contract/intermediates/noncommercial_matches/fr_matches.npz")
    iids, xys = [], []
    for k in fr.files:
        if not k.endswith("_p0"):
            continue
        i, j, _ = k.split("_")
        p0, p1 = fr[k], fr[f"{i}_{j}_p1"]
        iids.append(np.full(len(p0), int(i) + 1, np.int64))
        xys.append(p0.astype(np.float64) * FR_SCALE)
        iids.append(np.full(len(p1), int(j) + 1, np.int64))
        xys.append(p1.astype(np.float64) * FR_SCALE)
    return np.concatenate(iids), np.concatenate(xys)


def verify_floor_frame_mapping(imgs):
    """floor-rescue fid -> image_id=fid+1: pose agreement check on 3 frames."""
    P = json.load(open(f"{os.path.dirname(EXP)}/floor_plane_sweep_densifier_2026-07-13/poses.json"))["poses"]
    worst = 0.0
    for fid in (0, 30, 90):
        if str(fid) not in P or (fid + 1) not in imgs:
            continue
        R = np.array(P[str(fid)]["R_cam_from_world"])
        t = np.array(P[str(fid)]["t_cam_from_world"])
        im = imgs[fid + 1]
        worst = max(worst, float(np.abs(R - L.qvec2rot(im["qvec"])).max()),
                    float(np.abs(t - im["tvec"]).max()))
    return worst


def nearest_per_point(band, cov_iid, cov_xy):
    """Per 3D point: min over its obs of dist to nearest same-frame coverage obs."""
    trees = {}
    for iid in np.unique(cov_iid):
        trees[int(iid)] = cKDTree(cov_xy[cov_iid == iid])
    dmin = {}
    for iid in np.unique(band["obs_iid"]):
        m = band["obs_iid"] == iid
        tr = trees.get(int(iid))
        d = tr.query(band["obs_xy"][m], k=1)[0] if tr is not None else np.full(m.sum(), np.inf)
        for pt, dd in zip(band["obs_pt"][m], d):
            if dd < dmin.get(int(pt), np.inf):
                dmin[int(pt)] = float(dd)
    pts = band["pt_rows"]
    arr = np.array([dmin.get(int(p), np.inf) for p in pts])
    fin = arr[np.isfinite(arr)]
    return {
        "n_points": int(len(pts)),
        "nearest_cov_px_p50": (round(float(np.median(fin)), 2) if len(fin) else None),
        "nearest_cov_px_p90": (round(float(np.percentile(fin, 90)), 2) if len(fin) else None),
        "opponent_rate_pct": {f"r{int(r)}px": round(100.0 * float((arr <= r).mean()), 2) for r in RADII},
    }


def main():
    print(f"[e15] vm avail {vm_avail_gb():.2f} GB", flush=True)
    report = {"bands": {"true": [TRUE_LO, TRUE_HI], "ghost": [GHOST_LO, GHOST_HI]},
              "radii_px": list(RADII), "pixel_space": "camera 3840x2160 (db==images.bin, E13-verified bit-identical)",
              "unavailable_sources": {
                  "floor_rescue_loftr_cap51": "NOT AVAILABLE - floor_plane_sweep experiment is cap50-only",
                  "weaktex_recall": "NOT FOUND anywhere in worktree (find -iname '*weaktex*' empty) - unmappable"},
              "caps": {}}
    for cap in ("cap51", "cap50"):
        bands, imgs = load_band_obs(cap)
        del_imgs_note = len(imgs)
        sources = {
            "e6_injected": cov_e6(cap, True),
            "e6_candidate_pool": cov_e6(cap, False),
        }
        if cap == "cap50":
            report["floor_frame_mapping_worst_pose_diff"] = verify_floor_frame_mapping(imgs)
            sources["floor_rescue_loftr_raw"] = cov_floor_loftr()
            a, b = sources["e6_candidate_pool"]
            c, d = sources["floor_rescue_loftr_raw"]
            sources["union_all"] = (np.concatenate([a, c]), np.concatenate([b, d]))
        capr = {"n_images": del_imgs_note, "sources": {}}
        for sname, (ciid, cxy) in sources.items():
            entry = {"n_cov_obs": int(len(ciid)), "n_cov_frames": int(len(np.unique(ciid)))}
            for bname in ("ghost", "true"):
                entry[bname] = nearest_per_point(bands[bname], ciid, cxy)
            capr["sources"][sname] = entry
            print(f"[e15] {cap} {sname}: ghost r16 {entry['ghost']['opponent_rate_pct']['r16px']}% "
                  f"| true r16 {entry['true']['opponent_rate_pct']['r16px']}%", flush=True)
        report["caps"][cap] = capr
        del bands, imgs, sources
    report["vm_avail_gb_end"] = round(vm_avail_gb(), 2)
    out = os.path.join(ANA, "e15_confluence.json")
    json.dump(report, open(out, "w"), indent=1)
    print(f"[e15] wrote {out}", flush=True)


if __name__ == "__main__":
    main()
