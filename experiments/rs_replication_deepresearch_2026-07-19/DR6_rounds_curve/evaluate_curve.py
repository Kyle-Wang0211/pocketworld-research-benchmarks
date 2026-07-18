#!/usr/bin/env python3.11
"""DR6: stage-1 rounds cost curve on the cap51 host replay.

Per arm (base = env unset, cap1..cap5 = AETHER_STAGE1_ROUNDS_CAP):
  - timing from run.log RESULT line + finalize_segments.json
  - peak RSS from /usr/bin/time -l stderr
  - geometry from the dumped COLMAP model: floor thickness proxy
    (identical formula to the frozen cap51 incremental-BA A/B evaluator:
    umeyama-align camera centers to the ARKit ledger, floor band = y in
    [p2, p15], plane fit residual, thickness = (p84 - p16) * 1000 mm).

Writes curve.json + curve.md. Read-only over run outputs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pycolmap

DR6 = Path(__file__).resolve().parent
LEDGER = Path(
    "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/"
    "pocketworld-repro-contract-20260714/data/pocketworld_captures/cap51/"
    "private_manifests/sfm_fed_frames.jsonl"
)
ARMS = ["base", "base_r2", "cap1", "cap2", "cap3", "cap4", "cap5"]


def umeyama(src: np.ndarray, dst: np.ndarray):
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src0 = src - src_mean
    dst0 = dst - dst_mean
    covariance = dst0.T @ src0 / len(src)
    u, singular, vt = np.linalg.svd(covariance)
    correction = np.eye(3)
    if np.linalg.det(u @ vt) < 0:
        correction[-1, -1] = -1
    rotation = u @ correction @ vt
    variance = np.mean(np.sum(src0 * src0, axis=1))
    scale = float(np.sum(singular * np.diag(correction)) / variance)
    translation = dst_mean - scale * (rotation @ src_mean)
    return scale, rotation, translation


def fit_residual(points: np.ndarray, dependent: int, independent: tuple[int, int]):
    design = np.column_stack(
        [points[:, independent[0]], points[:, independent[1]], np.ones(len(points))]
    )
    coef, _, _, _ = np.linalg.lstsq(design, points[:, dependent], rcond=None)
    return points[:, dependent] - design @ coef


def geometry(model_dir: Path, ledger: list[dict]) -> dict:
    rec = pycolmap.Reconstruction(model_dir)
    rec_centers, arkit_centers = [], []
    for image in rec.images.values():
        frame_id = int(Path(image.name).stem.split("_")[-1])
        rec_centers.append(image.projection_center())
        arkit_centers.append(ledger[frame_id]["arkitCameraCenterWorld"])
    rc = np.asarray(rec_centers, dtype=np.float64)
    ac = np.asarray(arkit_centers, dtype=np.float64)
    scale, rotation, translation = umeyama(rc, ac)
    aligned = scale * (rotation @ rc.T).T + translation
    cam_res = np.linalg.norm(aligned - ac, axis=1)

    xyz = np.asarray([p.xyz for p in rec.points3D.values()])
    metric = scale * (rotation @ xyz.T).T + translation
    y = metric[:, 1]
    y02, y15 = np.percentile(y, [2, 15])
    floor = metric[(y >= y02) & (y <= y15)]
    fres = fit_residual(floor, dependent=1, independent=(0, 2))
    thickness_mm = float((np.percentile(fres, 84) - np.percentile(fres, 16)) * 1000)
    return {
        "registered_frames": len(rec.images),
        "sparse_points": len(rec.points3D),
        "arkit_alignment_scale": scale,
        "arkit_camera_median_mm": float(np.median(cam_res) * 1000),
        "floor_band_points": int(len(floor)),
        "floor_thickness_mm": thickness_mm,
    }


def parse_run(arm: str, ledger: list[dict]) -> dict:
    out = DR6 / "runs" / arm
    row: dict = {"arm": arm}
    log = (out / "run.log").read_text()
    m = re.search(
        r"RESULT incr=\S+ n_reg=(\d+) n_points=(\d+) track3plus=(\d+) n_obs=(\d+) "
        r"mean_reproj_px=([\d.]+) stream_ms=([\d.]+) finalize_ms=([\d.]+) total_ms=([\d.]+)",
        log,
    )
    if m:
        row.update(
            n_reg=int(m[1]), n_points=int(m[2]), track3plus=int(m[3]),
            n_obs=int(m[4]), mean_reproj_px=float(m[5]), stream_ms=float(m[6]),
            finalize_ms=float(m[7]), total_ms=float(m[8]),
        )
    seg = json.loads((out / "finalize_segments.json").read_text())
    for key in ("cache_pre_ms", "enrich_ms", "stage1_ms", "stage1_rounds",
                "stage1_state", "stage2_ms", "stage2_rounds_budget",
                "temporal_ms", "total_ms"):
        row[f"seg_{key}"] = seg[key]
    err = (out / "run.err").read_text()
    rss = re.search(r"(\d+)\s+maximum resident set size", err)
    if rss:
        row["max_rss_bytes"] = int(rss[1])
    row.update(geometry(out, ledger))
    return row


def main() -> None:
    ledger = [json.loads(l) for l in LEDGER.read_text().splitlines() if l]
    rows = [parse_run(a, ledger) for a in ARMS]
    (DR6 / "curve.json").write_text(json.dumps(rows, indent=2) + "\n")

    cols = [
        ("arm", "arm"), ("seg_stage1_rounds", "s1轮"), ("seg_stage1_ms", "s1_ms"),
        ("seg_stage2_ms", "s2_ms"), ("seg_stage2_rounds_budget", "s2预算"),
        ("seg_enrich_ms", "enrich_ms"), ("finalize_ms", "finalize_ms"),
        ("stream_ms", "stream_ms"), ("total_ms", "total_ms"),
        ("n_points", "点数"), ("mean_reproj_px", "reproj_px"),
        ("floor_thickness_mm", "厚度mm"), ("n_reg", "注册"),
        ("max_rss_bytes", "峰值RSS"),
    ]
    lines = ["| " + " | ".join(h for _, h in cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        cells = []
        for key, _ in cols:
            v = r.get(key, "?")
            if isinstance(v, float):
                v = f"{v:.3f}" if v < 100 else f"{v:.0f}"
            cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    (DR6 / "curve.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
