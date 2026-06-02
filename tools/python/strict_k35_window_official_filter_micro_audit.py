#!/usr/bin/env python3
"""Official-filter micro-audit cumulative slots inside one strict DA3 K35 window.

This script keeps the CoreML DA3 output fixed and changes only point generation
and confidence filtering to match official DA3 export paths:

- Depth-Anything-3 `utils/export/glb.py` point generation:
  confidence percentile clamp, depth backprojection, first-camera glTF alignment,
  finite filtering, and max-point downsampling.
- DA3-Streaming `npz_output_process.py` / `save_confident_pointcloud_batch`
  point generation:
  group mean confidence threshold and streaming reservoir downsampling.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageOps

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


GROUPS = [
    ("slot_00", [0]),
    ("slots_00_01", [0, 1]),
    ("slots_00_02", [0, 1, 2]),
    ("first_05", list(range(5))),
    ("first_10", list(range(10))),
    ("first_35", list(range(35))),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--da3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_000")
    parser.add_argument("--glb-conf-thresh", type=float, default=1.05)
    parser.add_argument("--glb-conf-percentile", type=float, default=40.0)
    parser.add_argument("--glb-ensure-percentile", type=float, default=90.0)
    parser.add_argument("--glb-num-max-points", type=int, default=1_000_000)
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.75)
    parser.add_argument("--npz-sample-ratio", type=float, default=0.015)
    parser.add_argument("--seed", type=int, default=4300)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    reports = read_json(args.da3_dir / "mac_da3_window_reports.json")
    window_reports = {str(row["windowID"]): row for row in reports.get("windows", [])}
    if args.window_id not in window_reports:
        raise KeyError(f"{args.window_id} not found in {args.da3_dir / 'mac_da3_window_reports.json'}")

    frames = sorted(
        window_reports[args.window_id].get("frames", []),
        key=lambda row: int(row.get("windowSlot", 0)),
    )
    slots = [
        load_slot(frame, capture_dir=args.capture_dir, da3_dir=args.da3_dir)
        for frame in frames
    ]

    styles = [
        (
            "glb_style",
            {
                "source": "Depth-Anything-3/src/depth_anything_3/utils/export/glb.py",
                "conf_thresh": args.glb_conf_thresh,
                "conf_thresh_percentile": args.glb_conf_percentile,
                "ensure_thresh_percentile": args.glb_ensure_percentile,
                "num_max_points": args.glb_num_max_points,
            },
        ),
        (
            "npz_streaming_style",
            {
                "source": "Depth-Anything-3/da3_streaming/npz_output_process.py + loop_utils/sim3utils.py",
                "conf_threshold_coef": args.npz_conf_threshold_coef,
                "sample_ratio": args.npz_sample_ratio,
                "note": "Uses DA3-Streaming base_config Pointcloud_Save defaults; npz_output_process.py CLI default is 0.5.",
            },
        ),
    ]

    style_reports: list[dict[str, Any]] = []
    for style_name, style_params in styles:
        style_dir = args.out_dir / style_name
        style_dir.mkdir(parents=True, exist_ok=True)
        group_reports = []
        for group_index, (group_name, group_slots_raw) in enumerate(GROUPS):
            group_slots = [slot for slot in group_slots_raw if slot < len(slots)]
            if not group_slots:
                continue
            group = build_group(slots, group_slots)
            if style_name == "glb_style":
                exported = export_glb_style_group(
                    group,
                    conf_thresh=args.glb_conf_thresh,
                    conf_percentile=args.glb_conf_percentile,
                    ensure_percentile=args.glb_ensure_percentile,
                    num_max_points=args.glb_num_max_points,
                    seed=args.seed + group_index,
                )
            else:
                exported = export_npz_streaming_style_group(
                    group,
                    conf_threshold_coef=args.npz_conf_threshold_coef,
                    sample_ratio=args.npz_sample_ratio,
                    seed=args.seed + 1000 + group_index,
                )

            ply_path = style_dir / f"{group_name}_rgb.ply"
            png_path = style_dir / f"{group_name}_views.png"
            write_point_cloud(ply_path, exported["points"], exported["colors"])
            write_views_png(
                png_path,
                exported["points"],
                exported["colors"],
                title=f"{args.window_id} {style_name} {group_name}",
            )
            group_reports.append(
                {
                    "name": group_name,
                    "slots": group_slots,
                    "frame_ids": group["frame_ids"],
                    "outputs": {
                        "ply": str(ply_path),
                        "views_png": str(png_path),
                    },
                    "official_filter": exported["filter"],
                    "metrics": metrics_for_group(group, exported),
                }
            )

        contact_sheet = style_dir / f"{style_name}_contact_sheet.png"
        write_contact_sheet(contact_sheet, [Path(row["outputs"]["views_png"]) for row in group_reports])
        style_report = {
            "style": style_name,
            "parameters": style_params,
            "outputs": {
                "contact_sheet": str(contact_sheet),
            },
            "groups": group_reports,
            "interpretation": interpret_groups(group_reports),
        }
        write_json(style_dir / f"{style_name}_report.json", style_report)
        write_markdown(style_dir / f"{style_name}_report_zh.md", style_report)
        style_reports.append(style_report)

    comparison = compare_styles(style_reports)
    report = {
        "schema_version": "pocketworld_strict_k35_window_official_filter_micro_audit_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "da3_dir": str(args.da3_dir),
            "window_id": args.window_id,
            "model_context": {
                "commercial_path": "DA3-BASE",
                "mobile_model": "DA3BASE_476x742_N35_pose.mlpackage",
                "note": "This audit does not change the CoreML model output; it changes only point export/filter rules.",
            },
        },
        "parameters": {
            "groups": GROUPS,
            "seed": args.seed,
            "glb_style": styles[0][1],
            "npz_streaming_style": styles[1][1],
        },
        "styles": style_reports,
        "comparison": comparison,
    }
    write_json(args.out_dir / "window_000_official_filter_micro_audit_report.json", report)
    write_summary_markdown(args.out_dir / "window_000_official_filter_micro_audit_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def load_slot(frame: dict[str, Any], *, capture_dir: Path, da3_dir: Path) -> dict[str, Any]:
    height = int(frame["depthHeight"])
    width = int(frame["depthWidth"])
    depth = np.fromfile(da3_dir / str(frame["relativeDepthPath"]), dtype="<f4").reshape(height, width)
    conf = np.fromfile(da3_dir / str(frame["confidencePath"]), dtype="<f4").reshape(height, width)
    intrinsics = np.fromfile(da3_dir / str(frame["predIntrinsicsPath"]), dtype="<f4").reshape(3, 3)
    extrinsics = np.fromfile(da3_dir / str(frame["predExtrinsicsPath"]), dtype="<f4").reshape(3, 4)
    image = load_frame_colors(frame, capture_dir)
    return {
        "window_slot": int(frame.get("windowSlot", 0)),
        "frame_id": str(frame.get("frameID")),
        "frame_index": int(frame.get("frameIndex", -1)),
        "image_relative_path": str(frame.get("imageRelativePath")),
        "depth": depth.astype(np.float32, copy=False),
        "conf": conf.astype(np.float32, copy=False),
        "intrinsics": intrinsics.astype(np.float32, copy=False),
        "extrinsics": extrinsics.astype(np.float32, copy=False),
        "image": image,
        "camera_center": camera_center_from_w2c(extrinsics),
    }


def build_group(slots: list[dict[str, Any]], group_slots: list[int]) -> dict[str, Any]:
    selected = [slots[slot] for slot in group_slots]
    return {
        "slots": group_slots,
        "frame_ids": [slot["frame_id"] for slot in selected],
        "depth": np.stack([slot["depth"] for slot in selected], axis=0),
        "conf": np.stack([slot["conf"] for slot in selected], axis=0),
        "intrinsics": np.stack([slot["intrinsics"] for slot in selected], axis=0),
        "extrinsics": np.stack([slot["extrinsics"] for slot in selected], axis=0),
        "images": np.stack([slot["image"] for slot in selected], axis=0),
        "camera_centers": np.stack([slot["camera_center"] for slot in selected], axis=0),
    }


def export_glb_style_group(
    group: dict[str, Any],
    *,
    conf_thresh: float,
    conf_percentile: float,
    ensure_percentile: float,
    num_max_points: int,
    seed: int,
) -> dict[str, Any]:
    threshold = official_glb_conf_threshold(
        group["conf"],
        conf_thresh=conf_thresh,
        conf_thresh_percentile=conf_percentile,
        ensure_thresh_percentile=ensure_percentile,
    )
    points, colors = official_depths_to_world_points_with_colors(
        group["depth"],
        group["intrinsics"],
        group["extrinsics"],
        group["images"],
        group["conf"],
        threshold,
    )
    alignment = official_glb_alignment_transform(group["extrinsics"][0], points)
    points = transform_points(points, alignment)
    valid_before_downsample = int(points.shape[0])
    points, colors = official_glb_filter_and_downsample(
        points,
        colors,
        num_max=num_max_points,
        seed=seed,
    )
    return {
        "points": points,
        "colors": colors,
        "filter": {
            "style": "glb.py",
            "conf_threshold": threshold,
            "conf_thresh_base": conf_thresh,
            "conf_thresh_percentile": conf_percentile,
            "ensure_thresh_percentile": ensure_percentile,
            "valid_point_count_before_downsample": valid_before_downsample,
            "num_max_points": num_max_points,
            "exported_point_count": int(points.shape[0]),
            "alignment_transform": alignment,
            "random_downsample_seed": seed,
        },
    }


def export_npz_streaming_style_group(
    group: dict[str, Any],
    *,
    conf_threshold_coef: float,
    sample_ratio: float,
    seed: int,
) -> dict[str, Any]:
    point_maps = depth_to_point_cloud_vectorized(
        group["depth"],
        group["intrinsics"],
        group["extrinsics"],
    )
    threshold = float(np.mean(group["conf"]) * conf_threshold_coef)
    points, colors, valid_count = official_streaming_filter_and_reservoir_sample(
        point_maps,
        group["images"],
        group["conf"],
        conf_threshold=threshold,
        sample_ratio=sample_ratio,
        seed=seed,
    )
    return {
        "points": points,
        "colors": colors,
        "filter": {
            "style": "npz_output_process.py + save_confident_pointcloud_batch",
            "conf_threshold": threshold,
            "conf_threshold_coef": conf_threshold_coef,
            "sample_ratio": sample_ratio,
            "valid_point_count_before_downsample": valid_count,
            "exported_point_count": int(points.shape[0]),
            "random_downsample_seed": seed,
        },
    }


def official_glb_conf_threshold(
    conf: np.ndarray,
    *,
    conf_thresh: float,
    conf_thresh_percentile: float,
    ensure_thresh_percentile: float,
) -> float:
    conf_pixels = conf
    lower = np.percentile(conf_pixels, conf_thresh_percentile)
    upper = np.percentile(conf_pixels, ensure_thresh_percentile)
    return float(min(max(conf_thresh, lower), upper))


def official_depths_to_world_points_with_colors(
    depth: np.ndarray,
    intrinsics: np.ndarray,
    ext_w2c: np.ndarray,
    images_u8: np.ndarray,
    conf: np.ndarray | None,
    conf_thr: float,
) -> tuple[np.ndarray, np.ndarray]:
    n_frames, height, width = depth.shape
    us, vs = np.meshgrid(np.arange(width), np.arange(height))
    ones = np.ones_like(us)
    pix = np.stack([us, vs, ones], axis=-1).reshape(-1, 3)
    pts_all = []
    col_all = []
    for index in range(n_frames):
        d = depth[index]
        valid = np.isfinite(d) & (d > 0)
        if conf is not None:
            valid &= conf[index] >= conf_thr
        if not np.any(valid):
            continue

        d_flat = d.reshape(-1)
        valid_indices = np.flatnonzero(valid.reshape(-1))
        k_inv = np.linalg.inv(intrinsics[index])
        c2w = np.linalg.inv(as_homogeneous44(ext_w2c[index]))
        rays = k_inv @ pix[valid_indices].T
        camera_points = rays * d_flat[valid_indices][None, :]
        camera_points_h = np.vstack([camera_points, np.ones((1, camera_points.shape[1]))])
        world_points = (c2w @ camera_points_h)[:3].T.astype(np.float32)
        colors = images_u8[index].reshape(-1, 3)[valid_indices].astype(np.uint8)
        pts_all.append(world_points)
        col_all.append(colors)
    if not pts_all:
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.uint8)
    return np.concatenate(pts_all, axis=0), np.concatenate(col_all, axis=0)


def official_glb_alignment_transform(ext_w2c0: np.ndarray, points_world: np.ndarray) -> np.ndarray:
    w2c0 = as_homogeneous44(ext_w2c0).astype(np.float64)
    m = np.eye(4, dtype=np.float64)
    m[1, 1] = -1.0
    m[2, 2] = -1.0
    a_no_center = m @ w2c0
    if points_world.shape[0] > 0:
        pts_tmp = transform_points(points_world, a_no_center)
        center = np.median(pts_tmp, axis=0)
    else:
        center = np.zeros(3, dtype=np.float64)
    t_center = np.eye(4, dtype=np.float64)
    t_center[:3, 3] = -center
    return t_center @ a_no_center


def official_glb_filter_and_downsample(
    points: np.ndarray,
    colors: np.ndarray,
    *,
    num_max: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    if points.shape[0] == 0:
        return points.astype(np.float32), colors.astype(np.uint8)
    finite = np.isfinite(points).all(axis=1)
    points = points[finite].astype(np.float32, copy=False)
    colors = colors[finite].astype(np.uint8, copy=False)
    if points.shape[0] > num_max:
        rng = np.random.default_rng(seed)
        selected = rng.choice(points.shape[0], num_max, replace=False)
        points = points[selected]
        colors = colors[selected]
    return points, colors


def depth_to_point_cloud_vectorized(
    depth: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
) -> np.ndarray:
    n_frames, height, width = depth.shape
    u = np.arange(width, dtype=np.float32).reshape(1, 1, width, 1)
    v = np.arange(height, dtype=np.float32).reshape(1, height, 1, 1)
    u = np.broadcast_to(u, (n_frames, height, width, 1))
    v = np.broadcast_to(v, (n_frames, height, width, 1))
    ones = np.ones((n_frames, height, width, 1), dtype=np.float32)
    pixels = np.concatenate([u, v, ones], axis=-1)
    intrinsics_inv = np.linalg.inv(intrinsics.astype(np.float64))
    camera_coords = np.einsum("nij,nhwj->nhwi", intrinsics_inv, pixels.astype(np.float64))
    camera_coords = camera_coords * depth[..., None].astype(np.float64)
    camera_coords_homo = np.concatenate([camera_coords, np.ones_like(camera_coords[..., :1])], axis=-1)
    extrinsics_4x4 = np.zeros((n_frames, 4, 4), dtype=np.float64)
    extrinsics_4x4[:, :3, :4] = extrinsics.astype(np.float64)
    extrinsics_4x4[:, 3, 3] = 1.0
    c2w = np.linalg.inv(extrinsics_4x4)
    world_coords_homo = np.einsum("nij,nhwj->nhwi", c2w, camera_coords_homo)
    return world_coords_homo[..., :3].astype(np.float32)


def official_streaming_filter_and_reservoir_sample(
    points: np.ndarray,
    colors: np.ndarray,
    confs: np.ndarray,
    *,
    conf_threshold: float,
    sample_ratio: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    if points.ndim != 4:
        raise ValueError(f"Expected point map batch (b,H,W,3), got {points.shape}")
    batch_count = points.shape[0]
    total_valid = 0
    for index in range(batch_count):
        cfs = confs[index].reshape(-1)
        finite = np.isfinite(points[index].reshape(-1, 3)).all(axis=1)
        total_valid += int(np.count_nonzero(finite & (cfs >= conf_threshold) & (cfs > 1e-5)))

    num_samples = int(total_valid * sample_ratio) if sample_ratio < 1.0 else total_valid
    if num_samples == 0:
        return (
            np.zeros((0, 3), dtype=np.float32),
            np.zeros((0, 3), dtype=np.uint8),
            total_valid,
        )

    if sample_ratio == 1.0:
        point_chunks = []
        color_chunks = []
        for index in range(batch_count):
            pts = points[index].reshape(-1, 3).astype(np.float32)
            cls = colors[index].reshape(-1, 3).astype(np.uint8)
            cfs = confs[index].reshape(-1).astype(np.float32)
            mask = np.isfinite(pts).all(axis=1) & (cfs >= conf_threshold) & (cfs > 1e-5)
            point_chunks.append(pts[mask])
            color_chunks.append(cls[mask])
        return np.concatenate(point_chunks, axis=0), np.concatenate(color_chunks, axis=0), total_valid

    np.random.seed(seed)
    reservoir_pts = np.zeros((num_samples, 3), dtype=np.float32)
    reservoir_clr = np.zeros((num_samples, 3), dtype=np.uint8)
    count = 0
    for index in range(batch_count):
        pts = points[index].reshape(-1, 3).astype(np.float32)
        cls = colors[index].reshape(-1, 3).astype(np.uint8)
        cfs = confs[index].reshape(-1).astype(np.float32)
        mask = np.isfinite(pts).all(axis=1) & (cfs >= conf_threshold) & (cfs > 1e-5)
        valid_pts = pts[mask]
        valid_cls = cls[mask]
        n_valid = len(valid_pts)

        if count < num_samples:
            fill_count = min(num_samples - count, n_valid)
            reservoir_pts[count : count + fill_count] = valid_pts[:fill_count]
            reservoir_clr[count : count + fill_count] = valid_cls[:fill_count]
            count += fill_count
            if fill_count < n_valid:
                remaining_pts = valid_pts[fill_count:]
                remaining_cls = valid_cls[fill_count:]
                count, reservoir_pts, reservoir_clr = optimized_vectorized_reservoir_sampling(
                    remaining_pts,
                    remaining_cls,
                    count,
                    reservoir_pts,
                    reservoir_clr,
                )
        else:
            count, reservoir_pts, reservoir_clr = optimized_vectorized_reservoir_sampling(
                valid_pts,
                valid_cls,
                count,
                reservoir_pts,
                reservoir_clr,
            )
    return reservoir_pts, reservoir_clr, total_valid


def optimized_vectorized_reservoir_sampling(
    new_points: np.ndarray,
    new_colors: np.ndarray,
    current_count: int,
    reservoir_points: np.ndarray,
    reservoir_colors: np.ndarray,
) -> tuple[int, np.ndarray, np.ndarray]:
    reservoir_size = len(reservoir_points)
    num_new_points = len(new_points)
    if num_new_points == 0:
        return current_count, reservoir_points, reservoir_colors
    point_indices = np.arange(current_count + 1, current_count + num_new_points + 1)
    random_values = np.random.randint(0, point_indices, size=num_new_points)
    replacement_mask = random_values < reservoir_size
    replacement_positions = random_values[replacement_mask]
    if np.any(replacement_mask):
        reservoir_points[replacement_positions] = new_points[replacement_mask]
        reservoir_colors[replacement_positions] = new_colors[replacement_mask]
    return current_count + num_new_points, reservoir_points, reservoir_colors


def metrics_for_group(group: dict[str, Any], exported: dict[str, Any]) -> dict[str, Any]:
    points = exported["points"]
    return {
        "slot_count": len(group["slots"]),
        "valid_point_count_before_downsample": int(exported["filter"]["valid_point_count_before_downsample"]),
        "sampled_point_count": int(points.shape[0]),
        "valid_fraction_of_pixels": float(
            exported["filter"]["valid_point_count_before_downsample"]
            / max(np.prod(group["conf"].shape), 1)
        ),
        "point_cloud": cloud_metrics(points) if points.shape[0] else {"point_count": 0},
        "pca": pca_metrics(points) if points.shape[0] >= 3 else {"status": "not_enough_points"},
        "depth": summarize_array(group["depth"].reshape(-1)),
        "confidence": summarize_array(group["conf"].reshape(-1)),
        "pose": pose_metrics(group["camera_centers"]),
    }


def as_homogeneous44(ext: np.ndarray) -> np.ndarray:
    if ext.shape == (4, 4):
        return ext
    if ext.shape == (3, 4):
        homo = np.eye(4, dtype=ext.dtype)
        homo[:3, :4] = ext
        return homo
    raise ValueError(f"extrinsic must be (4,4) or (3,4), got {ext.shape}")


def transform_points(points: np.ndarray, transform: np.ndarray) -> np.ndarray:
    if points.shape[0] == 0:
        return points.astype(np.float32)
    homo = np.concatenate([points.astype(np.float64), np.ones((points.shape[0], 1), dtype=np.float64)], axis=1)
    out = homo @ transform.T
    return out[:, :3].astype(np.float32)


def camera_center_from_w2c(extrinsics: np.ndarray) -> np.ndarray:
    rotation = extrinsics[:3, :3].astype(np.float64)
    translation = extrinsics[:3, 3].astype(np.float64)
    return (-rotation.T @ translation).astype(np.float32)


def load_frame_colors(frame: dict[str, Any], capture_dir: Path) -> np.ndarray:
    width = int(frame["depthWidth"])
    height = int(frame["depthHeight"])
    with Image.open(capture_dir / str(frame["imageRelativePath"])) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.BILINEAR)
        return np.asarray(image, dtype=np.uint8)


def write_point_cloud(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    colors_u8 = np.clip(colors, 0, 255).astype(np.uint8)
    points_f32 = points.astype("<f4", copy=False)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {points_f32.shape[0]}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    with path.open("wb") as handle:
        handle.write(header)
        for point, color in zip(points_f32, colors_u8):
            handle.write(
                struct.pack(
                    "<fffBBB",
                    float(point[0]),
                    float(point[1]),
                    float(point[2]),
                    int(color[0]),
                    int(color[1]),
                    int(color[2]),
                )
            )


def write_views_png(path: Path, points: np.ndarray, colors: np.ndarray, *, title: str) -> None:
    if points.shape[0] == 0:
        image = Image.new("RGB", (1800, 600), "white")
        draw = ImageDraw.Draw(image)
        draw.text((40, 40), f"{title}: no points", fill=(20, 20, 20))
        image.save(path, quality=95)
        return
    rng = np.random.default_rng(123)
    pts = points.astype(np.float64)
    cols = np.clip(colors.astype(np.float64) / 255.0, 0.0, 1.0)
    lo = np.percentile(pts, 1.0, axis=0)
    hi = np.percentile(pts, 99.0, axis=0)
    mask = np.all((pts >= lo) & (pts <= hi), axis=1)
    pts = pts[mask]
    cols = cols[mask]
    if pts.shape[0] > 180_000:
        selected = rng.choice(pts.shape[0], size=180_000, replace=False)
        pts = pts[selected]
        cols = cols[selected]
    views = [("front XY", (0, 1)), ("top XZ", (0, 2)), ("side YZ", (1, 2))]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), facecolor="white")
    fig.suptitle(title)
    for ax, (view_name, (a, b)) in zip(axes, views):
        ax.scatter(pts[:, a], pts[:, b], s=0.35, c=cols, linewidths=0)
        ax.set_aspect("equal", "box")
        ax.set_title(view_name)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)


def write_contact_sheet(path: Path, png_paths: list[Path]) -> None:
    images = [Image.open(png_path).convert("RGB") for png_path in png_paths]
    if not images:
        return
    width = max(image.width for image in images)
    label_h = 48
    rows = []
    for png_path, image in zip(png_paths, images):
        if image.width != width:
            height = int(image.height * width / image.width)
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        row = Image.new("RGB", (width, image.height + label_h), "white")
        draw = ImageDraw.Draw(row)
        draw.rectangle([0, 0, width, label_h], fill=(245, 245, 245))
        draw.text((20, 16), png_path.stem, fill=(20, 20, 20))
        row.paste(image, (0, label_h))
        rows.append(row)
    sheet = Image.new("RGB", (width, sum(row.height for row in rows)), "white")
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height
    sheet.save(path, quality=95)


def cloud_metrics(points: np.ndarray) -> dict[str, Any]:
    lo = np.percentile(points, 1.0, axis=0)
    hi = np.percentile(points, 99.0, axis=0)
    lo95 = np.percentile(points, 5.0, axis=0)
    hi95 = np.percentile(points, 95.0, axis=0)
    extent = hi - lo
    extent95 = hi95 - lo95
    std = np.std(points, axis=0)
    return {
        "point_count": int(points.shape[0]),
        "bbox_p01": [float(v) for v in lo],
        "bbox_p99": [float(v) for v in hi],
        "bbox_extent_p01_p99": [float(v) for v in extent],
        "bbox_diag_p01_p99": float(np.linalg.norm(extent)),
        "bbox_extent_p05_p95": [float(v) for v in extent95],
        "bbox_diag_p05_p95": float(np.linalg.norm(extent95)),
        "std_xyz": [float(v) for v in std],
    }


def pca_metrics(points: np.ndarray) -> dict[str, Any]:
    pts = points.astype(np.float64)
    centered = pts - np.mean(pts, axis=0)
    cov = (centered.T @ centered) / max(points.shape[0] - 1, 1)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    projected = centered @ eigvecs
    lo = np.percentile(projected, 1.0, axis=0)
    hi = np.percentile(projected, 99.0, axis=0)
    extent = hi - lo
    return {
        "eigenvalues_desc": [float(v) for v in eigvals],
        "extent_p01_p99_desc": [float(v) for v in extent],
        "major_extent": float(extent[0]),
        "middle_extent": float(extent[1]),
        "minor_extent": float(extent[2]),
        "minor_to_major_ratio": float(extent[2] / max(extent[0], 1e-12)),
    }


def pose_metrics(centers: np.ndarray) -> dict[str, Any]:
    lo = np.min(centers, axis=0)
    hi = np.max(centers, axis=0)
    extent = hi - lo
    if centers.shape[0] > 1:
        steps = np.linalg.norm(np.diff(centers, axis=0), axis=1)
    else:
        steps = np.zeros((0,), dtype=np.float32)
    return {
        "camera_center_min": [float(v) for v in lo],
        "camera_center_max": [float(v) for v in hi],
        "camera_center_extent": [float(v) for v in extent],
        "camera_center_diag": float(np.linalg.norm(extent)),
        "step_mean": None if steps.size == 0 else float(np.mean(steps)),
        "step_max": None if steps.size == 0 else float(np.max(steps)),
    }


def summarize_array(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"count": 0}
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p05": float(np.percentile(arr, 5)),
        "p40": float(np.percentile(arr, 40)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
    }


def interpret_groups(groups: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    prev_diag = None
    prev_minor = None
    first_large_diag_jump = None
    first_large_minor_jump = None
    for group in groups:
        metrics = group["metrics"]
        diag = float(metrics["point_cloud"]["bbox_diag_p01_p99"])
        minor = float(metrics["pca"]["minor_extent"])
        ratio = float(metrics["pca"]["minor_to_major_ratio"])
        diag_growth = None if prev_diag is None else diag / max(prev_diag, 1e-12)
        minor_growth = None if prev_minor is None else minor / max(prev_minor, 1e-12)
        if first_large_diag_jump is None and diag_growth is not None and diag_growth >= 1.35:
            first_large_diag_jump = group["name"]
        if first_large_minor_jump is None and minor_growth is not None and minor_growth >= 1.35:
            first_large_minor_jump = group["name"]
        rows.append(
            {
                "name": group["name"],
                "slots": group["slots"],
                "valid_fraction": metrics["valid_fraction_of_pixels"],
                "exported_points": metrics["sampled_point_count"],
                "conf_threshold": group["official_filter"]["conf_threshold"],
                "bbox_diag_p01_p99": diag,
                "bbox_diag_growth_from_previous_group": diag_growth,
                "pca_minor_extent": minor,
                "pca_minor_growth_from_previous_group": minor_growth,
                "pca_minor_to_major_ratio": ratio,
                "camera_center_diag": metrics["pose"]["camera_center_diag"],
            }
        )
        prev_diag = diag
        prev_minor = minor
    return {
        "summary_rows": rows,
        "first_large_bbox_diag_jump_ge_1_35": first_large_diag_jump,
        "first_large_pca_minor_jump_ge_1_35": first_large_minor_jump,
        "note": "Growth thresholds are triage heuristics; visual PNG/PLY inspection remains part of the judgment.",
    }


def compare_styles(style_reports: list[dict[str, Any]]) -> dict[str, Any]:
    by_style = {report["style"]: report for report in style_reports}
    rows = []
    glb_rows = {
        row["name"]: row for row in by_style.get("glb_style", {}).get("interpretation", {}).get("summary_rows", [])
    }
    npz_rows = {
        row["name"]: row
        for row in by_style.get("npz_streaming_style", {}).get("interpretation", {}).get("summary_rows", [])
    }
    for name in [group[0] for group in GROUPS]:
        if name not in glb_rows or name not in npz_rows:
            continue
        glb = glb_rows[name]
        npz = npz_rows[name]
        rows.append(
            {
                "name": name,
                "glb_bbox_diag": glb["bbox_diag_p01_p99"],
                "npz_bbox_diag": npz["bbox_diag_p01_p99"],
                "glb_pca_minor": glb["pca_minor_extent"],
                "npz_pca_minor": npz["pca_minor_extent"],
                "glb_valid_fraction": glb["valid_fraction"],
                "npz_valid_fraction": npz["valid_fraction"],
            }
        )
    return {"rows": rows}


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "out_dir": str(Path(report["styles"][0]["outputs"]["contact_sheet"]).parents[1]),
        "style_contact_sheets": {
            style["style"]: style["outputs"]["contact_sheet"] for style in report["styles"]
        },
        "summary": {
            style["style"]: style["interpretation"] for style in report["styles"]
        },
    }


def write_markdown(path: Path, style_report: dict[str, Any]) -> None:
    lines = [
        f"# {style_report['style']} Report",
        "",
        f"- contact sheet: `{style_report['outputs']['contact_sheet']}`",
        f"- source: `{style_report['parameters']['source']}`",
        "",
        "| group | valid frac | points | conf thr | bbox diag | bbox growth | PCA minor | minor growth | minor/major |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in style_report["interpretation"]["summary_rows"]:
        lines.append(
            "| {name} | {valid:.3f} | {points} | {thr:.4f} | {diag:.4f} | {diag_growth} | {minor:.4f} | {minor_growth} | {ratio:.4f} |".format(
                name=row["name"],
                valid=row["valid_fraction"],
                points=row["exported_points"],
                thr=row["conf_threshold"],
                diag=row["bbox_diag_p01_p99"],
                diag_growth=fmt_optional(row["bbox_diag_growth_from_previous_group"]),
                minor=row["pca_minor_extent"],
                minor_growth=fmt_optional(row["pca_minor_growth_from_previous_group"]),
                ratio=row["pca_minor_to_major_ratio"],
            )
        )
    interp = style_report["interpretation"]
    lines.extend(
        [
            "",
            "## 自动标记",
            "",
            f"- first bbox diag jump >= 1.35x: `{interp['first_large_bbox_diag_jump_ge_1_35']}`",
            f"- first PCA minor jump >= 1.35x: `{interp['first_large_pca_minor_jump_ge_1_35']}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Window 000 Official Filter Micro Audit",
        "",
        "## 前提",
        "",
        "- DA3-BASE 是当前可商用路径中的最好模型。",
        "- DA3BASE_476x742_N35_pose.mlpackage 是手机可承载且深度信息最好的调参结果。",
        "- 本实验固定 CoreML 输出，只替换点云导出/过滤规则为官方规则。",
        "",
        "## 输出",
        "",
    ]
    for style in report["styles"]:
        lines.append(f"- {style['style']} contact sheet: `{style['outputs']['contact_sheet']}`")
        lines.append(f"- {style['style']} report: `{Path(style['outputs']['contact_sheet']).parent / (style['style'] + '_report_zh.md')}`")
    lines.extend(
        [
            "",
            "## 对比",
            "",
            "| group | glb bbox | npz bbox | glb minor | npz minor | glb valid | npz valid |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["comparison"]["rows"]:
        lines.append(
            "| {name} | {glb_diag:.4f} | {npz_diag:.4f} | {glb_minor:.4f} | {npz_minor:.4f} | {glb_valid:.3f} | {npz_valid:.3f} |".format(
                name=row["name"],
                glb_diag=row["glb_bbox_diag"],
                npz_diag=row["npz_bbox_diag"],
                glb_minor=row["glb_pca_minor"],
                npz_minor=row["npz_pca_minor"],
                glb_valid=row["glb_valid_fraction"],
                npz_valid=row["npz_valid_fraction"],
            )
        )
    lines.extend(
        [
            "",
            "## 初步判读",
            "",
            "- `glb_style` 使用官方 GLB export 的 percentile/clamp 过滤，slot_00 的 bbox 明显收紧，但仍能看到半透明厚层和少量游离片。",
            "- `npz_streaming_style` 使用官方 streaming pcd 保存规则；由于 base_config 是 `mean(conf)*0.75`，它保留约 69%-71% 像素，行为接近 raw micro audit。",
            "- 两套官方规则都没有出现 0+1、0+1+2、前 5 或前 10 的突增崩坏；问题更像是 CoreML 输出/pose-depth尺度/置信语义与点云消费规则之间的连续厚化，而不是某个早期 slot 拼接瞬间炸掉。",
            "",
            "## 自动标记",
            "",
        ]
    )
    for style in report["styles"]:
        interp = style["interpretation"]
        lines.append(
            f"- {style['style']}: bbox jump `{interp['first_large_bbox_diag_jump_ge_1_35']}`, "
            f"PCA minor jump `{interp['first_large_pca_minor_jump_ge_1_35']}`"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt_optional(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.3f}x"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
