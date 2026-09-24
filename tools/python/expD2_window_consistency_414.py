#!/usr/bin/env python3
"""expD2: CONTROL for expD — inter-window consistency on the GOOD-LIGHT 414 set.

expD (dim-light phone capture cap_1781248804035239) showed ~27% median
cross-window surface disagreement that one extra per-window scalar does
NOT reduce. Confounds there: DA3 conf was floor-level (median ~1.0) and
the metric mixes occlusion into the median. This control reruns the
same measurement on the 2026-06-02 daylight dataset where window 025
is the calibrated high-conf anchor (true K18 conf 11.81).

Windows are the PRODUCTION shape: the spatial-order manifest is sorted
so window w = frames[w*9 : w*9+18]; adjacent windows share 9 frames.
We take w=25,26,28 (heavy overlap 25-26, lighter 25-28).

Same official DA3 path (pose-conditioned, umeyama align to ARKit
metric), same PRE/POST pair metric, plus a strict-conf variant
(top-25% conf) to separate "low-conf regions disagree" from
"everything disagrees".
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

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
OUT_DIR = Path("data/expD2_window_consistency_414_2026_06_12")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "expD2_results.jsonl"

WINDOW_IDS = [25, 26, 28]
GATE_LOG_RATIO = np.log(2.0)
MEAS_STRIDE = 3
PLY_STRIDE = 3


def log(msg: str) -> None:
    print(f"[expD2 {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def append_row(row: dict) -> None:
    with OUT.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
log(f"manifest frames: {len(man)}")

LAST_SCALE = {"v": None}


def _align_capture_scale(self, extrinsics, intrinsics, prediction,
                         align_to_input_ext_scale=True, ransac_view_thresh=10):
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


def run_window(rows: list) -> dict:
    paths = [str(D / "capture_seq_k35_strict" / r["jpegPath"]) for r in rows]
    ext = np.stack([
        np.asarray(r["cameraExtrinsic4x4"], dtype=np.float32).reshape(4, 4) for r in rows
    ])
    ixt = np.stack([
        np.asarray(
            [
                [r["cameraIntrinsicFxFyCxCy"][0], 0, r["cameraIntrinsicFxFyCxCy"][2]],
                [0, r["cameraIntrinsicFxFyCxCy"][1], r["cameraIntrinsicFxFyCxCy"][3]],
                [0, 0, 1],
            ],
            dtype=np.float32,
        )
        for r in rows
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
    depth = np.asarray(pred.depth, dtype=np.float32)
    conf = np.asarray(pred.conf, dtype=np.float32)
    ixt_p = np.asarray(pred.intrinsics, dtype=np.float32)
    w2c = np.asarray([
        np.asarray(r["cameraExtrinsic4x4"], dtype=np.float32).reshape(4, 4) for r in rows
    ])
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


def backproject(win: dict, stride: int, depth_scale: float, conf_pct: float):
    pts, cols = [], []
    n, H, W = win["depth"].shape
    conf_floor = np.percentile(win["conf"], conf_pct)
    for i in range(n):
        z = win["depth"][i] * depth_scale
        m = (win["conf"][i] >= conf_floor) & (z > 1e-3)
        vs, us = np.where(m)
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


def pair_residual(src, dst, s_src, s_dst, conf_pct) -> dict:
    pts, _ = backproject(src, MEAS_STRIDE, s_src, conf_pct)
    n, H, W = dst["depth"].shape
    conf_floor = np.percentile(dst["conf"], conf_pct)
    ratios, absd, zs = [], [], []
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
    for ax, (ai, bi, name) in zip(axes, [(0, 2, "top-down XZ"), (0, 1, "side XY")]):
        for w, (p, _) in enumerate(clouds):
            sub = p[:: max(1, len(p) // 120_000)]
            ax.scatter(sub[:, ai], sub[:, bi], s=0.3, c=palette[w % 3],
                       alpha=0.25, linewidths=0, label=f"win{WINDOW_IDS[w]}")
        ax.set_xlim(lo[ai], hi[ai]); ax.set_ylim(lo[bi], hi[bi])
        ax.set_title(f"{name} — {tag}"); ax.set_aspect("equal"); ax.legend(markerscale=20)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"render_{tag}.png", dpi=110)
    plt.close(fig)


def main() -> int:
    windows = []
    for w in WINDOW_IDS:
        rows = man[w * 9: w * 9 + 18]
        if len(rows) < 18:
            log(f"win{w}: only {len(rows)} frames — abort")
            return 1
        log(f"win{w}: inferring …")
        win = run_window(rows)
        windows.append(win)
        log(
            f"win{w}: done in {win['infer_s']:.0f}s, umeyama_scale={win['umeyama_scale']:.4f}, "
            f"conf_med={float(np.median(win['conf'])):.2f}, conf_p90={float(np.percentile(win['conf'],90)):.2f}"
        )
        append_row({
            "kind": "window", "win": w,
            "umeyama_scale": win["umeyama_scale"],
            "conf_median": float(np.median(win["conf"])),
            "conf_p90": float(np.percentile(win["conf"], 90)),
            "infer_s": win["infer_s"],
        })

    scales = [w["umeyama_scale"] for w in windows]
    append_row({"kind": "scale_spread", "umeyama_scales": scales,
                "spread_pct": float((max(scales) / max(min(scales), 1e-9) - 1) * 100)})
    log(f"umeyama scales: {scales}")

    for conf_pct, tag in [(40.0, "conf40"), (75.0, "conf75")]:
        fits = {}
        for a in range(len(windows)):
            for b in range(len(windows)):
                if a >= b:
                    continue
                ab = pair_residual(windows[a], windows[b], 1.0, 1.0, conf_pct)
                ba = pair_residual(windows[b], windows[a], 1.0, 1.0, conf_pct)
                append_row({"kind": f"pair_pre_{tag}", "pair": [WINDOW_IDS[a], WINDOW_IDS[b]],
                            "a_into_b": ab, "b_into_a": ba})
                log(f"PRE[{tag}]  {WINDOW_IDS[a]}->{WINDOW_IDS[b]}: {ab}")
                log(f"PRE[{tag}]  {WINDOW_IDS[b]}->{WINDOW_IDS[a]}: {ba}")
                if ab.get("n", 0) and ba.get("n", 0):
                    fits[(a, b)] = float(np.sqrt(ab["scale_ratio_median"] / ba["scale_ratio_median"]))
        s_win = [1.0] * len(windows)
        for w in range(1, len(windows)):
            if (0, w) in fits:
                s_win[w] = 1.0 / fits[(0, w)]
        append_row({"kind": f"overlap_fit_{tag}", "s_win": s_win})
        log(f"[{tag}] overlap-fit scalars: {s_win}")
        for a in range(len(windows)):
            for b in range(len(windows)):
                if a >= b:
                    continue
                ab = pair_residual(windows[a], windows[b], s_win[a], s_win[b], conf_pct)
                ba = pair_residual(windows[b], windows[a], s_win[b], s_win[a], conf_pct)
                append_row({"kind": f"pair_post_{tag}", "pair": [WINDOW_IDS[a], WINDOW_IDS[b]],
                            "a_into_b": ab, "b_into_a": ba})
                log(f"POST[{tag}] {WINDOW_IDS[a]}->{WINDOW_IDS[b]}: {ab}")
                log(f"POST[{tag}] {WINDOW_IDS[b]}->{WINDOW_IDS[a]}: {ba}")

    clouds = []
    for w, win in enumerate(windows):
        p0, c0 = backproject(win, PLY_STRIDE, 1.0, 40.0)
        clouds.append((p0, c0))
        write_ply(OUT_DIR / f"win{WINDOW_IDS[w]}_official.ply", p0, c0)
    render("official", clouds)
    log("EXPD2-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
