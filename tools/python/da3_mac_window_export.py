#!/usr/bin/env python3
"""Mac DA3 CoreML window exporter for real PocketWorld captures.

This research utility mirrors the iOS DA3 executor contract closely enough for
downstream Dart/Python research tools:

  capture/photo_bundle.json + da3_k_windows.json + photos_depth/*.jpg
    -> depth_index.json
    -> relative_depth/*.bin
    -> confidence/*.bin
    -> pred_pose/*_{extrinsics,intrinsics}.bin

It intentionally does not own window policy, model choice, naming semantics, or
quality gates. Those come from the capture-side Dart manifests.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import resource
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = (
    REPO_ROOT
    / "ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage"
)
IMAGENET_MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument(
        "--image-root",
        type=Path,
        default=None,
        help="Optional root for photos_depth/photos_highres image files; manifests still come from capture-dir.",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument(
        "--compute-unit",
        default="all",
        choices=["cpu", "cpu_and_gpu", "cpu_and_ne", "all"],
    )
    parser.add_argument("--max-windows", type=int, default=0)
    parser.add_argument(
        "--window-id",
        action="append",
        default=[],
        help="Export only the selected window id. Can be repeated.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--official-normalize-input-extrinsics",
        action="store_true",
        help=(
            "Research parity test only: normalize pose-conditioned CoreML extrinsics "
            "with the official DA3 external-camera pre-forward contract."
        ),
    )
    args = parser.parse_args()

    capture_dir = args.capture_dir
    image_root = args.image_root or capture_dir
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ("relative_depth", "confidence", "pred_pose"):
        (out_dir / subdir).mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "mac_da3_window_export_log.jsonl"
    write_jsonl(log_path, {"event": "start", "args": vars_for_json(args)})

    bundle = read_json(capture_dir / "photo_bundle.json")
    k_windows = read_json(capture_dir / "da3_k_windows.json")
    da3_input_manifest = maybe_read_json(capture_dir / "da3_input_manifest.json")
    raw_model_policy = maybe_read_json(capture_dir / "model_policy.json")
    model_policy = dict(
        raw_model_policy.get("selectedDepthModel")
        or k_windows.get("model")
        or raw_model_policy
    )

    height = int(k_windows.get("inputHeight") or model_policy.get("inputHeight") or 476)
    width = int(k_windows.get("inputWidth") or model_policy.get("inputWidth") or 742)
    window_size = int(k_windows.get("windowSize") or model_policy.get("windowSize") or 35)
    windows = list(k_windows.get("windows") or [])
    if args.window_id:
        wanted = set(args.window_id)
        windows = [window for window in windows if str(window.get("id")) in wanted]
        missing = sorted(wanted - {str(window.get("id")) for window in windows})
        if missing:
            raise ValueError(
                f"Requested window id(s) not found in da3_k_windows.json: {missing}"
            )
    if args.max_windows > 0:
        windows = windows[: args.max_windows]

    frames_by_id = {str(frame["id"]): frame for frame in bundle.get("frames", [])}
    input_by_id = {
        str(frame["id"]): frame for frame in da3_input_manifest.get("frames", [])
    }

    import coremltools as ct

    if not args.model.exists():
        raise FileNotFoundError(args.model)
    write_jsonl(log_path, {"event": "model_load_start", "model": str(args.model)})
    load_start = time.perf_counter()
    model = ct.models.MLModel(
        str(args.model),
        compute_units=compute_unit(ct, args.compute_unit),
    )
    model_input_names = coreml_input_names(model)
    model_input_contract = da3_input_contract(model_input_names)
    write_jsonl(
        log_path,
        {
            "event": "model_load_done",
            "load_s": round(time.perf_counter() - load_start, 3),
            "rss_mb": round(rss_mb(), 3),
            "coremltools": ct.__version__,
            "modelInputNames": model_input_names,
            "da3InputContract": model_input_contract,
        },
    )

    selected_by_frame: dict[str, dict[str, Any]] = {}
    window_reports: list[dict[str, Any]] = []
    started = time.perf_counter()
    for window_index, window in enumerate(windows):
        window_id = str(window.get("id") or f"window_{window_index:03d}")
        frame_ids = [str(value) for value in window.get("frameIDs", [])]
        if len(frame_ids) != window_size:
            raise ValueError(
                f"{window_id} has {len(frame_ids)} frames; expected {window_size}"
            )

        existing = expected_window_frame_rows(
            window=window,
            frame_ids=frame_ids,
            frames_by_id=frames_by_id,
            input_by_id=input_by_id,
            out_dir=out_dir,
            height=height,
            width=width,
        )
        if args.resume and all_outputs_exist(existing, out_dir):
            window_report = {
                "windowID": window_id,
                "status": "completed",
                "frames": existing,
                "telemetry": {"resumed": True},
            }
            window_reports.append(window_report)
            merge_selected(selected_by_frame, existing, window)
            write_jsonl(
                log_path,
                {
                    "event": "window_resumed",
                    "window": window_index + 1,
                    "window_count": len(windows),
                    "windowID": window_id,
                },
            )
            continue

        write_jsonl(
            log_path,
            {
                "event": "window_start",
                "window": window_index + 1,
                "window_count": len(windows),
                "windowID": window_id,
                "rss_mb": round(rss_mb(), 3),
            },
        )
        inputs, input_report = build_inputs(
            capture_dir=capture_dir,
            image_root=image_root,
            frame_ids=frame_ids,
            frames_by_id=frames_by_id,
            input_by_id=input_by_id,
            height=height,
            width=width,
            model_input_names=model_input_names,
            official_normalize_input_extrinsics=args.official_normalize_input_extrinsics,
        )
        predict_start = time.perf_counter()
        outputs = model.predict(inputs)
        predict_ms = (time.perf_counter() - predict_start) * 1000.0
        frame_rows = write_window_outputs(
            outputs=outputs,
            window=window,
            frame_ids=frame_ids,
            frames_by_id=frames_by_id,
            input_by_id=input_by_id,
            out_dir=out_dir,
            height=height,
            width=width,
            inference_ms=predict_ms,
        )
        window_report = {
            "windowID": window_id,
            "status": "completed",
            "frames": frame_rows,
            "telemetry": {
                "predictMs": predict_ms,
                "rssAfterPredictMB": rss_mb(),
                "computeUnit": args.compute_unit,
                "macResearchExecutor": "coremltools",
                "inputCameraContract": input_report,
            },
        }
        window_reports.append(window_report)
        merge_selected(selected_by_frame, frame_rows, window)
        write_jsonl(
            log_path,
            {
                "event": "window_done",
                "window": window_index + 1,
                "window_count": len(windows),
                "windowID": window_id,
                "predict_ms": round(predict_ms, 3),
                "elapsed_s": round(time.perf_counter() - started, 3),
                "rss_mb": round(rss_mb(), 3),
            },
        )

    ordered_frames = sorted(
        selected_by_frame.values(),
        key=lambda row: int(row.get("frameIndex", 0)),
    )
    write_json(out_dir / "mac_da3_window_reports.json", {"windows": window_reports})
    write_depth_index(
        out_dir=out_dir,
        capture_dir=capture_dir,
        model_path=args.model,
        bundle=bundle,
        k_windows=k_windows,
        model_policy=model_policy,
        window_reports=window_reports,
        frames=ordered_frames,
        height=height,
        width=width,
        model_input_names=model_input_names,
        model_input_contract=model_input_contract,
        elapsed_s=time.perf_counter() - started,
    )
    write_jsonl(
        log_path,
        {
            "event": "done",
            "window_count": len(window_reports),
            "frame_count": len(ordered_frames),
            "elapsed_s": round(time.perf_counter() - started, 3),
        },
    )
    return 0


def vars_for_json(args: argparse.Namespace) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Path) else value
        for key, value in vars(args).items()
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def maybe_read_json(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


def rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return usage / (1024.0 * 1024.0)
    return usage / 1024.0


def compute_unit(ct: Any, raw: str) -> Any:
    table = {
        "cpu": ct.ComputeUnit.CPU_ONLY,
        "cpu_and_gpu": ct.ComputeUnit.CPU_AND_GPU,
        "cpu_and_ne": ct.ComputeUnit.CPU_AND_NE,
        "all": ct.ComputeUnit.ALL,
    }
    return table[raw]


def coreml_input_names(model: Any) -> list[str]:
    return [feature.name for feature in model.get_spec().description.input]


def da3_input_contract(input_names: list[str]) -> str:
    input_set = set(input_names)
    if input_set == {"image"}:
        return "image_only"
    if {"image", "extrinsics", "intrinsics"}.issubset(input_set):
        return "pose_conditioned_coreml_requires_image_extrinsics_intrinsics"
    return "unknown_coreml_input_contract"


def build_inputs(
    *,
    capture_dir: Path,
    image_root: Path,
    frame_ids: list[str],
    frames_by_id: dict[str, dict[str, Any]],
    input_by_id: dict[str, dict[str, Any]],
    height: int,
    width: int,
    model_input_names: list[str],
    official_normalize_input_extrinsics: bool,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    images: list[np.ndarray] = []
    extrinsics: list[np.ndarray] = []
    intrinsics: list[np.ndarray] = []
    needs_extrinsics = "extrinsics" in model_input_names
    needs_intrinsics = "intrinsics" in model_input_names
    if needs_extrinsics != needs_intrinsics:
        raise ValueError(
            f"Unsupported DA3 CoreML camera input set: {model_input_names}; "
            "expected both extrinsics/intrinsics or neither."
        )
    for frame_id in frame_ids:
        frame = frames_by_id[frame_id]
        input_frame = input_by_id.get(frame_id, {})
        image_rel = input_frame.get("depthImageRelativePath") or f"photos_depth/{frame_id}.jpg"
        images.append(preprocess_image(image_root / str(image_rel), height, width))
        if needs_extrinsics:
            extrinsics.append(da3_extrinsics(frame, input_frame))
            intrinsics.append(da3_intrinsics(frame, input_frame, height, width))
    inputs = {"image": np.stack(images, axis=0)[None, ...].astype(np.float32)}
    input_report: dict[str, Any] = {
        "officialPreForwardExtrinsicsNormalization": False,
        "cameraInputsPresent": needs_extrinsics,
    }
    if needs_extrinsics:
        extrinsic_stack = np.stack(extrinsics, axis=0).astype(np.float32)
        if official_normalize_input_extrinsics:
            extrinsic_stack, input_report = official_normalize_extrinsics_stack(
                extrinsic_stack
            )
        inputs["extrinsics"] = extrinsic_stack[None, ...].astype(np.float32)
        inputs["intrinsics"] = np.stack(intrinsics, axis=0)[None, ...].astype(np.float32)
    return inputs, input_report


def official_normalize_extrinsics_stack(
    extrinsics: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Mirror depth_anything_3.api.DA3._normalize_extrinsics for one window."""
    if extrinsics.ndim != 3 or extrinsics.shape[1:] != (4, 4):
        raise ValueError(f"Expected extrinsics shape [N,4,4], got {extrinsics.shape}")
    transform = np.linalg.inv(extrinsics[:1])
    normalized = extrinsics @ transform
    c2ws = np.linalg.inv(normalized)
    translations = c2ws[:, :3, 3]
    dists = np.linalg.norm(translations, axis=-1)
    raw_median_dist = float(np.median(dists))
    median_dist = max(raw_median_dist, 1e-1)
    normalized[:, :3, 3] = normalized[:, :3, 3] / np.float32(median_dist)
    return normalized.astype(np.float32), {
        "officialPreForwardExtrinsicsNormalization": True,
        "cameraInputsPresent": True,
        "normalizationContract": (
            "ex_t_norm = ex_t @ inv(ex_t_first); c2w translations median distance "
            "clamped to >= 1e-1; ex_t_norm translation divided by that median"
        ),
        "rawMedianCameraCenterDistance": raw_median_dist,
        "clampedMedianCameraCenterDistance": float(median_dist),
        "cameraCenterDistanceMin": float(np.min(dists)),
        "cameraCenterDistanceMax": float(np.max(dists)),
        "cameraCenterDistanceMedian": raw_median_dist,
    }


def da3_model_resource(model_policy: dict[str, Any], model_path: Path) -> str:
    if model_path.stem.startswith("DA3BASE_"):
        resource = model_path.stem
    else:
        resource = str(model_policy.get("resourceName") or model_path.stem)
    return resource.removesuffix(".mlpackage").removesuffix(".mlmodelc")


def effective_model_policy(
    model_policy: dict[str, Any],
    *,
    model_path: Path,
    width: int,
    height: int,
    model_input_contract: str,
) -> dict[str, Any]:
    policy = dict(model_policy)
    resource = da3_model_resource(policy, model_path)
    policy.update(
        {
            "resourceName": resource,
            "windowSize": int(policy.get("windowSize") or 35),
            "inputWidth": width,
            "inputHeight": height,
            "da3InputContract": model_input_contract,
        }
    )
    if model_input_contract == "image_only":
        policy.update(
            {
                "id": policy.get("id") or "DA3-BASE",
                "mobileTag": "da3:base:k35:process_res504:upper_bound_resize:image_only",
                "inputSizeStatus":
                    "official_da3_process_res_504_upper_bound_resize_patch14_for_16x9",
                "processRes": 504,
                "processResMethod": "upper_bound_resize",
                "patchSize": 14,
                "preprocessContract":
                    "official_depth_anything_3_input_processor_upper_bound_resize_patch_align",
                "officialStreamingBaseline": True,
                "officialStreamingBaselineStatus":
                    "ready_DA3BASE_280x504_N35_image_only_coreml_signature",
            }
        )
    return policy


def preprocess_image(path: Path, height: int, width: int) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.BICUBIC)
        arr = np.asarray(image, dtype=np.float32) / 255.0
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(arr, (2, 0, 1)).astype(np.float32)


def camera_transform_to_opencv_w2c(values: list[float]) -> np.ndarray:
    c2w_arkit = np.asarray(values, dtype=np.float32).reshape(4, 4, order="F")
    cv_from_arkit_camera = np.diag([1.0, -1.0, -1.0, 1.0]).astype(np.float32)
    c2w_opencv = c2w_arkit @ cv_from_arkit_camera
    return np.linalg.inv(c2w_opencv).astype(np.float32)


def da3_extrinsics(frame: dict[str, Any], input_frame: dict[str, Any]) -> np.ndarray:
    precomputed = input_frame.get("cameraExtrinsicOpenCvW2c4x4") or []
    if len(precomputed) == 16:
        return np.asarray(precomputed, dtype=np.float32).reshape(4, 4)
    return camera_transform_to_opencv_w2c(frame["cameraTransform"])


def da3_intrinsics(
    frame: dict[str, Any],
    input_frame: dict[str, Any],
    height: int,
    width: int,
) -> np.ndarray:
    precomputed = input_frame.get("cameraIntrinsic3x3") or []
    if len(precomputed) == 9:
        return np.asarray(precomputed, dtype=np.float32).reshape(3, 3)
    return scale_intrinsics(frame, input_frame, height, width)


def scale_intrinsics(
    frame: dict[str, Any],
    input_frame: dict[str, Any],
    height: int,
    width: int,
) -> np.ndarray:
    intrinsics = frame.get("intrinsics") or []
    if len(intrinsics) == 4:
        fx, fy, cx, cy = [float(value) for value in intrinsics]
    elif len(intrinsics) == 9:
        mat = np.asarray(intrinsics, dtype=np.float32).reshape(3, 3)
        fx, fy, cx, cy = float(mat[0, 0]), float(mat[1, 1]), float(mat[0, 2]), float(mat[1, 2])
    else:
        fx = fy = float(max(width, height))
        cx = float(width) * 0.5
        cy = float(height) * 0.5

    transform = input_frame.get("intrinsicsTransform") or {}
    if transform:
        fx *= float(transform.get("fxScale", 1.0))
        fy *= float(transform.get("fyScale", 1.0))
        cx = cx * float(transform.get("cxScale", 1.0)) + float(transform.get("cxOffset", 0.0))
        cy = cy * float(transform.get("cyScale", 1.0)) + float(transform.get("cyOffset", 0.0))
    else:
        source_w = float(frame.get("imageWidth") or width)
        source_h = float(frame.get("imageHeight") or height)
        fx *= float(width) / max(source_w, 1.0)
        fy *= float(height) / max(source_h, 1.0)
        cx *= float(width) / max(source_w, 1.0)
        cy *= float(height) / max(source_h, 1.0)

    return np.asarray(
        [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def write_window_outputs(
    *,
    outputs: dict[str, Any],
    window: dict[str, Any],
    frame_ids: list[str],
    frames_by_id: dict[str, dict[str, Any]],
    input_by_id: dict[str, dict[str, Any]],
    out_dir: Path,
    height: int,
    width: int,
    inference_ms: float,
) -> list[dict[str, Any]]:
    window_id = str(window.get("id"))
    downstream_ids = official_downstream_ids(window)
    withheld_ids = set(str(value) for value in window.get("withheldForNextOverlapFrameIDs", []))
    depth = np.squeeze(np.asarray(outputs["depth"], dtype=np.float32), axis=0)
    # Keep sealed CoreML output on the raw DA3 API confidence contract.
    # DA3-Streaming's `predictions.conf -= 1.0` is applied only when
    # materializing results_output/frame_*.npz, not at this raw export layer.
    conf = np.squeeze(np.asarray(outputs["depth_conf"], dtype=np.float32), axis=0)
    pred_extrinsics = np.squeeze(
        np.asarray(outputs["pred_extrinsics"], dtype=np.float32),
        axis=0,
    )
    pred_intrinsics = np.squeeze(
        np.asarray(outputs["pred_intrinsics"], dtype=np.float32),
        axis=0,
    )
    frame_rows: list[dict[str, Any]] = []
    for slot, frame_id in enumerate(frame_ids):
        frame = frames_by_id[frame_id]
        input_frame = input_by_id.get(frame_id, {})
        bundle_index = int(frame.get("_bundleIndex", -1))
        if bundle_index < 0:
            bundle_index = frame_bundle_index(frames_by_id, frame_id)
            frame["_bundleIndex"] = bundle_index
        stem = f"{window_id}_{slot:02d}_{bundle_index}_{frame_id}"
        depth_rel = f"relative_depth/{stem}.bin"
        conf_rel = f"confidence/{stem}.bin"
        extr_rel = f"pred_pose/{stem}_extrinsics.bin"
        intr_rel = f"pred_pose/{stem}_intrinsics.bin"
        write_f32(out_dir / depth_rel, depth[slot])
        write_f32(out_dir / conf_rel, conf[slot])
        write_f32(out_dir / extr_rel, pred_extrinsics[slot])
        write_f32(out_dir / intr_rel, pred_intrinsics[slot])
        stats = finite_stats(conf[slot])
        frame_rows.append(
            {
                "frameID": frame_id,
                "frameIndex": bundle_index,
                "imageRelativePath": input_frame.get("depthImageRelativePath")
                or f"photos_depth/{frame_id}.jpg",
                "windowID": window_id,
                "windowSlot": slot,
                "status": "completed",
                "relativeDepthPath": depth_rel,
                "confidencePath": conf_rel,
                "predExtrinsicsPath": extr_rel,
                "predIntrinsicsPath": intr_rel,
                "depthWidth": width,
                "depthHeight": height,
                "inferenceMs": inference_ms,
                "confMedian": stats["median"],
                "confMean": stats["mean"],
                "confMin": stats["min"],
                "confMax": stats["max"],
                "windowRole": window_role(window, frame_id),
                "officialDownstreamFrame": frame_id in downstream_ids,
                "officialWithheldForNextOverlap": frame_id in withheld_ids,
            }
        )
    return frame_rows


def expected_window_frame_rows(
    *,
    window: dict[str, Any],
    frame_ids: list[str],
    frames_by_id: dict[str, dict[str, Any]],
    input_by_id: dict[str, dict[str, Any]],
    out_dir: Path,
    height: int,
    width: int,
) -> list[dict[str, Any]]:
    window_id = str(window.get("id"))
    downstream_ids = official_downstream_ids(window)
    withheld_ids = set(str(value) for value in window.get("withheldForNextOverlapFrameIDs", []))
    rows: list[dict[str, Any]] = []
    for slot, frame_id in enumerate(frame_ids):
        frame = frames_by_id[frame_id]
        input_frame = input_by_id.get(frame_id, {})
        bundle_index = int(frame.get("_bundleIndex", -1))
        if bundle_index < 0:
            bundle_index = frame_bundle_index(frames_by_id, frame_id)
            frame["_bundleIndex"] = bundle_index
        stem = f"{window_id}_{slot:02d}_{bundle_index}_{frame_id}"
        rows.append(
            {
                "frameID": frame_id,
                "frameIndex": bundle_index,
                "imageRelativePath": input_frame.get("depthImageRelativePath")
                or f"photos_depth/{frame_id}.jpg",
                "windowID": window_id,
                "windowSlot": slot,
                "status": "completed",
                "relativeDepthPath": f"relative_depth/{stem}.bin",
                "confidencePath": f"confidence/{stem}.bin",
                "predExtrinsicsPath": f"pred_pose/{stem}_extrinsics.bin",
                "predIntrinsicsPath": f"pred_pose/{stem}_intrinsics.bin",
                "depthWidth": width,
                "depthHeight": height,
                "windowRole": window_role(window, frame_id),
                "officialDownstreamFrame": frame_id in downstream_ids,
                "officialWithheldForNextOverlap": frame_id in withheld_ids,
            }
        )
    return rows


def frame_bundle_index(frames_by_id: dict[str, dict[str, Any]], frame_id: str) -> int:
    for index, key in enumerate(frames_by_id.keys()):
        if key == frame_id:
            return index
    return -1


def all_outputs_exist(rows: list[dict[str, Any]], out_dir: Path) -> bool:
    for row in rows:
        for key in (
            "relativeDepthPath",
            "confidencePath",
            "predExtrinsicsPath",
            "predIntrinsicsPath",
        ):
            if not (out_dir / str(row[key])).exists():
                return False
    return True


def window_role(window: dict[str, Any], frame_id: str) -> str:
    if frame_id in set(str(value) for value in window.get("coreFrameIDs", [])):
        return "core"
    if frame_id in set(str(value) for value in window.get("bridgeFrameIDs", [])):
        return "bridge"
    return "unknown"


def official_downstream_ids(window: dict[str, Any]) -> set[str]:
    for key in ("downstreamFrameIDs", "officialSaveFrameIDs"):
        values = set(str(value) for value in window.get(key, []))
        if values:
            return values
    return set(str(value) for value in window.get("coreFrameIDs", []))


def merge_selected(
    selected_by_frame: dict[str, dict[str, Any]],
    frame_rows: list[dict[str, Any]],
    window: dict[str, Any],
) -> None:
    downstream_ids = official_downstream_ids(window)
    for row in frame_rows:
        frame_id = str(row["frameID"])
        if downstream_ids and frame_id not in downstream_ids:
            continue
        current = selected_by_frame.get(frame_id)
        if current is None:
            selected_by_frame[frame_id] = dict(row)
            continue
        if row.get("officialDownstreamFrame") and not current.get("officialDownstreamFrame"):
            selected_by_frame[frame_id] = dict(row)


def write_f32(path: Path, value: np.ndarray) -> None:
    np.asarray(value, dtype="<f4").tofile(path)


def finite_stats(value: np.ndarray) -> dict[str, float]:
    arr = np.asarray(value, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"median": math.nan, "mean": math.nan, "min": math.nan, "max": math.nan}
    return {
        "median": float(np.median(finite)),
        "mean": float(np.mean(finite)),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
    }


def write_depth_index(
    *,
    out_dir: Path,
    capture_dir: Path,
    model_path: Path,
    bundle: dict[str, Any],
    k_windows: dict[str, Any],
    model_policy: dict[str, Any],
    window_reports: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    height: int,
    width: int,
    model_input_names: list[str],
    model_input_contract: str,
    elapsed_s: float,
) -> None:
    completed = len([frame for frame in frames if frame.get("status") == "completed"])
    model = effective_model_policy(
        model_policy or k_windows.get("model") or {},
        model_path=model_path,
        width=width,
        height=height,
        model_input_contract=model_input_contract,
    )
    depth_index = {
        "schema_version": "aether_depth_index_v1",
        "status": "completed",
        "source_manifest": "photo_bundle.json",
        "model_policy_path": "model_policy.json",
        "k_windows_path": "da3_k_windows.json",
        "input_size_locked": True,
        "input_size_status": str(
            model.get("inputSizeStatus")
            or "locked_da3_base_k35_476x742_benchmark_2026_05_25"
        ),
        "input_width": width,
        "input_height": height,
        "model": model,
        "mac_research_executor": {
            "schema_version": "aether_mac_da3_coreml_window_export_v1",
            "model_path": str(model_path),
            "model_input_names": model_input_names,
            "da3_input_contract": model_input_contract,
            "capture_dir": str(capture_dir),
            "elapsed_s": elapsed_s,
            "note": "Mac research export of the selected DA3 CoreML model; phone thermal/RSS is not part of this benchmark.",
        },
        "k_window_graph": {
            "windowing_policy": k_windows.get("windowingPolicy", {}),
            "bridge_graph": k_windows.get("bridgeGraph", []),
            "loop_closure_policy": k_windows.get("loopClosurePolicy", {}),
            "loop_candidates": k_windows.get("loopCandidates", []),
            "uncovered_frame_ids": k_windows.get("uncoveredFrameIDs", []),
        },
        "window_count": len(window_reports),
        "frame_count": len(frames),
        "completed_count": completed,
        "pending_count": 0,
        "failed_count": len(frames) - completed,
        "depth_meta_schema_version": 2,
        "geometry_contract": {
            "producer": "DA3-BASE CoreML",
            "model_resource": da3_model_resource(model, model_path),
            "da3_input_contract": model_input_contract,
            "official_streaming_baseline": model_input_contract == "image_only",
            "camera_input_role": (
                "none_official_image_only"
                if model_input_contract == "image_only"
                else "pose_conditioned_compatibility_only"
            ),
            "pose_outputs": ["predExtrinsicsPath", "predIntrinsicsPath"],
            "depth_outputs": ["relativeDepthPath", "confidencePath"],
            "downstream_consumers": [
                "pre_sap_uncertainty_research",
                "pointcloud",
                "mesh",
                "texture",
                "highlight_specular",
            ],
        },
        "frames": frames,
    }
    write_json(out_dir / "depth_index.json", depth_index)
    report = {
        "schema_version": "aether_da3_depth_runner_report_v1",
        "status": "completed",
        "rule": "Mac research executor runs sealed DA3 CoreML windows; Dart manifests still own the policy.",
        "model": depth_index["model"],
        "window_count": len(window_reports),
        "frame_count": len(frames),
        "completed_count": completed,
        "windows": window_reports,
    }
    write_json(out_dir / "depth_runner_report.json", report)


if __name__ == "__main__":
    raise SystemExit(main())
