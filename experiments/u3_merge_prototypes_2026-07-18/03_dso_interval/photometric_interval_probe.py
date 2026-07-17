#!/usr/bin/env python3
"""#3b Photometric inverse-depth interval probe — cap50 (diagnostic only).

Companion to dso_interval_gate.py. That script showed the *geometric* DSO interval
(w_rel prop 1/parallax) reduces to a sub-2deg angle threshold and therefore cannot
hold anything the fixed 2deg gate borns. The interval that actually matures a point
in DSO is the *photometric* epipolar-search interval: the range of inverse depth
whose multi-view ZNCC stays within a margin of the best. This probe measures that
profile on a FROZEN, deterministically-selected sample so the immaturity mechanism
can be inspected on real cap50 geometry.

For each sample point we take the closest observing view as reference, cast the ray
through its keypoint, scan inverse depth, project the hypothesis into every other
observing view, and compute a block-matching multi-view ZNCC vs the reference patch.
We report, per point:
  * geometric interval half-width  w_geo = (sigma_px/f)/sin(parallax)
  * photometric interval rel-width = idepth range within `margin` of the ZNCC peak
  * number of ZNCC modes (search multimodality)
  * peak ZNCC and whether the peak sits at the triangulated inverse depth

HONEST EXPECTATION (to be confirmed/refuted by the numbers, not assumed):
  - well-constrained high-parallax control -> single sharp peak, narrow photometric
    interval -> mature.
  - genuine low-parallax 2-view point -> flat/multimodal profile, wide photometric
    interval -> correctly held immature (mechanism does real work where geometry alone
    cannot).
  - chair-ROI point -> if photometrically consistent at its depth the interval is
    ALSO narrow and the probe will NOT flag it, reproducing #5 / section 7.5 (needs
    free-space/opposition, not any single-ray interval).

Not a production candidate, not a threshold, no self-approval.
Memory-safe: 4K images loaded per-point and released; resident image cap enforced.
"""
from __future__ import annotations

import hashlib
import json
import os
import resource
import sqlite3
import time
from collections import defaultdict, OrderedDict
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
CAP = BASE / "data/pocketworld_captures/cap50/device_full_pull_2026-07-17"
DB = CAP / "sfm_live.db"
META = CAP / "sfm_sparse_meta.json"
LEDGER = CAP / "sfm_fed_frames.jsonl"
PHOTOS = CAP / "photos_highres"

NKP = 8192
ROI_X = (0.25, 1.05)
ROI_Z = (-1.70, -0.55)
SIGMA_PX = 3.0
PATCH_HALF = 3          # 7x7 window
PATCH_STEP = 2.0        # px between taps -> 12px support
N_SCAN = 161            # inverse-depth samples
SCAN_LO, SCAN_HI = 0.35, 2.8   # multiplicative range around triangulated depth
MARGIN = 0.05           # ZNCC margin defining the mature interval
MAX_RESIDENT = 10       # image cache cap
GRAY = np.array([0.299, 0.587, 0.114])
SAMPLES_PER_CLASS = 5
SEED_DOMAIN = "pocketworld:dso-photometric-probe:v1"


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


class ImageCache:
    def __init__(self, paths, cap):
        self.paths = paths
        self.cap = cap
        self.store = OrderedDict()

    def gray(self, fid):
        if fid in self.store:
            self.store.move_to_end(fid)
            return self.store[fid]
        with Image.open(self.paths[fid]) as im:
            arr = np.asarray(im.convert("RGB"), dtype=np.float32)
        g = arr @ GRAY
        self.store[fid] = g
        if len(self.store) > self.cap:
            self.store.popitem(last=False)
        return g


def bilinear(img, xy):
    x = xy[:, 0]
    y = xy[:, 1]
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1 = x0 + 1
    y1 = y0 + 1
    inb = (x0 >= 0) & (y0 >= 0) & (x1 < img.shape[1]) & (y1 < img.shape[0])
    x0c = np.clip(x0, 0, img.shape[1] - 1)
    x1c = np.clip(x1, 0, img.shape[1] - 1)
    y0c = np.clip(y0, 0, img.shape[0] - 1)
    y1c = np.clip(y1, 0, img.shape[0] - 1)
    wx = x - x0
    wy = y - y0
    v = (img[y0c, x0c] * (1 - wx) * (1 - wy) + img[y0c, x1c] * wx * (1 - wy)
         + img[y1c, x0c] * (1 - wx) * wy + img[y1c, x1c] * wx * wy)
    return v, inb


def patch_grid(uv):
    off = np.arange(-PATCH_HALF, PATCH_HALF + 1) * PATCH_STEP
    gx, gy = np.meshgrid(off, off)
    return np.stack([uv[0] + gx.ravel(), uv[1] + gy.ravel()], 1)


def zncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        return -1.0
    return float((a @ b) / (na * nb))


def build_tracks_with_obs(con, K, R_, t_, C_, P_, Kinv, has_img):
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
        for a, b in m:
            na, nb = id1 * NKP + int(a), id2 * NKP + int(b)
            ra, rb = find(na), find(nb)
            if ra != rb:
                parent[ra] = rb
            seen.add(na)
            seen.add(nb)
    groups = defaultdict(list)
    for node in seen:
        groups[find(node)].append(node)

    out = []
    for nodes in groups.values():
        byimg = {}
        for n in nodes:
            img = n // NKP
            if img not in byimg:
                byimg[img] = n % NKP
        obs = []
        for img, kp in byimg.items():
            fid = img - 1
            if fid in R_ and has_img.get(fid):
                obs.append((fid, KP[img][kp].copy()))
        if len(obs) < 2:
            continue
        A = []
        for fid, uv in obs:
            x = Kinv @ np.array([uv[0], uv[1], 1.0])
            A.append(x[0] * P_[fid][2] - x[2] * P_[fid][0])
            A.append(x[1] * P_[fid][2] - x[2] * P_[fid][1])
        _, _, Vt = np.linalg.svd(np.array(A))
        X = Vt[-1][:3] / Vt[-1][3]
        errs, fronts, Cs, depths = [], [], [], []
        for fid, uv in obs:
            cam = R_[fid] @ X + t_[fid]
            fronts.append(cam[2] > 0)
            depths.append(cam[2])
            p = K @ cam
            errs.append(float(np.hypot(*(p[:2] / p[2] - uv))))
            Cs.append(C_[fid])
        if not all(fronts) or np.median(errs) > 4.0:
            continue
        Cs = np.array(Cs)
        rays = X - Cs
        rays /= np.linalg.norm(rays, axis=1, keepdims=True) + 1e-12
        cos = np.clip(rays @ rays.T, -1, 1)
        maxpar = float(np.degrees(np.arccos(cos))[np.triu_indices(len(obs), 1)].max())
        out.append({"X": X, "obs": obs, "nviews": len(obs), "maxpar": maxpar,
                    "reproj": float(np.mean(errs)), "depths": depths})
    return out


def scan_point(rec, cache, R_, t_, C_, K, f_px):
    obs = rec["obs"]
    depths = rec["depths"]
    ref_i = int(np.argmin(depths))
    ref_fid, ref_uv = obs[ref_i]
    ref_img = cache.gray(ref_fid)
    ref_patch, ref_inb = bilinear(ref_img, patch_grid(ref_uv))
    if not ref_inb.all():
        return None
    Cref = C_[ref_fid]
    X = rec["X"]
    dir_w = X - Cref
    s_tri = np.linalg.norm(dir_w)
    dir_w = dir_w / s_tri
    others = [obs[j][0] for j in range(len(obs)) if j != ref_i]
    s_vals = s_tri * np.linspace(SCAN_LO, SCAN_HI, N_SCAN)
    idepth = 1.0 / s_vals
    cost = np.full(N_SCAN, np.nan)
    for k, s in enumerate(s_vals):
        Xh = Cref + s * dir_w
        vals = []
        for fid in others:
            cam = R_[fid] @ Xh + t_[fid]
            if cam[2] <= 0.05:
                continue
            center = (K @ cam)[:2] / cam[2]
            patch, inb = bilinear(cache.gray(fid), patch_grid(center))
            if not inb.all():
                continue
            vals.append(zncc(ref_patch, patch))
        if vals:
            cost[k] = float(np.mean(vals))
    valid = ~np.isnan(cost)
    if valid.sum() < 5:
        return None
    ci = np.where(valid, cost, -np.inf)
    kbest = int(np.argmax(ci))
    zmax = float(ci[kbest])
    id_best = float(idepth[kbest])
    id_tri = 1.0 / s_tri
    # mature interval: contiguous run around peak with cost >= zmax - MARGIN
    lo = kbest
    while lo - 1 >= 0 and valid[lo - 1] and ci[lo - 1] >= zmax - MARGIN:
        lo -= 1
    hi = kbest
    while hi + 1 < N_SCAN and valid[hi + 1] and ci[hi + 1] >= zmax - MARGIN:
        hi += 1
    id_hi = idepth[lo]  # idepth decreases with s index; idepth[lo] is larger
    id_lo = idepth[hi]
    photo_relwidth = float((id_hi - id_lo) / id_best) if id_best > 0 else None
    # modes: local maxima above zmax-0.10, separated by a dip of >0.03
    thr = zmax - 0.10
    modes = 0
    prev = -np.inf
    rising = False
    above_run = ci >= thr
    # count connected components above threshold that contain a local max
    comp = 0
    inrun = False
    for k in range(N_SCAN):
        if valid[k] and above_run[k]:
            if not inrun:
                comp += 1
                inrun = True
        else:
            inrun = False
    w_geo = (SIGMA_PX / f_px) / max(np.sin(np.radians(rec["maxpar"])), 1e-9)
    return {
        "nviews": rec["nviews"],
        "maxpar_deg": round(rec["maxpar"], 4),
        "reproj_px": round(rec["reproj"], 4),
        "ref_fid": int(ref_fid),
        "n_other_views": len(others),
        "zncc_peak": round(zmax, 4),
        "w_geo_relwidth": round(float(w_geo), 5),
        "photo_relwidth": None if photo_relwidth is None else round(photo_relwidth, 5),
        "photo_modes_above_peak_minus_0.10": int(comp),
        "peak_at_triangulation": bool(abs(np.log(id_best / id_tri)) < np.log(1.15)),
        "idepth_best": round(id_best, 5),
        "idepth_tri": round(float(id_tri), 5),
        "profile_idepth": [round(float(v), 5) for v in idepth[valid]],
        "profile_zncc": [round(float(v), 4) for v in cost[valid]],
        "X": [round(float(v), 5) for v in X],
    }


def main():
    t0 = time.time()
    out = HERE
    log = open(out / "probe.stdout.log", "w")

    def pr(*a):
        s = " ".join(str(x) for x in a)
        print(s)
        log.write(s + "\n")
        log.flush()

    inputs = {p.name: sha256_file(p) for p in (DB, META, LEDGER)}
    pr("inputs:", json.dumps(inputs))

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

    img_path = {}
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        p = PHOTOS / os.path.basename(r["jpegPath"])
        if p.exists():
            img_path[int(r["frameId"])] = p
    has_img = {fid: True for fid in img_path}
    pr("frames with 4K image:", len(img_path))

    pr("building tracks (image-backed obs only)...")
    tracks = build_tracks_with_obs(con, K, R_, t_, C_, P_, Kinv, has_img)
    pr("image-backed tracks:", len(tracks))

    def in_roi(X):
        return ROI_X[0] <= X[0] <= ROI_X[1] and ROI_Z[0] <= X[2] <= ROI_Z[1]

    classes = {
        "lowpar_2view": [r for r in tracks if r["nviews"] == 2 and 0.5 <= r["maxpar"] <= 1.5],
        "highpar_control": [r for r in tracks if r["nviews"] >= 3 and r["maxpar"] >= 15.0],
        "chair_roi_2view": [r for r in tracks if r["nviews"] == 2 and in_roi(r["X"])],
        "chair_roi_multiview": [r for r in tracks if r["nviews"] >= 3 and in_roi(r["X"])],
    }
    # deterministic frozen selection by hash of X
    sample = []
    for cls, recs in classes.items():
        ranked = sorted(recs, key=lambda r: hashlib.sha256(
            (SEED_DOMAIN + "\0" + cls + "\0" + ",".join(f"{v:.6f}" for v in r["X"])).encode()).hexdigest())
        for r in ranked[:SAMPLES_PER_CLASS]:
            sample.append((cls, r))
        pr(f"class {cls}: pool={len(recs)} selected={min(len(recs),SAMPLES_PER_CLASS)}")

    cache = ImageCache(img_path, MAX_RESIDENT)
    rows = []
    for i, (cls, rec) in enumerate(sample):
        res = scan_point(rec, cache, R_, t_, C_, K, float(ff))
        if res is None:
            pr(f"  [{i}] {cls}: skipped (patch out of bounds / too few views)")
            continue
        res["sample_id"] = f"{cls}-{i:02d}"
        res["class"] = cls
        rows.append(res)
        pr(f"  [{i}] {cls}: par={res['maxpar_deg']}deg w_geo={res['w_geo_relwidth']} "
           f"photo_w={res['photo_relwidth']} modes={res['photo_modes_above_peak_minus_0.10']} "
           f"zpeak={res['zncc_peak']} peak_at_tri={res['peak_at_triangulation']}")
        cache.store.clear()  # release between points; keep memory flat

    # summary by class
    summary = {}
    for cls in classes:
        cr = [r for r in rows if r["class"] == cls]
        if not cr:
            summary[cls] = {"n": 0}
            continue
        pw = [r["photo_relwidth"] for r in cr if r["photo_relwidth"] is not None]
        summary[cls] = {
            "n": len(cr),
            "w_geo_median": round(float(np.median([r["w_geo_relwidth"] for r in cr])), 5),
            "photo_relwidth_median": round(float(np.median(pw)), 5) if pw else None,
            "photo_modes_median": float(np.median([r["photo_modes_above_peak_minus_0.10"] for r in cr])),
            "zncc_peak_median": round(float(np.median([r["zncc_peak"] for r in cr])), 4),
            "peak_at_tri_frac": round(float(np.mean([r["peak_at_triangulation"] for r in cr])), 3),
        }

    # write probe jsonl + summary
    with (out / "photometric_probe.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    (out / "photometric_probe_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))

    # viewer: ZNCC vs inverse depth, one panel per class
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cls_list = [c for c in classes if summary[c]["n"]]
    fig, axes = plt.subplots(1, len(cls_list), figsize=(5 * len(cls_list), 4.2), squeeze=False)
    for ax, cls in zip(axes[0], cls_list):
        for r in [x for x in rows if x["class"] == cls]:
            ax.plot(r["profile_idepth"], r["profile_zncc"], lw=1.0, alpha=0.8)
            ax.axvline(r["idepth_tri"], color="k", ls=":", lw=0.6, alpha=0.4)
        ax.set_title(f"{cls}\n(photo_w med={summary[cls]['photo_relwidth_median']}, modes med={summary[cls]['photo_modes_median']})", fontsize=9)
        ax.set_xlabel("inverse depth 1/s (1/m)")
        ax.set_ylabel("multi-view ZNCC")
        ax.set_ylim(-0.2, 1.0)
    fig.suptitle("DSO photometric epipolar-search interval — cap50 frozen sample (dotted = triangulated idepth)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "viewer_photometric_profiles.png", dpi=115)
    plt.close(fig)

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    manifest = {
        "schema": "pocketworld_dso_photometric_interval_probe_v1",
        "kind": "diagnostic_only__frozen_sample__no_self_approval",
        "capture": "cap50",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs_sha256": inputs,
        "params": {"sigma_px": SIGMA_PX, "patch_half": PATCH_HALF, "patch_step_px": PATCH_STEP,
                   "n_scan": N_SCAN, "scan_mult_range": [SCAN_LO, SCAN_HI], "zncc_margin": MARGIN,
                   "samples_per_class": SAMPLES_PER_CLASS, "seed_domain": SEED_DOMAIN,
                   "roi_x": ROI_X, "roi_z": ROI_Z, "max_resident_images": MAX_RESIDENT},
        "n_sampled": len(rows),
        "summary": summary,
        "outputs": {},
        "elapsed_s": round(time.time() - t0, 2),
        "peak_rss_bytes": int(peak),
        "peak_rss_mb": round(peak / (1024 * 1024), 1),
        "APPROXIMATIONS": [
            "Block-matching ZNCC uses an image-aligned 7x7 window in each view (no "
            "homography warp of the patch). Adequate for probing interval width/"
            "multimodality on small windows; not a calibrated MVS cost.",
            "Reference view = closest observing view; ray cast through its keypoint. "
            "Only image-backed observing frames (115/139) are used.",
        ],
    }
    for fn in ("photometric_probe.jsonl", "photometric_probe_summary.json", "viewer_photometric_profiles.png"):
        manifest["outputs"][fn] = sha256_file(out / fn)
    (out / "probe_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    pr("peak RSS MB:", manifest["peak_rss_mb"], "elapsed_s:", manifest["elapsed_s"])
    log.close()


if __name__ == "__main__":
    main()
