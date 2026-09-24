#!/usr/bin/env python3
"""expAC: Q3 re-windowing experiment — does cutting windows at the
expAA span plateau (cap diameter 44°, FPS-18 per cap) lift window conf
(11.81 -> ~12.5 expected on good content) and shrink per-window scale
error / cross-window residuals?

Old cut (baseline): spatial-order stride-9 K18 windows (win025 conf
11.81, achieved span 40.5°, but span varies uncontrolled per window).
New cut: FPS window centers over capture directions, accept a center
iff >=18 frames within the 44° cap AND >=18° from accepted centers;
frames per window = FPS-18 inside the cap (frame reuse across windows
allowed, mirroring production 1-ring windows).

Per window: official DA3 K18@896 (umeyama captured) -> production
Fix B (da3_window_scale_fixb module, cached 29k anchors) -> conf +
adjacent-pair PRE/POST-B residuals + merged pre/postB PLYs.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import da3_window_scale_fixb as fixb  # noqa: E402

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
ANCHOR_CACHE = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
OUT_DIR = Path("data/expAC_rewindow_span_2026_06_13")
WIN_DIR = OUT_DIR / "windows"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WIN_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "expAC_results.jsonl"
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"

# expAD-measured comfort band: both contents peak at 40-48° achieved
# span, collapse begins ~50-53° -> caps stop at 50 so achieved span
# can never enter the danger zone.
CAP_DIAM_LADDER = (44.0, 47.0, 50.0)
MIN_SPAN_DEG = 40.0                          # HARD floor (expAD peak band)
MIN_CENTER_SEP_DEG = 18.0
CONF_PCT = 40.0
GATE_LOG_RATIO = np.log(2.0)
MEAS_STRIDE = 3


def log(m):
    print(f"[expAC {time.strftime('%H:%M:%S')}] {m}", flush=True)


def append_row(row):
    with OUT.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: (fr["azimuth"], fr["elevation"]) for fr in bundle["frames"]}


def unit(az, el):
    return np.array([np.cos(el) * np.cos(az), np.sin(el), np.cos(el) * np.sin(az)])


frames, dirs = [], []
for r in man:
    fn = r["jpegPath"].split("/")[-1]
    if fn in azel:
        frames.append(r)
        dirs.append(unit(*azel[fn]))
dirs = np.stack(dirs)
log(f"frames with directions: {len(frames)}")

# ------------------------------------------------------------ window cut
COS_SEP = np.cos(np.radians(MIN_CENTER_SEP_DEG))


def fps18(cand_idx, center):
    d2c = dirs[cand_idx] @ center
    chosen = [int(np.argmax(d2c))]
    while len(chosen) < 18:
        sel = dirs[cand_idx][chosen]
        dmin = (dirs[cand_idx] @ sel.T).max(axis=1)
        dmin[chosen] = 2.0
        chosen.append(int(np.argmin(dmin)))
    return [cand_idx[i] for i in chosen]


def build_window(c):
    """Adaptive cap: widen within the expAA plateau until the FPS-18
    achieved span clears the hard floor; None if it never does."""
    best = None
    for diam in CAP_DIAM_LADDER:
        cand = np.where(dirs @ c >= np.cos(np.radians(diam / 2)))[0]
        if len(cand) < 18:
            continue
        pick = fps18(list(cand), c)
        us = dirs[pick]
        span = float(np.degrees(np.arccos(np.clip((us @ us.T).min(), -1, 1))))
        best = {"frame_idx": [int(j) for j in pick], "span_deg": span,
                "cap_deg": diam, "n_avail": int(len(cand))}
        if span >= MIN_SPAN_DEG:
            return best
    return {"rejected": True, **(best or {"span_deg": None})}


def cut_windows():
    mean = dirs.mean(axis=0)
    mean /= np.linalg.norm(mean)
    order = [int(np.argmax(dirs @ mean))]
    while len(order) < len(dirs):
        sel = dirs[order]
        dmin = (dirs @ sel.T).max(axis=1)
        dmin[order] = 2.0
        order.append(int(np.argmin(dmin)))
    centers, windows, dropped = [], [], []
    for idx in order:
        c = dirs[idx]
        if centers and max(cc @ c for cc in centers) > COS_SEP:
            continue
        w = build_window(c)
        if w.get("rejected"):
            dropped.append({"center": c.tolist(), "best_span": w.get("span_deg")})
            continue
        centers.append(c)
        windows.append({"center": c.tolist(), **w})
    # coverage accounting: frames within any accepted window's cap
    covered = set()
    for w in windows:
        covered.update(w["frame_idx"])
        cc = np.asarray(w["center"])
        covered.update(np.where(dirs @ cc >= np.cos(np.radians(w["cap_deg"] / 2)))[0].tolist())
    log(f"dropped centers (span floor {MIN_SPAN_DEG}°): {len(dropped)} "
        f"best_spans={[round(d['best_span'],1) if d['best_span'] else None for d in dropped]}")
    log(f"frame coverage: {len(covered)}/{len(dirs)}")
    append_row({"kind": "cut_audit", "dropped": dropped,
                "frames_covered": len(covered), "frames_total": len(dirs)})
    return windows


windows = cut_windows()
log(f"new cut: {len(windows)} windows, spans {[round(w['span_deg'], 1) for w in windows]}")
for i, w in enumerate(windows):
    append_row({"kind": "window_def", "win": i, "span_deg": w["span_deg"],
                "n_avail": w["n_avail"], "frame_idx": w["frame_idx"]})

# adjacent pairs by center angular proximity (chain along arc)
cs = np.stack([np.asarray(w["center"]) for w in windows])
pairs = []
for a in range(len(windows)):
    for b in range(a + 1, len(windows)):
        ang = np.degrees(np.arccos(np.clip(cs[a] @ cs[b], -1, 1)))
        if ang < 30.0:
            pairs.append((a, b))
log(f"adjacent pairs: {pairs}")


# ------------------------------------------------------------ inference
def run_all():
    todo = [i for i in range(len(windows)) if not (WIN_DIR / f"win_{i:02d}.npz").exists()]
    if not todo:
        return
    import torch
    from da3base_official_streaming_oracle import install_mps_chunked_sdpa
    install_mps_chunked_sdpa(torch, 256, 4.0)
    from depth_anything_3.api import DepthAnything3
    from depth_anything_3.utils.pose_align import align_poses_umeyama

    last = {"v": None}

    def _align(self, extrinsics, intrinsics, prediction,
               align_to_input_ext_scale=True, ransac_view_thresh=10):
        if extrinsics is None:
            return prediction
        prediction.intrinsics = intrinsics.numpy()
        _, _, scale, aligned = align_poses_umeyama(
            prediction.extrinsics, extrinsics.numpy(),
            ransac=len(extrinsics) >= ransac_view_thresh,
            return_aligned=True, random_state=42)
        last["v"] = float(scale)
        if align_to_input_ext_scale:
            prediction.extrinsics = extrinsics[..., :3, :].numpy()
            prediction.depth /= scale
        else:
            prediction.extrinsics = aligned
        return prediction

    DepthAnything3._align_to_input_extrinsics_intrinsics = _align
    log(f"loading DA3-BASE for {len(todo)} windows …")
    model = DepthAnything3.from_pretrained(
        "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE"
    ).to(device=torch.device("mps"))
    model.model.eval()
    for n_done, i in enumerate(todo):
        rows = [frames[j] for j in windows[i]["frame_idx"]]
        paths = [str(D / "capture_seq_k35_strict" / r["jpegPath"]) for r in rows]
        ext = np.stack([np.asarray(r["cameraExtrinsic4x4"], np.float32).reshape(4, 4) for r in rows])
        ixt = np.stack([np.asarray(
            [[r["cameraIntrinsicFxFyCxCy"][0], 0, r["cameraIntrinsicFxFyCxCy"][2]],
             [0, r["cameraIntrinsicFxFyCxCy"][1], r["cameraIntrinsicFxFyCxCy"][3]],
             [0, 0, 1]], np.float32) for r in rows])
        t0 = time.time()
        pred = model.inference(paths, extrinsics=ext, intrinsics=ixt,
                               align_to_input_ext_scale=True,
                               process_res=896, process_res_method="upper_bound_resize")
        cm = float(np.median(np.asarray(pred.conf)))
        np.savez_compressed(WIN_DIR / f"win_{i:02d}.npz",
                            depth=np.asarray(pred.depth, np.float32),
                            conf=np.asarray(pred.conf, np.float16),
                            K=np.asarray(pred.intrinsics, np.float32),
                            w2c=ext)
        log(f"win{i:02d} inferred ({n_done+1}/{len(todo)}) in {time.time()-t0:.0f}s, "
            f"span {windows[i]['span_deg']:.1f}°, umeyama={last['v']:.4f}, conf_med={cm:.2f}")
        append_row({"kind": "window_run", "win": i, "span_deg": windows[i]["span_deg"],
                    "umeyama_scale": last["v"], "conf_median": cm,
                    "infer_s": time.time() - t0})


def load_win(i):
    z = np.load(WIN_DIR / f"win_{i:02d}.npz")
    return {"depth": z["depth"].astype(np.float32), "conf": z["conf"].astype(np.float32),
            "K": z["K"].astype(np.float64), "w2c": z["w2c"].astype(np.float64)}


# ------------------------------------------------------------ measurement
def backproject(win, stride, s):
    depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    pts = []
    for i in range(n):
        z = depth[i] * s
        m = (conf[i] >= floor) & (z > 1e-3)
        vs, us = np.where(m)
        sel = (vs % stride == 0) & (us % stride == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs):
            continue
        K = Ks[i]
        zz = z[vs, us].astype(np.float64)
        x = (us + 0.5 - K[0, 2]) / K[0, 0] * zz
        y = (vs + 0.5 - K[1, 2]) / K[1, 1] * zz
        cam = np.stack([x, y, zz, np.ones_like(zz)])
        c2w = np.linalg.inv(w2cs[i])
        pts.append((c2w @ cam)[:3].T)
    return np.concatenate(pts)


def pair_residual(src_pts, dst, s_dst):
    depth, conf, Ks, w2cs = dst["depth"], dst["conf"], dst["K"], dst["w2c"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    ratios, absd = [], []
    for i in range(n):
        w2c = w2cs[i]
        cam = (w2c[:3, :3] @ src_pts.T + w2c[:3, 3:4])
        zw = cam[2]
        front = zw > 1e-3
        K = Ks[i]
        u = cam[0] / zw * K[0, 0] + K[0, 2] - 0.5
        v = cam[1] / zw * K[1, 1] + K[1, 2] - 0.5
        ui, vi = np.round(u).astype(int), np.round(v).astype(int)
        ok = front & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        if not ok.any():
            continue
        zd = depth[i][vi[ok], ui[ok]].astype(np.float64) * s_dst
        cd = conf[i][vi[ok], ui[ok]]
        zp = zw[ok]
        good = (cd >= floor) & (zd > 1e-3)
        r = np.log(zd[good] / zp[good])
        keep = np.abs(r) <= GATE_LOG_RATIO
        ratios.append(r[keep])
        absd.append(np.abs(zd[good][keep] - zp[good][keep]))
    if not ratios:
        return {"n": 0}
    r = np.concatenate(ratios)
    a = np.concatenate(absd)
    return {"n": int(len(r)),
            "abs_rel_median_pct": float(np.median(np.abs(np.expm1(r))) * 100),
            "abs_rel_p90_pct": float(np.percentile(np.abs(np.expm1(r)), 90) * 100),
            "abs_cm_median": float(np.median(a) * 100)}


def write_ply_merged(name, scales):
    path = DELIVER / name
    fh = open(path, "wb")
    header = ("ply\nformat binary_little_endian 1.0\n"
              "element vertex 000000000000\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "end_header\n")
    fh.write(header.encode("ascii"))
    count = 0
    for i in range(len(windows)):
        win = load_win(i)
        rows = [frames[j] for j in windows[i]["frame_idx"]]
        depth, conf, Ks, w2cs = win["depth"], win["conf"], win["K"], win["w2c"]
        n, H, W = depth.shape
        floor = np.percentile(conf, CONF_PCT)
        for k in range(n):
            z0 = depth[k] * scales[i]
            m = (conf[k] >= floor) & (z0 > 1e-3)
            vs, us = np.where(m)
            if not len(vs):
                continue
            img = cv2.imread(str(D / "capture_seq_k35_strict" / rows[k]["jpegPath"]))
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
            cols = img[vs, us][:, ::-1]
            K = Ks[k]
            zz = z0[vs, us].astype(np.float64)
            x = (us + 0.5 - K[0, 2]) / K[0, 0] * zz
            y = (vs + 0.5 - K[1, 2]) / K[1, 1] * zz
            cam = np.stack([x, y, zz, np.ones_like(zz)])
            c2w = np.linalg.inv(w2cs[k])
            pts = (c2w @ cam)[:3].T.astype(np.float32)
            rec = np.empty(len(pts), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
            rec["xyz"], rec["rgb"] = pts, cols
            fh.write(rec.tobytes())
            count += len(pts)
    fh.close()
    with open(path, "r+b") as f2:
        data = f2.read(200)
        idx = data.find(b"000000000000")
        f2.seek(idx)
        f2.write(f"{count:012d}".encode("ascii"))
    log(f"{name}: {count:,} pts")
    append_row({"kind": "ply", "file": name, "pts": count})


def main():
    run_all()

    z = np.load(ANCHOR_CACHE)
    anchors = fixb.AnchorSet(z["pts"], z["obs_frame"], z["obs_uv"], z["obs_aidx"])
    fits, confs = [], []
    for i in range(len(windows)):
        win = load_win(i)
        s, n_obs = fixb.fit_window_scale(anchors, win["depth"], win["conf"],
                                         win["w2c"], windows[i]["frame_idx"])
        cm = float(np.median(win["conf"]))
        fits.append((s, n_obs))
        confs.append(cm)
        log(f"win{i:02d}: conf_med={cm:.2f}, s_B={s if s is None else round(s,4)} (obs {n_obs})")
    scales = fixb.authorize_scales(fits, confs)
    append_row({"kind": "scales", "s_B": scales, "conf_medians": confs,
                "n_authorized": sum(1 for i in range(len(windows))
                                    if fits[i][0] is not None and confs[i] >= 6.0)})

    pre_meds, post_meds = [], []
    for a, b in pairs:
        wa, wb = load_win(a), load_win(b)
        pa = backproject(wa, MEAS_STRIDE, 1.0)
        r0 = pair_residual(pa, wb, 1.0)
        pa = backproject(wa, MEAS_STRIDE, scales[a])
        r1 = pair_residual(pa, wb, scales[b])
        pre_meds.append(r0.get("abs_rel_median_pct"))
        post_meds.append(r1.get("abs_rel_median_pct"))
        log(f"pair {a}-{b}: PRE {r0} POST-B {r1}")
        append_row({"kind": "pair", "pair": [a, b], "pre": r0, "postB": r1})
    log(f"SUMMARY: conf_med list {[round(c,2) for c in confs]}")
    log(f"SUMMARY: PRE median {np.median([m for m in pre_meds if m]):.3f}% "
        f"POST-B median {np.median([m for m in post_meds if m]):.3f}%")
    append_row({"kind": "summary",
                "conf_medians": confs,
                "pre_median_pct": float(np.median([m for m in pre_meds if m])),
                "postB_median_pct": float(np.median([m for m in post_meds if m]))})

    write_ply_merged("rewin_pre.ply", [1.0] * len(windows))
    write_ply_merged("rewin_postB.ply", scales)
    log("EXPAC-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
