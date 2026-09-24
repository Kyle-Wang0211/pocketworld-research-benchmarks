#!/usr/bin/env python3
"""expD: inter-window metric consistency of DA3 K18 windows on a REAL phone capture.

User question (2026-06-12): final reconstructions show cabinet/floor ghosting
(double surfaces). Hypothesis: each DA3 window carries a residual free
scale even AFTER the official per-window metric alignment
(api.py _align_to_input_extrinsics_intrinsics: umeyama(pred_traj, arkit_traj)
-> depth /= scale). This experiment measures, on tonight's capture
cap_1781248804035239 (174 frames, ARKit metric w2c already converted to
OpenCV convention by the app's derivation service):

  1. official per-window umeyama scale (spread across windows),
  2. cross-window depth disagreement on SHARED surfaces (the ghosting,
     in cm and in relative %), BEFORE any extra correction,
  3. the same AFTER one extra overlap-fitted scalar per window
     ("每窗1标量" v2 — median depth-reprojection ratio, window 0 = ref).

Verdict rule agreed with user: if the post-fit residual collapses to ~cm
level, the K18 fusion design + rough-cloud preview are viable and ghosting
has a validated fix; if not, the window fusion design must be rethought.

Outputs (all under data/expD_window_consistency_2026_06_12/):
  expD_results.jsonl     — incremental rows (window defs, scales, pair stats)
  win{i}_{pre|post}.ply  — colored world point clouds per window
  render_*.png           — top-down / side scatter, colored by window,
                           before vs after the overlap fit
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from da3base_official_streaming_oracle import install_mps_chunked_sdpa  # noqa: E402

install_mps_chunked_sdpa(torch, 256, 4.0)

from depth_anything_3.api import DepthAnything3  # noqa: E402
from depth_anything_3.utils.pose_align import align_poses_umeyama  # noqa: E402

CAP = Path("/Users/kaidongwang/Developer/Aether3D-cross/phone_captures_2026_06_12/cap_1781248804035239")
OUT_DIR = Path("data/expD_window_consistency_2026_06_12")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "expD_results.jsonl"

K_PER_WINDOW = 18
CAP_RADIUS_DEG = 22.0          # 1-ring window ≈ 40-48° diameter (expAA optimum)
CENTER_SEP_DEG = (16.0, 30.0)  # adjacent-window center separation band
CONF_PERCENTILE = 40.0         # official GLB default: keep top 60% conf
GATE_LOG_RATIO = np.log(2.0)   # correspondence gate for depth reprojection
MEAS_STRIDE = 3                # pixel stride for measurement clouds
PLY_STRIDE = 3                 # pixel stride for exported PLYs


def log(msg: str) -> None:
    print(f"[expD {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def append_row(row: dict) -> None:
    with OUT.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------- data ----
man = json.loads((CAP / "da3_input_manifest.json").read_text())["frames"]
bundle = json.loads((CAP / "photo_bundle.json").read_text())["frames"]
azel = {f["id"]: (float(f["azimuth"]), float(f["elevation"])) for f in bundle}

frames = [f for f in man if f["id"] in azel]
log(f"frames with pose+azel: {len(frames)}")
max_abs = max(max(abs(a), abs(e)) for a, e in azel.values())
to_rad = np.pi / 180.0 if max_abs > 7.0 else 1.0  # bundle stores radians


def unit(az: float, el: float) -> np.ndarray:
    az, el = az * to_rad, el * to_rad
    return np.array([np.cos(el) * np.cos(az), np.sin(el), np.cos(el) * np.sin(az)])


dirs = np.stack([unit(*azel[f["id"]]) for f in frames])


def cap_members(center: np.ndarray, radius_deg: float) -> np.ndarray:
    return np.where(dirs @ center >= np.cos(np.radians(radius_deg)))[0]


def fps_pick(cand: list, center: np.ndarray, k: int) -> list:
    d2c = dirs[cand] @ center
    chosen = [int(np.argmax(d2c))]
    while len(chosen) < min(k, len(cand)):
        sel = dirs[cand][chosen]
        dmin = (dirs[cand] @ sel.T).max(axis=1)
        dmin[chosen] = 2.0
        chosen.append(int(np.argmin(dmin)))
    return [cand[i] for i in chosen]


def pick_window_centers(max_windows: int = 3) -> list:
    """Greedy: densest cap first, then adjacent caps 16-30° away."""
    centers = []
    # seed: frame direction with most neighbors inside the cap radius
    counts = (dirs @ dirs.T >= np.cos(np.radians(CAP_RADIUS_DEG))).sum(axis=1)
    seed = dirs[int(np.argmax(counts))]
    seed_members = cap_members(seed, CAP_RADIUS_DEG)
    c0 = dirs[seed_members].mean(axis=0)
    c0 /= np.linalg.norm(c0)
    centers.append(c0)
    lo, hi = np.cos(np.radians(CENTER_SEP_DEG[1])), np.cos(np.radians(CENTER_SEP_DEG[0]))
    while len(centers) < max_windows:
        best, best_n = None, 0
        for i in range(len(dirs)):
            c = dirs[i]
            if any(not (lo <= c @ p <= hi) for p in centers):
                continue
            n = len(cap_members(c, CAP_RADIUS_DEG))
            if n > best_n:
                best, best_n = c, n
        if best is None or best_n < K_PER_WINDOW:
            break
        members = cap_members(best, CAP_RADIUS_DEG)
        c = dirs[members].mean(axis=0)
        c /= np.linalg.norm(c)
        # keep the refined center inside the separation band; else keep raw
        if all(lo <= c @ p <= hi for p in centers):
            centers.append(c)
        else:
            centers.append(best)
    return centers


# ---------------------------------------------------------------- model ----
LAST_SCALE = {"v": None}
_orig_align = DepthAnything3._align_to_input_extrinsics_intrinsics


def _align_capture_scale(self, extrinsics, intrinsics, prediction,
                         align_to_input_ext_scale=True, ransac_view_thresh=10):
    # Verbatim official body (api.py:341) with the umeyama scale surfaced.
    if extrinsics is None:
        return prediction
    prediction.intrinsics = intrinsics.numpy()
    _, _, scale, aligned_extrinsics = align_poses_umeyama(
        prediction.extrinsics,
        extrinsics.numpy(),
        ransac=len(extrinsics) >= ransac_view_thresh,
        return_aligned=True,
        random_state=42,
    )
    LAST_SCALE["v"] = float(scale)
    if align_to_input_ext_scale:
        prediction.extrinsics = extrinsics[..., :3, :].numpy()
        prediction.depth /= scale
    else:
        prediction.extrinsics = aligned_extrinsics
    return prediction


DepthAnything3._align_to_input_extrinsics_intrinsics = _align_capture_scale

log("loading DA3-BASE …")
model = DepthAnything3.from_pretrained(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE"
).to(device=torch.device("mps"))
model.model.eval()
log("model ready")


def run_window(idxs: list) -> dict:
    sub = [frames[i] for i in idxs]
    paths = [str(CAP / f["sourceHighresRelativePath"]) for f in sub]
    ext = np.stack([
        np.asarray(f["cameraExtrinsicOpenCvW2c4x4"], dtype=np.float32).reshape(4, 4)
        for f in sub
    ])
    ixt = np.stack([
        np.asarray(f["cameraIntrinsic3x3"], dtype=np.float32).reshape(3, 3)
        for f in sub
    ])
    t0 = time.time()
    pred = model.inference(
        paths,
        extrinsics=ext,
        intrinsics=ixt,
        align_to_input_ext_scale=True,
        process_res=896,
        process_res_method="upper_bound_resize",
    )
    dt = time.time() - t0
    depth = np.asarray(pred.depth, dtype=np.float32)            # (N,H,W) metric
    conf = np.asarray(pred.conf, dtype=np.float32)
    ixt_p = np.asarray(pred.intrinsics, dtype=np.float32)       # processed K
    w2c = np.asarray(
        [np.asarray(f["cameraExtrinsicOpenCvW2c4x4"], dtype=np.float32).reshape(4, 4) for f in sub]
    )
    imgs = getattr(pred, "processed_images", None)
    rgb = None
    if imgs is not None:
        arr = np.asarray(imgs)
        if arr.ndim == 4 and arr.shape[-1] != 3 and arr.shape[1] == 3:
            arr = np.transpose(arr, (0, 2, 3, 1))
        if arr.dtype != np.uint8:
            arr = np.clip(arr * 255.0 if arr.max() <= 1.5 else arr, 0, 255).astype(np.uint8)
        rgb = arr
    return {
        "depth": depth, "conf": conf, "K": ixt_p, "w2c": w2c, "rgb": rgb,
        "umeyama_scale": LAST_SCALE["v"], "infer_s": dt,
    }


# ----------------------------------------------------------- geometry ----
def backproject(win: dict, stride: int, depth_scale: float = 1.0):
    pts, cols = [], []
    n, H, W = win["depth"].shape
    conf_floor = np.percentile(win["conf"], CONF_PERCENTILE)
    for i in range(n):
        z = win["depth"][i] * depth_scale
        m = (win["conf"][i] >= conf_floor) & (z > 1e-3)
        vs, us = np.where(m)
        vs, us = vs[::1], us[::1]
        sel = (vs % stride == 0) & (us % stride == 0)
        vs, us = vs[sel], us[sel]
        if len(vs) == 0:
            continue
        K = win["K"][i]
        zz = z[vs, us]
        x = (us + 0.5 - K[0, 2]) / K[0, 0] * zz
        y = (vs + 0.5 - K[1, 2]) / K[1, 1] * zz
        cam = np.stack([x, y, zz, np.ones_like(zz)])
        c2w = np.linalg.inv(win["w2c"][i])
        world = (c2w @ cam)[:3].T
        pts.append(world.astype(np.float32))
        if win["rgb"] is not None:
            cols.append(win["rgb"][i][vs, us])
    pts = np.concatenate(pts) if pts else np.zeros((0, 3), np.float32)
    cols = np.concatenate(cols) if cols else np.full((len(pts), 3), 200, np.uint8)
    return pts, cols


def pair_residual(src: dict, dst: dict, s_src: float = 1.0, s_dst: float = 1.0) -> dict:
    """Project src window's points into dst's frames; compare depth."""
    pts, _ = backproject(src, MEAS_STRIDE, s_src)
    n, H, W = dst["depth"].shape
    conf_floor = np.percentile(dst["conf"], CONF_PERCENTILE)
    ratios = []
    absd = []
    zs = []
    for i in range(n):
        w2c = dst["w2c"][i]
        cam = (w2c[:3, :3] @ pts.T + w2c[:3, 3:4])
        z = cam[2]
        front = z > 1e-3
        K = dst["K"][i]
        u = (cam[0] / z) * K[0, 0] + K[0, 2] - 0.5
        v = (cam[1] / z) * K[1, 1] + K[1, 2] - 0.5
        ui, vi = np.round(u).astype(int), np.round(v).astype(int)
        ok = front & (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        if not ok.any():
            continue
        zd = dst["depth"][i][vi[ok], ui[ok]] * s_dst
        cd = dst["conf"][i][vi[ok], ui[ok]]
        zp = z[ok]
        good = (cd >= conf_floor) & (zd > 1e-3)
        r = np.log(zd[good] / zp[good])
        keep = np.abs(r) <= GATE_LOG_RATIO
        ratios.append(r[keep])
        absd.append(np.abs(zd[good][keep] - zp[good][keep]))
        zs.append(zd[good][keep])
    if not ratios:
        return {"n": 0}
    r = np.concatenate(ratios)
    a = np.concatenate(absd)
    z = np.concatenate(zs)
    return {
        "n": int(len(r)),
        "scale_ratio_median": float(np.exp(np.median(r))),
        "abs_rel_median_pct": float(np.median(np.abs(np.expm1(r))) * 100),
        "abs_rel_p90_pct": float(np.percentile(np.abs(np.expm1(r)), 90) * 100),
        "abs_cm_median": float(np.median(a) * 100),
        "abs_cm_p90": float(np.percentile(a, 90) * 100),
        "z_median_m": float(np.median(z)),
    }


def write_ply(path: Path, pts: np.ndarray, cols: np.ndarray) -> None:
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(pts)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    )
    rec = np.empty(len(pts), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
    rec["xyz"], rec["rgb"] = pts, cols[: len(pts)]
    with path.open("wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(rec.tobytes())


def render(tag: str, clouds: list) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    palette = ["#e6194b", "#3cb44b", "#4363d8"]
    allpts = np.concatenate([p for p, _ in clouds])
    lo, hi = np.percentile(allpts, 2, axis=0), np.percentile(allpts, 98, axis=0)
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    for ax, (ai, bi, name) in zip(axes, [(0, 2, "top-down XZ (y=up)"), (0, 1, "side XY")]):
        for w, (p, _) in enumerate(clouds):
            sub = p[:: max(1, len(p) // 120_000)]
            ax.scatter(sub[:, ai], sub[:, bi], s=0.3, c=palette[w % 3],
                       alpha=0.25, linewidths=0, label=f"win{w}")
        ax.set_xlim(lo[ai], hi[ai]); ax.set_ylim(lo[bi], hi[bi])
        ax.set_title(f"{name} — {tag}"); ax.set_aspect("equal"); ax.legend(markerscale=20)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"render_{tag}.png", dpi=110)
    plt.close(fig)


# -------------------------------------------------------------- main ----
def main() -> int:
    centers = pick_window_centers(3)
    log(f"window centers: {len(centers)}")
    windows = []
    for w, c in enumerate(centers):
        members = list(cap_members(c, CAP_RADIUS_DEG))
        pick = fps_pick(members, c, K_PER_WINDOW)
        if len(pick) < K_PER_WINDOW:
            log(f"win{w}: only {len(pick)} frames, skipping window")
            continue
        ids = [frames[i]["id"] for i in pick]
        log(f"win{w}: {len(members)} avail → K{len(pick)} | inferring …")
        win = run_window(pick)
        win["ids"] = ids
        windows.append(win)
        log(
            f"win{w}: done in {win['infer_s']:.0f}s, umeyama_scale={win['umeyama_scale']:.4f}, "
            f"conf_med={float(np.median(win['conf'])):.2f}"
        )
        append_row({
            "kind": "window", "win": w, "ids": ids,
            "umeyama_scale": win["umeyama_scale"],
            "conf_median": float(np.median(win["conf"])),
            "infer_s": win["infer_s"],
        })
    if len(windows) < 2:
        log("FATAL: <2 windows — capture too concentrated for adjacency test")
        return 1

    scales = [w["umeyama_scale"] for w in windows]
    append_row({"kind": "scale_spread",
                "umeyama_scales": scales,
                "spread_pct": float((max(scales) / max(min(scales), 1e-9) - 1) * 100)})

    # BEFORE: official alignment only
    fits = {}
    for a in range(len(windows)):
        for b in range(len(windows)):
            if a >= b:
                continue
            ab = pair_residual(windows[a], windows[b])
            ba = pair_residual(windows[b], windows[a])
            append_row({"kind": "pair_pre", "pair": [a, b], "a_into_b": ab, "b_into_a": ba})
            log(f"PRE  {a}->{b}: {ab}")
            log(f"PRE  {b}->{a}: {ba}")
            if ab.get("n", 0) and ba.get("n", 0):
                # combine both directions into one scale estimate for b vs a
                s = float(np.sqrt(ab["scale_ratio_median"] / ba["scale_ratio_median"]))
                fits[(a, b)] = s

    # one extra scalar per window, window 0 = reference
    s_win = [1.0] * len(windows)
    for w in range(1, len(windows)):
        key = (0, w)
        if key in fits:
            # ratio medians measure dst/src; align w onto 0
            s_win[w] = 1.0 / fits[key]
    append_row({"kind": "overlap_fit_scales", "s_win": s_win})
    log(f"overlap-fit per-window scalars (ref win0): {s_win}")

    # AFTER: apply the extra scalar
    for a in range(len(windows)):
        for b in range(len(windows)):
            if a >= b:
                continue
            ab = pair_residual(windows[a], windows[b], s_win[a], s_win[b])
            ba = pair_residual(windows[b], windows[a], s_win[b], s_win[a])
            append_row({"kind": "pair_post", "pair": [a, b], "a_into_b": ab, "b_into_a": ba})
            log(f"POST {a}->{b}: {ab}")
            log(f"POST {b}->{a}: {ba}")

    # exports
    pre_clouds, post_clouds = [], []
    for w, win in enumerate(windows):
        p0, c0 = backproject(win, PLY_STRIDE, 1.0)
        p1, c1 = backproject(win, PLY_STRIDE, s_win[w])
        pre_clouds.append((p0, c0))
        post_clouds.append((p1, c1))
        write_ply(OUT_DIR / f"win{w}_pre.ply", p0, c0)
        write_ply(OUT_DIR / f"win{w}_post.ply", p1, c1)
    render("pre", pre_clouds)
    render("post", post_clouds)
    log("EXPD-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
