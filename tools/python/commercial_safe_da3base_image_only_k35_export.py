#!/usr/bin/env python3
"""Run DA3-BASE image-only K35 and export official-GLB-style PLY diagnostics.

This script intentionally avoids DA3-Streaming, VGGT-Long, SALAD, AR/VIO,
depth-camera poses, and manifest camera poses. DA3 estimates cameras from RGB
images; the copied export path then fuses DA3's own depth/confidence/cameras.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import resource
import struct
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image, ImageDraw

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


DEFAULT_MODEL_PATH = Path(
    "/Users/kaidongwang/.cache/huggingface/hub/models--depth-anything--DA3-BASE/"
    "snapshots/f4a6c9b3c95e41c82048423d3493a81ec3fa810e"
)
DEFAULT_OFFICIAL_SRC = Path(
    "/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--windows-json", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--official-src", type=Path, default=DEFAULT_OFFICIAL_SRC)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_000")
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"], default="auto")
    parser.add_argument("--process-res", type=int, default=504)
    parser.add_argument("--process-res-method", default="upper_bound_resize")
    parser.add_argument(
        "--use-ray-pose",
        action="store_true",
        help="Use DA3's internal ray-based pose estimator instead of the camera decoder.",
    )
    parser.add_argument("--ref-view-strategy", default="saddle_balanced")
    parser.add_argument("--glb-conf-thresh", type=float, default=1.05)
    parser.add_argument("--glb-conf-percentile", type=float, default=40.0)
    parser.add_argument("--glb-ensure-percentile", type=float, default=90.0)
    parser.add_argument("--glb-num-max-points", type=int, default=1_000_000)
    parser.add_argument("--seed", type=int, default=8120)
    parser.add_argument(
        "--mps-chunked-sdpa",
        choices=["auto", "on", "off"],
        default="auto",
        help="Exact query-chunked SDPA execution fallback for MPS memory pressure.",
    )
    parser.add_argument("--mps-sdpa-query-chunk", type=int, default=256)
    parser.add_argument("--mps-sdpa-min-gib", type=float, default=2.0)
    args = parser.parse_args()

    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    windows_path = args.windows_json or args.capture_dir / "da3_k_windows.json"
    manifest_path = args.manifest or args.capture_dir / "da3_input_manifest.json"

    sys.path.insert(0, str(args.official_src))
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    import torch
    from depth_anything_3.api import DepthAnything3

    device = choose_device(torch, args.device)
    if should_install_mps_chunked_sdpa(args, device):
        install_mps_chunked_sdpa(torch, args.mps_sdpa_query_chunk, args.mps_sdpa_min_gib)

    manifest = read_json(manifest_path)
    windows = read_json(windows_path)
    window = select_window(windows, args.window_id)
    frames_by_id = {str(row["id"]): row for row in manifest.get("frames", [])}
    frame_ids = list(window.get("officialChunkFrameIDs") or window.get("frameIDs") or [])
    if not frame_ids:
        raise ValueError(f"{args.window_id} has no frame ids")
    rows = [frames_by_id[frame_id] for frame_id in frame_ids]
    image_paths = [str(resolve_image_path(args.capture_dir, row)) for row in rows]

    load_t0 = time.perf_counter()
    model = DepthAnything3.from_pretrained(str(args.model_path))
    model = model.to(device=device)
    model.model.eval()
    load_ms = (time.perf_counter() - load_t0) * 1000.0

    rss_before = rss_mb()
    run_t0 = time.perf_counter()
    with torch.no_grad():
        prediction = model.inference(
            image_paths,
            extrinsics=None,
            intrinsics=None,
            infer_gs=False,
            use_ray_pose=args.use_ray_pose,
            ref_view_strategy=args.ref_view_strategy,
            process_res=args.process_res,
            process_res_method=args.process_res_method,
            export_dir=None,
            export_feat_layers=[],
        )
    run_ms = (time.perf_counter() - run_t0) * 1000.0
    rss_after = rss_mb()

    depth = ensure_nhw(np.asarray(prediction.depth, dtype=np.float32), len(frame_ids), "depth")
    conf = ensure_nhw(np.asarray(prediction.conf, dtype=np.float32), len(frame_ids), "conf")
    intrinsics = np.asarray(prediction.intrinsics, dtype=np.float32)
    extrinsics = ensure_w2c34(np.asarray(prediction.extrinsics, dtype=np.float32), len(frame_ids))
    images = processed_images_to_uint8(np.asarray(prediction.processed_images), len(frame_ids))

    save_raw_prediction_arrays(args.out_dir, depth, conf, intrinsics, extrinsics, images)
    save_official_save_npz(args.out_dir / "results_output", window, frame_ids, depth, conf, intrinsics, extrinsics, images)

    full_group = build_group(
        frame_ids=frame_ids,
        indices=list(range(len(frame_ids))),
        depth=depth,
        conf=conf,
        intrinsics=intrinsics,
        extrinsics=extrinsics,
        images=images,
    )
    save_indices = official_save_indices(window, len(frame_ids))
    save_group = build_group(
        frame_ids=frame_ids,
        indices=save_indices,
        depth=depth,
        conf=conf,
        intrinsics=intrinsics,
        extrinsics=extrinsics,
        images=images,
    )

    combined = export_group(
        full_group,
        out_dir=args.out_dir,
        stem=f"{args.window_id}_combined35_glb_style",
        conf_thresh=args.glb_conf_thresh,
        conf_percentile=args.glb_conf_percentile,
        ensure_percentile=args.glb_ensure_percentile,
        num_max_points=args.glb_num_max_points,
        seed=args.seed,
    )
    unique = export_group(
        save_group,
        out_dir=args.out_dir,
        stem=f"{args.window_id}_official_save_unique_glb_style",
        conf_thresh=args.glb_conf_thresh,
        conf_percentile=args.glb_conf_percentile,
        ensure_percentile=args.glb_ensure_percentile,
        num_max_points=args.glb_num_max_points,
        seed=args.seed + 1,
    )

    report = {
        "schema_version": "pocketworld_commercial_safe_da3base_image_only_k35_export_v1",
        "commercial_safety_scope": {
            "legal_note": "Engineering compliance screen only, not legal advice.",
            "model": "DA3-BASE",
            "model_license_source": "Depth-Anything-3 README model table and pyproject show DA3-BASE / project as Apache-2.0.",
            "excluded_dependencies": [
                "DA3-Streaming runtime",
                "VGGT-Long runtime",
                "SALAD loop retrieval",
                "external AR/VIO/depth-camera pose input",
                "manifest camera extrinsics/intrinsics as model input",
            ],
            "image_only_contract": "DepthAnything3.inference(image_paths, extrinsics=None, intrinsics=None); DA3 predicts intrinsics/extrinsics from RGB.",
        },
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "windows_json": str(windows_path),
            "manifest": str(manifest_path),
            "model_path": str(args.model_path),
            "official_src": str(args.official_src),
            "window_id": args.window_id,
            "frame_count": len(frame_ids),
            "frame_ids": frame_ids,
            "official_save_local_indices": save_indices,
            "official_save_frame_ids": [frame_ids[index] for index in save_indices],
        },
        "parameters": {
            "device": str(device),
            "process_res": args.process_res,
            "process_res_method": args.process_res_method,
            "use_ray_pose": args.use_ray_pose,
            "ref_view_strategy": args.ref_view_strategy,
            "glb_conf_thresh": args.glb_conf_thresh,
            "glb_conf_percentile": args.glb_conf_percentile,
            "glb_ensure_percentile": args.glb_ensure_percentile,
            "glb_num_max_points": args.glb_num_max_points,
            "seed": args.seed,
            "mps_chunked_sdpa": args.mps_chunked_sdpa,
            "mps_sdpa_query_chunk": args.mps_sdpa_query_chunk,
            "mps_sdpa_min_gib": args.mps_sdpa_min_gib,
        },
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "torch": torch.__version__,
            "load_ms": load_ms,
            "run_ms": run_ms,
            "rss_before_mb": rss_before,
            "rss_after_mb": rss_after,
            "rss_delta_mb": rss_after - rss_before,
            "elapsed_s": round(time.perf_counter() - started, 3),
        },
        "prediction_metrics": {
            "processed_shape_nhwc": list(images.shape),
            "depth": summarize_array(depth.reshape(-1)),
            "confidence": summarize_array(conf.reshape(-1)),
            "intrinsics_fx": summarize_array(intrinsics[:, 0, 0]),
            "intrinsics_fy": summarize_array(intrinsics[:, 1, 1]),
            "pose": pose_metrics(np.stack([camera_center_from_w2c(ext) for ext in extrinsics], axis=0)),
        },
        "outputs": {
            "raw_arrays_dir": str(args.out_dir),
            "results_output_npz": str(args.out_dir / "results_output"),
            "combined35": combined,
            "official_save_unique": unique,
        },
    }
    write_json(args.out_dir / f"{args.window_id}_commercial_safe_image_only_report.json", report)
    write_markdown(args.out_dir / f"{args.window_id}_commercial_safe_image_only_report.md", report)
    print(json.dumps(compact_stdout(report), ensure_ascii=False, indent=2))
    return 0


def choose_device(torch: Any, requested: str) -> Any:
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(requested)


def should_install_mps_chunked_sdpa(args: argparse.Namespace, device: Any) -> bool:
    if str(device) != "mps":
        return False
    return args.mps_chunked_sdpa == "on" or args.mps_chunked_sdpa == "auto"


def install_mps_chunked_sdpa(torch_module: Any, query_chunk: int, min_gib: float) -> None:
    import torch.nn.functional as F

    original_sdpa = F.scaled_dot_product_attention
    reported_shapes: set[tuple[int, ...]] = set()

    def chunked_sdpa(
        query: Any,
        key: Any,
        value: Any,
        attn_mask: Any = None,
        dropout_p: float = 0.0,
        is_causal: bool = False,
        scale: float | None = None,
        enable_gqa: bool = False,
    ) -> Any:
        if (
            query.device.type != "mps"
            or dropout_p != 0.0
            or is_causal
            or enable_gqa
            or query.shape[-2] <= query_chunk
        ):
            return original_sdpa(
                query,
                key,
                value,
                attn_mask=attn_mask,
                dropout_p=dropout_p,
                is_causal=is_causal,
                scale=scale,
                enable_gqa=enable_gqa,
            )

        batch_heads = 1
        for dim in query.shape[:-2]:
            batch_heads *= int(dim)
        score_gib = (
            batch_heads
            * int(query.shape[-2])
            * int(key.shape[-2])
            * query.element_size()
            / (1024**3)
        )
        if score_gib < min_gib:
            return original_sdpa(
                query,
                key,
                value,
                attn_mask=attn_mask,
                dropout_p=dropout_p,
                is_causal=is_causal,
                scale=scale,
                enable_gqa=enable_gqa,
            )

        shape_key = tuple(int(dim) for dim in query.shape)
        if shape_key not in reported_shapes:
            print(
                "image_only_mps_chunked_sdpa "
                f"query_shape={shape_key} key_tokens={int(key.shape[-2])} "
                f"estimated_score_buffer_gib={score_gib:.2f} query_chunk={query_chunk}",
                flush=True,
            )
            reported_shapes.add(shape_key)

        scale_factor = float(scale) if scale is not None else 1.0 / math.sqrt(query.shape[-1])
        outputs = []
        key_t = key.transpose(-2, -1)
        query_tokens = int(query.shape[-2])
        for start in range(0, query_tokens, query_chunk):
            end = min(start + query_chunk, query_tokens)
            scores = torch_module.matmul(query[..., start:end, :], key_t) * scale_factor
            if attn_mask is not None:
                mask = attn_mask
                if mask.shape[-2] == query_tokens:
                    mask = mask[..., start:end, :]
                if mask.dtype == torch_module.bool:
                    scores = scores.masked_fill(~mask, float("-inf"))
                else:
                    scores = scores + mask
            probs = torch_module.softmax(scores.float(), dim=-1).to(value.dtype)
            outputs.append(torch_module.matmul(probs, value))
            del scores, probs
        return torch_module.cat(outputs, dim=-2)

    F.scaled_dot_product_attention = chunked_sdpa


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(data), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    combined = report["outputs"]["combined35"]
    unique = report["outputs"]["official_save_unique"]
    lines = [
        "# DA3-BASE Image-Only K35 Export",
        "",
        "- Runtime excludes DA3-Streaming, VGGT-Long, SALAD, external AR/VIO, and manifest camera pose inputs.",
        "- DA3 image-only predicts intrinsics/extrinsics from RGB, then the copied official GLB-style exporter fuses points.",
        f"- Window: `{report['inputs']['window_id']}`; frames: {report['inputs']['frame_count']}; process_res: {report['parameters']['process_res']}; use_ray_pose: {report['parameters']['use_ray_pose']}.",
        f"- Combined PLY: `{combined['outputs']['ply']}`",
        f"- Unique/save PLY: `{unique['outputs']['ply']}`",
        f"- Results NPZ dir: `{report['outputs']['results_output_npz']}`",
        "",
        "## Point Counts",
        "",
        f"- Combined exported points: {combined['filter']['exported_point_count']}",
        f"- Unique/save exported points: {unique['filter']['exported_point_count']}",
        "",
        "## Runtime",
        "",
        f"- Load ms: {report['runtime']['load_ms']:.1f}",
        f"- Run ms: {report['runtime']['run_ms']:.1f}",
        f"- RSS delta MB: {report['runtime']['rss_delta_mb']:.1f}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def select_window(windows: dict[str, Any], window_id: str) -> dict[str, Any]:
    by_id = {str(row["id"]): row for row in windows.get("windows", [])}
    if window_id not in by_id:
        raise KeyError(f"{window_id} not found")
    return by_id[window_id]


def resolve_image_path(capture_dir: Path, row: dict[str, Any]) -> Path:
    for key in ("sourceHighresRelativePath", "imageRelativePath", "jpegPath"):
        value = row.get(key)
        if value:
            path = Path(str(value))
            return path if path.is_absolute() else capture_dir / path
    raise KeyError(f"No image path field in frame {row.get('id')}")


def ensure_nhw(arr: np.ndarray, count: int, name: str) -> np.ndarray:
    out = np.asarray(arr)
    if out.ndim == 4 and out.shape[1] == 1:
        out = out[:, 0]
    if out.ndim == 4 and out.shape[-1] == 1:
        out = out[..., 0]
    if out.ndim == 2:
        out = out[None]
    if out.ndim != 3 or out.shape[0] != count:
        raise ValueError(f"{name} expected (N,H,W) with N={count}, got {arr.shape}")
    return out.astype(np.float32, copy=False)


def ensure_w2c34(arr: np.ndarray, count: int) -> np.ndarray:
    out = np.asarray(arr, dtype=np.float32)
    if out.ndim != 3 or out.shape[0] != count:
        raise ValueError(f"extrinsics expected batch N={count}, got {arr.shape}")
    if out.shape[1:] == (4, 4):
        out = out[:, :3, :]
    if out.shape[1:] != (3, 4):
        raise ValueError(f"extrinsics expected (N,3,4) or (N,4,4), got {arr.shape}")
    return out.astype(np.float32, copy=False)


def processed_images_to_uint8(images: np.ndarray, count: int) -> np.ndarray:
    arr = np.asarray(images)
    if arr.ndim != 4 or arr.shape[0] != count:
        raise ValueError(f"processed_images expected batch N={count}, got {arr.shape}")
    if arr.shape[1] == 3 and arr.shape[-1] != 3:
        arr = np.transpose(arr, (0, 2, 3, 1))
    if arr.shape[-1] != 3:
        raise ValueError(f"processed_images expected channels=3, got {arr.shape}")
    if np.issubdtype(arr.dtype, np.floating):
        if float(np.nanmax(arr)) <= 1.5:
            arr = arr * 255.0
        arr = np.clip(arr, 0, 255)
    return arr.astype(np.uint8)


def save_raw_prediction_arrays(
    out_dir: Path,
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    images: np.ndarray,
) -> None:
    np.save(out_dir / "pytorch_depth.npy", depth)
    np.save(out_dir / "pytorch_conf.npy", conf)
    np.save(out_dir / "pytorch_intrinsics.npy", intrinsics)
    np.save(out_dir / "pytorch_extrinsics.npy", extrinsics)
    np.save(out_dir / "pytorch_processed_images.npy", images)


def save_official_save_npz(
    out_dir: Path,
    window: dict[str, Any],
    frame_ids: list[str],
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    images: np.ndarray,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for save_order, local_index in enumerate(official_save_indices(window, len(frame_ids))):
        frame_id = frame_ids[local_index]
        np.savez_compressed(
            out_dir / f"frame_{save_order:06d}_{frame_id}.npz",
            frame_id=np.asarray(frame_id),
            local_index=np.asarray(local_index, dtype=np.int32),
            image=images[local_index],
            depth=depth[local_index],
            conf=conf[local_index],
            intrinsic=intrinsics[local_index],
            extrinsic=extrinsics[local_index],
        )


def official_save_indices(window: dict[str, Any], count: int) -> list[int]:
    indices = window.get("officialSaveLocalIndices")
    if indices:
        out = [int(index) for index in indices]
    else:
        out = list(range(count))
    for index in out:
        if index < 0 or index >= count:
            raise IndexError(f"official save local index {index} outside count {count}")
    return out


def build_group(
    *,
    frame_ids: list[str],
    indices: list[int],
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    images: np.ndarray,
) -> dict[str, Any]:
    centers = np.stack([camera_center_from_w2c(extrinsics[index]) for index in indices], axis=0)
    return {
        "indices": indices,
        "frame_ids": [frame_ids[index] for index in indices],
        "depth": depth[indices],
        "conf": conf[indices],
        "intrinsics": intrinsics[indices],
        "extrinsics": extrinsics[indices],
        "images": images[indices],
        "camera_centers": centers,
    }


def export_group(
    group: dict[str, Any],
    *,
    out_dir: Path,
    stem: str,
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
    valid_before_alignment = int(points.shape[0])
    alignment = official_glb_alignment_transform(group["extrinsics"][0], points)
    points = transform_points(points, alignment)
    points, colors = official_glb_filter_and_downsample(
        points,
        colors,
        num_max=num_max_points,
        seed=seed,
    )
    ply_path = out_dir / f"{stem}_rgb.ply"
    png_path = out_dir / f"{stem}_views.png"
    write_point_cloud(ply_path, points, colors)
    write_views_png(png_path, points, colors, title=stem)
    return {
        "outputs": {
            "ply": str(ply_path),
            "views_png": str(png_path),
        },
        "frame_ids": list(group["frame_ids"]),
        "filter": {
            "style": "copied official Depth-Anything-3 glb.py point-cloud path",
            "conf_threshold": float(threshold),
            "conf_thresh_base": conf_thresh,
            "conf_thresh_percentile": conf_percentile,
            "ensure_thresh_percentile": ensure_percentile,
            "valid_point_count_before_downsample": valid_before_alignment,
            "num_max_points": num_max_points,
            "exported_point_count": int(points.shape[0]),
            "alignment_transform": alignment,
            "random_downsample_seed": seed,
        },
        "point_cloud": cloud_metrics(points) if points.shape[0] else {"point_count": 0},
        "pca": pca_metrics(points) if points.shape[0] >= 3 else {"status": "not_enough_points"},
        "depth": summarize_array(group["depth"].reshape(-1)),
        "confidence": summarize_array(group["conf"].reshape(-1)),
        "pose": pose_metrics(group["camera_centers"]),
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
    path.parent.mkdir(parents=True, exist_ok=True)
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


def summarize_array(values: np.ndarray) -> dict[str, float | int]:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"count": 0}
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "p01": float(np.percentile(arr, 1)),
        "p10": float(np.percentile(arr, 10)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p90": float(np.percentile(arr, 90)),
        "p99": float(np.percentile(arr, 99)),
        "max": float(np.max(arr)),
    }


def cloud_metrics(points: np.ndarray) -> dict[str, Any]:
    pts = np.asarray(points, dtype=np.float64)
    if pts.size == 0:
        return {"point_count": 0}
    lo = np.percentile(pts, 1, axis=0)
    hi = np.percentile(pts, 99, axis=0)
    return {
        "point_count": int(pts.shape[0]),
        "bbox_min_p01": lo.tolist(),
        "bbox_max_p99": hi.tolist(),
        "bbox_diag_p01_p99": float(np.linalg.norm(hi - lo)),
        "centroid": np.mean(pts, axis=0).tolist(),
    }


def pca_metrics(points: np.ndarray) -> dict[str, Any]:
    pts = np.asarray(points, dtype=np.float64)
    if pts.shape[0] < 3:
        return {"status": "not_enough_points"}
    centered = pts - np.mean(pts, axis=0, keepdims=True)
    cov = np.cov(centered, rowvar=False)
    eigvals = np.linalg.eigvalsh(cov)
    eigvals = np.sort(np.maximum(eigvals, 0.0))[::-1]
    return {
        "eigenvalues": eigvals.tolist(),
        "major_extent": float(math.sqrt(eigvals[0])),
        "middle_extent": float(math.sqrt(eigvals[1])),
        "minor_extent": float(math.sqrt(eigvals[2])),
        "minor_over_major": float(math.sqrt(eigvals[2]) / max(math.sqrt(eigvals[0]), 1e-12)),
    }


def pose_metrics(camera_centers: np.ndarray) -> dict[str, Any]:
    centers = np.asarray(camera_centers, dtype=np.float64)
    if centers.shape[0] == 0:
        return {"count": 0}
    if centers.shape[0] == 1:
        step = np.zeros((0,), dtype=np.float64)
    else:
        step = np.linalg.norm(np.diff(centers, axis=0), axis=1)
    return {
        "count": int(centers.shape[0]),
        "camera_center_bbox": {
            "min": np.min(centers, axis=0).tolist(),
            "max": np.max(centers, axis=0).tolist(),
            "diag": float(np.linalg.norm(np.max(centers, axis=0) - np.min(centers, axis=0))),
        },
        "step_distance": summarize_array(step),
    }


def rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return float(value / (1024 * 1024))
    return float(value / 1024)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(val) for val in value]
    return value


def compact_stdout(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "window_id": report["inputs"]["window_id"],
        "frame_count": report["inputs"]["frame_count"],
        "excluded_dependencies": report["commercial_safety_scope"]["excluded_dependencies"],
        "runtime": report["runtime"],
        "outputs": {
            "combined_ply": report["outputs"]["combined35"]["outputs"]["ply"],
            "combined_views_png": report["outputs"]["combined35"]["outputs"]["views_png"],
            "unique_ply": report["outputs"]["official_save_unique"]["outputs"]["ply"],
            "unique_views_png": report["outputs"]["official_save_unique"]["outputs"]["views_png"],
            "report": str(Path(report["outputs"]["combined35"]["outputs"]["ply"]).parent / f"{report['inputs']['window_id']}_commercial_safe_image_only_report.json"),
        },
        "point_counts": {
            "combined": report["outputs"]["combined35"]["filter"]["exported_point_count"],
            "unique": report["outputs"]["official_save_unique"]["filter"]["exported_point_count"],
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
