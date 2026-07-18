#!/usr/bin/env python3.11
"""E4 · self-consistency validation + device-delivery reconciliation for the
cap40/cap41 (and cap51 control) host replays.

Per cap:
  A. SELF-CONSISTENCY (the acceptance gate that FAILED on device meta poses):
     - per-pair median Sampson px over db two_view_geometries inlier matches,
       evaluated with REPLAY poses (identical metric to
       S1_twoview_lifecycle/cap4x/db_meta_consistency.json: p10/p50/p90 of
       per-pair medians + frac pairs with median < 3 px).
     - track reprojection: reproject every points3D.bin observation with replay
       poses; median/mean px. Must land ~1 px (cap50/51 order) to PASS.
  B. RECONCILIATION vs device-delivered PLY (same gauge, NO Sim3, per memory
     anchor): point counts, floor-slab thickness proxy (same ruler as S1
     build_candidate), symmetric NN distance quantiles.

Reads frozen inputs read-only; writes ONLY into this experiment directory.
"""
import json, os, struct, sqlite3, sys
import numpy as np
from scipy.spatial import cKDTree

E4 = os.path.dirname(os.path.abspath(__file__))
ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
S1 = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/S1_twoview_lifecycle"
sys.path.insert(0, S1)
import build_candidate as bc  # reuse frozen floor/thickness ruler + ply reader

MAX_IMAGE_ID = 2147483647

CAPS = {
    "cap51_control": {
        "db": f"{ROOT}/experiments/rs_replication_deepresearch_2026-07-19/DR6_rounds_curve/input/sfm_live.db",
        "device_ply": f"{ROOT}/data/pocketworld_captures/cap51/device_full_pull_2026-07-17/sfm_sparse.ply",
    },
    "cap40": {
        "db": f"{ROOT}/data/pocketworld_captures/cap40/device_full_pull_2026-07-17/sfm_live.db",
        "device_ply": f"{ROOT}/data/pocketworld_captures/cap40/device_full_pull_2026-07-17/sfm_sparse.ply",
    },
    "cap41": {
        "db": f"{ROOT}/data/pocketworld_captures/cap41/device_db_pull_2026-07-17/sfm_live.db",
        "device_ply": f"{ROOT}/data/pocketworld_captures/cap41/device_db_pull_2026-07-17/sfm_sparse.ply",
    },
}


def read_cameras_bin(p):
    cams = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            cid, model, w, h = struct.unpack("<iiQQ", f.read(24))
            nparams = {0: 3, 1: 4, 2: 4, 3: 5, 4: 8}[model]
            params = np.frombuffer(f.read(8 * nparams), dtype="<f8")
            cams[cid] = {"model": model, "w": w, "h": h, "params": params}
    return cams


def read_images_bin(p):
    imgs = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid, qw, qx, qy, qz, tx, ty, tz, cam = struct.unpack("<I7dI", f.read(64))
            name = b""
            while True:
                c = f.read(1)
                if c == b"\x00":
                    break
                name += c
            npts = struct.unpack("<Q", f.read(8))[0]
            xys = np.frombuffer(f.read(24 * npts), dtype=np.dtype(
                [("x", "<f8"), ("y", "<f8"), ("pid", "<u8")]))
            imgs[iid] = {"q": np.array([qw, qx, qy, qz]),
                         "t": np.array([tx, ty, tz]), "cam": cam,
                         "name": name.decode(), "xys": xys}
    return imgs


def read_points3d_bin(p):
    pts = []
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            pid = struct.unpack("<Q", f.read(8))[0]
            xyz = np.frombuffer(f.read(24), dtype="<f8").copy()
            rgb = np.frombuffer(f.read(3), dtype="u1").copy()
            (err,) = struct.unpack("<d", f.read(8))
            (tl,) = struct.unpack("<Q", f.read(8))
            track = np.frombuffer(f.read(8 * tl), dtype=np.dtype(
                [("iid", "<u4"), ("p2d", "<u4")]))
            pts.append((pid, xyz, rgb, err, track))
    return pts


def sampson_check(db_path, imgs, K):
    """Identical metric to S1 db_meta_consistency: per-pair median Sampson px
    over inlier two_view_geometries, using the given poses."""
    Kinv = np.linalg.inv(K)
    # frame_id (=db image_id - 1) -> R,t from replay bin (name frame_%06d.jpg)
    pose = {}
    for iid, im in imgs.items():
        fid = int(im["name"].split("_")[1].split(".")[0])
        pose[fid] = (bc.quat_to_R(im["q"]), im["t"])
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    c = db.cursor()
    kp = {}
    for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
        arr = np.frombuffer(data, dtype=np.float32).reshape(r, cols)
        kp[iid] = arr[:, :2].astype(np.float64)
    per_pair_med = []
    n_skipped = 0
    for pair_id, r, cols, data in c.execute(
            "SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0"):
        i1, i2 = pair_id // MAX_IMAGE_ID, pair_id % MAX_IMAGE_ID
        f1, f2 = i1 - 1, i2 - 1
        if f1 not in pose or f2 not in pose:
            n_skipped += 1
            continue
        m = np.frombuffer(data, dtype=np.uint32).reshape(r, cols)
        R1, t1 = pose[f1]
        R2, t2 = pose[f2]
        R = R2 @ R1.T
        t = t2 - R @ t1
        tx = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])
        F = Kinv.T @ (tx @ R) @ Kinv
        x1 = np.hstack([kp[i1][m[:, 0]], np.ones((r, 1))])
        x2 = np.hstack([kp[i2][m[:, 1]], np.ones((r, 1))])
        Fx1 = x1 @ F.T
        Ftx2 = x2 @ F
        num = np.einsum("ij,ij->i", x2, Fx1) ** 2
        den = Fx1[:, 0]**2 + Fx1[:, 1]**2 + Ftx2[:, 0]**2 + Ftx2[:, 1]**2
        d = np.sqrt(num / np.maximum(den, 1e-12))
        per_pair_med.append(float(np.median(d)))
    db.close()
    a = np.array(per_pair_med)
    return {
        "n_pairs_tested": len(a),
        "n_pairs_skipped_unregistered": n_skipped,
        "per_pair_median_sampson_px": {
            "p10": round(float(np.percentile(a, 10)), 3),
            "p50": round(float(np.percentile(a, 50)), 3),
            "p90": round(float(np.percentile(a, 90)), 3),
        },
        "frac_pairs_lt3px": round(float((a < 3.0).mean()), 4),
    }


def track_reproj(imgs, pts, K):
    errs = []
    for pid, xyz, rgb, err, track in pts:
        for iid, p2d in track:
            im = imgs[int(iid)]
            R, t = bc.quat_to_R(im["q"]), im["t"]
            Xc = R @ xyz + t
            if Xc[2] <= 0:
                continue
            u = K[0, 0] * Xc[0] / Xc[2] + K[0, 2]
            v = K[1, 1] * Xc[1] / Xc[2] + K[1, 2]
            xy = im["xys"][int(p2d)]
            errs.append(np.hypot(u - xy["x"], v - xy["y"]))
    e = np.array(errs)
    return {"n_obs": len(e),
            "reproj_px_median": round(float(np.median(e)), 4),
            "reproj_px_mean": round(float(np.mean(e)), 4),
            "reproj_px_p90": round(float(np.percentile(e, 90)), 4)}


def cloud_compare(rx, device_ply):
    # rx = replay finalize model points (points3D.bin). NOTE: this exe build's
    # cloud.ply is a ~13-20k live/preview subset (DR6's Jul-14 frozen exe wrote
    # the full finalize cloud there); points3D.bin == RESULT n_points is the
    # finalize cloud and is what the cap51 precedent (65,658 vs 64,392) compared.
    dx, _ = bc.read_ply_xyzrgb(device_ply)
    out = {"replay_n_points": len(rx), "device_n_points": len(dx),
           "n_ratio_replay_over_device": round(len(rx) / len(dx), 4)}
    for tag, xyz in (("replay", rx), ("device", dx)):
        yf = bc.detect_floor_y(xyz)
        fm = bc.floor_metrics(xyz, yf)
        out[f"{tag}_floor_y"] = round(yf, 4)
        out[f"{tag}_thickness_med_cell_p90p10_m"] = fm["thickness_med_cell_p90p10_m"]
        out[f"{tag}_cover_area_m2"] = fm.get("cover_area_m2")
    # symmetric NN, same gauge, no alignment (Sim3 forbidden per memory anchor)
    td, tr = cKDTree(dx), cKDTree(rx)
    d_r2d, _ = td.query(rx, k=1)
    d_d2r, _ = tr.query(dx, k=1)
    out["nn_replay_to_device_m"] = {
        "p50": round(float(np.median(d_r2d)), 5),
        "p90": round(float(np.percentile(d_r2d, 90)), 5)}
    out["nn_device_to_replay_m"] = {
        "p50": round(float(np.median(d_d2r)), 5),
        "p90": round(float(np.percentile(d_d2r, 90)), 5)}
    # gauge diagnostics (device full re-solve may live in a different gauge)
    for tag, xyz in (("replay", rx), ("device", dx)):
        out[f"{tag}_centroid"] = [round(float(v), 3) for v in xyz.mean(0)]
        out[f"{tag}_bbox_extent_m"] = [round(float(v), 3) for v in
                                       (xyz.max(0) - xyz.min(0))]
    return out


def main():
    caps = sys.argv[1:] or ["cap51_control", "cap40", "cap41"]
    summary = {}
    for cap in caps:
        run = f"{E4}/runs/{cap}"
        cfg = CAPS[cap]
        print(f"=== {cap} ===", flush=True)
        cams = read_cameras_bin(f"{run}/cameras.bin")
        imgs = read_images_bin(f"{run}/images.bin")
        pts = read_points3d_bin(f"{run}/points3D.bin")
        cam = cams[next(iter(cams))]
        assert cam["model"] == 0, f"expected SIMPLE_PINHOLE, got {cam['model']}"
        f_, cx_, cy_ = cam["params"]
        K = np.array([[f_, 0, cx_], [0, f_, cy_], [0, 0, 1]])
        res = {"cap": cap, "n_registered_images": len(imgs), "n_points3d": len(pts)}
        res["sampson_vs_pulled_db"] = sampson_check(cfg["db"], imgs, K)
        res["track_reproj_replay_poses"] = track_reproj(imgs, pts, K)
        # export the finalize model as a PLY artifact (for compare.html eyeballing)
        rxyz = np.stack([p[1] for p in pts])
        rrgb = np.stack([p[2] for p in pts])
        bc.write_ply_xyzrgb(f"{run}/replay_finalize.ply", rxyz, rrgb,
                            f"E4 host replay finalize model {cap} (points3D.bin)")
        res["cloud_vs_device_delivery"] = cloud_compare(rxyz, cfg["device_ply"])
        s = res["sampson_vs_pulled_db"]["per_pair_median_sampson_px"]["p50"]
        r = res["track_reproj_replay_poses"]["reproj_px_median"]
        res["self_consistency_verdict"] = (
            "PASS" if (s < 3.0 and r < 3.0) else "FAIL")
        json.dump(res, open(f"{run}/consistency.json", "w"), indent=2)
        print(json.dumps(res, indent=2), flush=True)
        summary[cap] = res
    json.dump(summary, open(f"{E4}/consistency_summary.json", "w"), indent=2)
    print("VALIDATION DONE", flush=True)


if __name__ == "__main__":
    main()
