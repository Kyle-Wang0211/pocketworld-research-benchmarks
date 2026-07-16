#!/usr/bin/env python3
"""Commercial-route DKMv3-outdoor matcher probe on first-party cap50 frames.

The only capture inputs are the materialized work images and their ARKit pose
metadata.  Historical LoFTR/ScanNet matches and derived rescue artifacts are
deliberately not accepted by this program.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import types
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class Frame:
    index: int
    path: Path
    k: np.ndarray
    r_cam_from_world: np.ndarray
    t_cam_from_world: np.ndarray
    center_world: np.ndarray
    view_world: np.ndarray


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def available_gb() -> float:
    output = subprocess.check_output(["vm_stat"], text=True)
    pages: dict[str, int] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        try:
            pages[key.strip()] = int(value.strip().rstrip("."))
        except ValueError:
            pass
    page_size = 16384
    return (
        pages.get("Pages free", 0)
        + pages.get("Pages speculative", 0)
        + pages.get("Pages inactive", 0)
    ) * page_size / 1e9


def install_clean_dkm_utils(repo: Path) -> None:
    """Expose only DKM's required transform and local-correlation package path.

    Upstream ``dkm.utils.__init__`` eagerly imports ``utils.py``, which contains
    unrelated GPL-3.0-derived geometry helpers.  The model forward pass needs
    none of them.  This minimal package shell keeps that file outside both the
    executed and shipped inference closure.
    """
    import torch
    from torchvision.transforms import InterpolationMode
    from torchvision.transforms import functional as vision_functional

    class TupleImageTransform:
        def __init__(self, resize=None, normalize=True):
            self.resize = resize
            self.normalize = normalize

        def __call__(self, images):
            tensors = []
            for image in images:
                if self.resize is not None:
                    image = vision_functional.resize(
                        image,
                        list(self.resize),
                        interpolation=InterpolationMode.BICUBIC,
                        antialias=True,
                    )
                array = np.asarray(image, dtype=np.float32).transpose(2, 0, 1) / 255.0
                tensor = torch.from_numpy(array)
                if self.normalize:
                    tensor = vision_functional.normalize(
                        tensor,
                        mean=[0.485, 0.456, 0.406],
                        std=[0.229, 0.224, 0.225],
                    )
                tensors.append(tensor)
            return tensors

    def get_tuple_transform_ops(resize=None, normalize=True, unscale=False):
        if unscale:
            raise ValueError("unscaled transforms are not part of the inference route")
        return TupleImageTransform(resize=resize, normalize=normalize)

    package = types.ModuleType("dkm.utils")
    package.__path__ = [str((repo / "dkm/utils").resolve())]
    package.get_tuple_transform_ops = get_tuple_transform_ops
    sys.modules["dkm.utils"] = package


def load_frames(metadata_path: Path, images_dir: Path) -> tuple[list[Frame], tuple[int, int]]:
    document = json.loads(metadata_path.read_text())
    width = int(document["work_w"])
    height = int(document["work_h"])
    frames: list[Frame] = []
    for index, item in enumerate(document["frames"]):
        camera_to_world = np.asarray(item["extrinsic"], dtype=np.float64).reshape(
            4, 4, order="F"
        )
        rotation_world_from_camera = camera_to_world[:3, :3]
        center_world = camera_to_world[:3, 3]
        rotation_arkit_camera_from_world = rotation_world_from_camera.T
        translation_arkit_camera_from_world = (
            -rotation_arkit_camera_from_world @ center_world
        )
        # ARKit camera coordinates are x-right, y-up, z-backward.  Pixel
        # projection uses the OpenCV x-right, y-down, z-forward convention.
        cv_from_arkit = np.diag([1.0, -1.0, -1.0])
        rotation_camera_from_world = cv_from_arkit @ rotation_arkit_camera_from_world
        translation_camera_from_world = (
            cv_from_arkit @ translation_arkit_camera_from_world
        )
        intrinsic = np.array(
            [
                [float(item["fx"]), 0.0, float(item["cx"])],
                [0.0, float(item["fy"]), float(item["cy"])],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        image_path = images_dir / item["name"]
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        view_world = -rotation_world_from_camera[:, 2]
        view_world /= np.linalg.norm(view_world)
        frames.append(
            Frame(
                index=index,
                path=image_path,
                k=intrinsic,
                r_cam_from_world=rotation_camera_from_world,
                t_cam_from_world=translation_camera_from_world,
                center_world=center_world,
                view_world=view_world,
            )
        )
    return frames, (width, height)


def angle_degrees(a: np.ndarray, b: np.ndarray) -> float:
    cosine = float(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def select_pairs(
    frames: list[Frame],
    min_baseline: float,
    max_baseline: float,
    max_view_angle: float,
    neighbors: int,
) -> list[dict]:
    pairs: dict[tuple[int, int], dict] = {}
    for left in frames:
        candidates: list[tuple[float, Frame, float]] = []
        for right in frames:
            if right.index == left.index:
                continue
            baseline = float(np.linalg.norm(left.center_world - right.center_world))
            if not min_baseline <= baseline <= max_baseline:
                continue
            view_angle = angle_degrees(left.view_world, right.view_world)
            if view_angle > max_view_angle:
                continue
            candidates.append((baseline, right, view_angle))
        for baseline, right, view_angle in sorted(candidates, key=lambda row: row[0])[:neighbors]:
            first, second = sorted((left.index, right.index))
            pairs[(first, second)] = {
                    "i": first,
                    "j": second,
                    "baseline_m": baseline,
                    "view_angle_deg": view_angle,
                }
    return [pairs[key] for key in sorted(pairs)]


def representative_subset(rows: list[dict], limit: int) -> list[dict]:
    if limit <= 0 or limit >= len(rows):
        return rows
    indices = np.linspace(0, len(rows) - 1, limit, dtype=np.int64)
    return [rows[int(index)] for index in np.unique(indices)]


def skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def fundamental(left: Frame, right: Frame) -> np.ndarray:
    rotation = right.r_cam_from_world @ left.r_cam_from_world.T
    translation = right.t_cam_from_world - rotation @ left.t_cam_from_world
    essential = skew(translation) @ rotation
    return np.linalg.inv(right.k).T @ essential @ np.linalg.inv(left.k)


def sampson_error(matrix: np.ndarray, points0: np.ndarray, points1: np.ndarray) -> np.ndarray:
    if not len(points0):
        return np.empty(0, dtype=np.float64)
    ones = np.ones((len(points0), 1), dtype=np.float64)
    homogeneous0 = np.concatenate([points0, ones], axis=1)
    homogeneous1 = np.concatenate([points1, ones], axis=1)
    fp0 = (matrix @ homogeneous0.T).T
    ftp1 = (matrix.T @ homogeneous1.T).T
    numerator = np.sum(homogeneous1 * fp0, axis=1) ** 2
    denominator = fp0[:, 0] ** 2 + fp0[:, 1] ** 2 + ftp1[:, 0] ** 2 + ftp1[:, 1] ** 2
    return np.sqrt(numerator / np.maximum(denominator, 1e-12))


def deterministic_grid_matches(
    warp,
    certainty,
    image_size: tuple[int, int],
    confidence: float,
    grid_px: int,
    maximum: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    # DKMv3 is symmetric: the first half is image0 -> image1 and the second
    # half is the reverse direction.  Keep one direction to avoid duplicates.
    width = warp.shape[1] // 2
    forward = warp[:, :width].detach().float().cpu().numpy().reshape(-1, 4)
    scores = certainty[:, :width].detach().float().cpu().numpy().reshape(-1)
    raw_above_threshold = int(np.count_nonzero(scores >= confidence))
    order = np.argsort(-scores, kind="stable")
    original_width, original_height = image_size
    accepted: list[int] = []
    occupied: set[tuple[int, int]] = set()
    for index in order:
        if scores[index] < confidence:
            break
        x0 = original_width * 0.5 * (forward[index, 0] + 1.0)
        y0 = original_height * 0.5 * (forward[index, 1] + 1.0)
        x1 = original_width * 0.5 * (forward[index, 2] + 1.0)
        y1 = original_height * 0.5 * (forward[index, 3] + 1.0)
        if not (0.0 <= x0 < original_width and 0.0 <= y0 < original_height):
            continue
        if not (0.0 <= x1 < original_width and 0.0 <= y1 < original_height):
            continue
        cell = (int(x0) // grid_px, int(y0) // grid_px)
        if cell in occupied:
            continue
        occupied.add(cell)
        accepted.append(int(index))
        if len(accepted) >= maximum:
            break
    chosen = np.asarray(accepted, dtype=np.int64)
    selected = forward[chosen]
    points0 = np.column_stack(
        [
            original_width * 0.5 * (selected[:, 0] + 1.0),
            original_height * 0.5 * (selected[:, 1] + 1.0),
        ]
    ).astype(np.float32)
    points1 = np.column_stack(
        [
            original_width * 0.5 * (selected[:, 2] + 1.0),
            original_height * 0.5 * (selected[:, 3] + 1.0),
        ]
    ).astype(np.float32)
    return points0, points1, scores[chosen].astype(np.float32), raw_above_threshold


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dkm-repo", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "mps"), default="mps")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--pair-start", type=int, default=0)
    parser.add_argument("--pair-count", type=int, default=0)
    parser.add_argument("--focus-frame", type=int, default=-1)
    parser.add_argument("--neighbors", type=int, default=4)
    parser.add_argument("--min-baseline", type=float, default=0.15)
    parser.add_argument("--max-baseline", type=float, default=1.50)
    parser.add_argument("--max-view-angle", type=float, default=45.0)
    parser.add_argument("--model-width", type=int, default=640)
    parser.add_argument("--model-height", type=int, default=360)
    parser.add_argument("--confidence", type=float, default=0.20)
    parser.add_argument("--grid-px", type=int, default=8)
    parser.add_argument("--max-matches", type=int, default=5000)
    parser.add_argument("--sampson-px", type=float, default=3.0)
    parser.add_argument("--memory-guard-gb", type=float, default=3.0)
    parser.add_argument("--max-mps-gb", type=float, default=4.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in (args.dkm_repo, args.weights, args.metadata, args.images):
        if not path.exists():
            raise FileNotFoundError(path)
    initial_available = available_gb()
    if initial_available < args.memory_guard_gb:
        raise RuntimeError(
            f"available memory {initial_available:.2f}GB is below guard {args.memory_guard_gb:.2f}GB"
        )

    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    sys.path.insert(0, str(args.dkm_repo.resolve()))
    import torch
    import cv2

    install_clean_dkm_utils(args.dkm_repo)
    from dkm.models.model_zoo.DKMv3 import DKMv3

    if "dkm.utils.utils" in sys.modules:
        raise RuntimeError("refusing GPL-tainted upstream dkm.utils import closure")

    if args.device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS is unavailable")
    device = torch.device(args.device)
    torch.manual_seed(0)
    cv2.setRNGSeed(0)
    frames, image_size = load_frames(args.metadata, args.images)
    all_pairs = select_pairs(
        frames,
        args.min_baseline,
        args.max_baseline,
        args.max_view_angle,
        args.neighbors,
    )
    if args.focus_frame >= 0:
        all_pairs = [
            pair
            for pair in all_pairs
            if args.focus_frame in (pair["i"], pair["j"])
        ]
    selected_pairs = representative_subset(all_pairs, args.limit)
    if args.pair_start < 0 or args.pair_start > len(selected_pairs):
        raise ValueError("pair-start is outside the selected pair range")
    pair_stop = (
        args.pair_start + args.pair_count
        if args.pair_count > 0
        else len(selected_pairs)
    )
    pairs = selected_pairs[args.pair_start : pair_stop]
    if not pairs:
        raise RuntimeError("pair selection produced no pairs")

    print(
        f"[dkm] frames={len(frames)} candidate_pairs={len(all_pairs)} selected={len(pairs)} "
        f"slice={args.pair_start}:{args.pair_start + len(pairs)} "
        f"available={initial_available:.2f}GB",
        flush=True,
    )
    load_started = time.monotonic()
    weights = torch.load(args.weights, map_location="cpu", weights_only=True)
    model = DKMv3(
        weights,
        args.model_height,
        args.model_width,
        upsample_preds=False,
        device="cpu",
    ).eval()
    del weights
    model = model.to(device)
    load_seconds = time.monotonic() - load_started
    print(f"[dkm] model loaded on {device} in {load_seconds:.2f}s", flush=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {}
    rows: list[dict] = []
    peak_mps_bytes = 0
    run_started = time.monotonic()
    for pair_index, pair in enumerate(pairs):
        memory_before = available_gb()
        if memory_before < args.memory_guard_gb:
            raise RuntimeError(
                f"memory guard reached before pair {pair_index}: {memory_before:.2f}GB"
            )
        left, right = frames[pair["i"]], frames[pair["j"]]
        pair_started = time.monotonic()
        with Image.open(left.path) as image0, Image.open(right.path) as image1:
            warp, certainty = model.match(
                image0.convert("RGB"), image1.convert("RGB"), device=device
            )
        points0, points1, scores, raw_count = deterministic_grid_matches(
            warp,
            certainty,
            image_size,
            args.confidence,
            args.grid_px,
            args.max_matches,
        )
        errors = sampson_error(fundamental(left, right), points0, points1)
        inlier = errors <= args.sampson_px
        robust_mask = None
        robust_status = "insufficient_points"
        if len(points0) >= 8:
            try:
                _, robust_mask = cv2.findFundamentalMat(
                    points0,
                    points1,
                    cv2.USAC_MAGSAC,
                    args.sampson_px,
                    0.999,
                    10000,
                )
                robust_status = "estimated" if robust_mask is not None else "estimation_failed"
            except cv2.error:
                robust_status = "opencv_error"
        robust_inliers = (
            robust_mask.reshape(-1).astype(bool)
            if robust_mask is not None
            else np.zeros(len(points0), dtype=bool)
        )
        key = f"{left.index:03d}_{right.index:03d}"
        arrays[f"{key}_p0"] = points0
        arrays[f"{key}_p1"] = points1
        arrays[f"{key}_confidence"] = scores
        arrays[f"{key}_sampson_px"] = errors.astype(np.float32)
        if args.device == "mps":
            peak_mps_bytes = max(peak_mps_bytes, int(torch.mps.driver_allocated_memory()))
            if peak_mps_bytes > args.max_mps_gb * 1e9:
                raise RuntimeError(
                    f"MPS allocation {peak_mps_bytes / 1e9:.2f}GB exceeds "
                    f"cap {args.max_mps_gb:.2f}GB"
                )
        elapsed = time.monotonic() - pair_started
        row = {
            **pair,
            "raw_above_confidence": raw_count,
            "grid_unique_matches": int(len(points0)),
            "sampson_inliers": int(inlier.sum()),
            "sampson_inlier_ratio": float(inlier.mean()) if len(inlier) else 0.0,
            "sampson_median_px": float(np.median(errors)) if len(errors) else None,
            "sampson_p90_px": float(np.percentile(errors, 90)) if len(errors) else None,
            "magsac_inliers": int(robust_inliers.sum()),
            "magsac_status": robust_status,
            "magsac_inlier_ratio": (
                float(robust_inliers.mean()) if len(robust_inliers) else 0.0
            ),
            "wall_seconds": elapsed,
            "available_gb_before": memory_before,
            "available_gb_after": available_gb(),
        }
        rows.append(row)
        del warp, certainty
        if args.device == "mps":
            torch.mps.empty_cache()
        median_text = (
            f"{row['sampson_median_px']:.3f}px"
            if row["sampson_median_px"] is not None
            else "NA"
        )
        print(
            f"[dkm] {pair_index + 1}/{len(pairs)} {key} grid={len(points0)} "
            f"arkit_inlier={row['sampson_inlier_ratio']:.3f} "
            f"magsac_inlier={row['magsac_inlier_ratio']:.3f} "
            f"median={median_text} time={elapsed:.2f}s",
            flush=True,
        )

    npz_path = args.output_dir / "matches.npz"
    np.savez_compressed(npz_path, **arrays)
    ratios = [row["sampson_inlier_ratio"] for row in rows]
    robust_ratios = [row["magsac_inlier_ratio"] for row in rows]
    counts = [row["grid_unique_matches"] for row in rows]
    metadata = {
        "route": "commercial_detector_free_dkmv3_outdoor_megadepth_only",
        "dkm_revision": subprocess.check_output(
            ["git", "-C", str(args.dkm_repo), "rev-parse", "HEAD"], text=True
        ).strip(),
        "dkm_source_sha256": sha256(args.dkm_repo / "dkm/models/model_zoo/DKMv3.py"),
        "dkm_model_runtime_sha256": sha256(args.dkm_repo / "dkm/models/dkm.py"),
        "dkm_weight_registry_sha256": sha256(
            args.dkm_repo / "dkm/models/model_zoo/__init__.py"
        ),
        "dkm_outdoor_training_recipe_sha256": sha256(
            args.dkm_repo / "experiments/dkm/train_DKMv3_outdoor.py"
        ),
        "clean_inference_wrapper_sha256": sha256(Path(__file__)),
        "gpl_geometry_utils_imported": False,
        "dkm_license_sha256": sha256(args.dkm_repo / "LICENSE"),
        "weights_sha256": sha256(args.weights),
        "weights_bytes": args.weights.stat().st_size,
        "capture_metadata_sha256": sha256(args.metadata),
        "input_image_count": len(frames),
        "input_classes": ["first_party_work_images", "first_party_arkit_pose_metadata"],
        "forbidden_noncommercial_matcher_outputs_consumed": False,
        "device": str(device),
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "model_resolution": [args.model_width, args.model_height],
        "confidence_threshold": args.confidence,
        "grid_px": args.grid_px,
        "sampson_threshold_px": args.sampson_px,
        "pair_selection": {
            "candidate_count": len(all_pairs),
            "selected_count": len(pairs),
            "pre_slice_selected_count": len(selected_pairs),
            "pair_start": args.pair_start,
            "pair_stop": args.pair_start + len(pairs),
            "neighbors": args.neighbors,
            "min_baseline_m": args.min_baseline,
            "max_baseline_m": args.max_baseline,
            "max_view_angle_deg": args.max_view_angle,
            "representative_subset": args.limit > 0,
            "mode": "symmetric_knn_union",
            "focus_frame": args.focus_frame,
        },
        "model_load_seconds": load_seconds,
        "match_wall_seconds": time.monotonic() - run_started,
        "peak_mps_bytes": peak_mps_bytes,
        "max_mps_gb_guard": args.max_mps_gb,
        "available_gb_initial": initial_available,
        "grid_matches_median": float(np.median(counts)),
        "arkit_sampson_inlier_ratio_median": float(np.median(ratios)),
        "magsac_inlier_ratio_median": float(np.median(robust_ratios)),
        "pairs": rows,
    }
    metadata_path = args.output_dir / "metrics.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(f"[dkm] matches_sha256={sha256(npz_path)}", flush=True)
    print(f"[dkm] metrics_sha256={sha256(metadata_path)}", flush=True)
    print("DKM_CAP50_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
