#!/usr/bin/env python3
"""Commercial-safe VPR loop retrieval for the DA3-BASE K35 streaming baseline.

This script keeps the official DA3-Streaming boundary:

  images -> VPR loop pairs -> official process_loop_list -> loop chunk windows

The DA3 model forward, dense Sim3, and Sim3LoopOptimizer remain separate stages.
The only backend-specific part here is descriptor extraction.  Candidate
filtering mirrors the official loop_detector.py parameters: top-k, similarity
threshold, temporal gap, and NMS threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image, ImageOps


RESEARCH_ROOT = Path(__file__).resolve().parents[2]
BOQ_REPO = RESEARCH_ROOT / "tools/vendor/vpr/Bag-of-Queries"
SELAVPR_REPO = RESEARCH_ROOT / "tools/vendor/vpr/SelaVPRplusplus"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--da3-out-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--backend", choices=["boq-dinov2", "selavprpp"], required=True)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "mps", "cuda"])
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--similarity-threshold", type=float, default=0.85)
    parser.add_argument("--min-frame-gap", type=int, default=10)
    parser.add_argument("--nms-threshold", type=int, default=25)
    parser.add_argument("--loop-half-window", type=int, default=8)
    parser.add_argument("--window-size", type=int, default=35)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    out_dir = args.out_dir / args.backend
    out_dir.mkdir(parents=True, exist_ok=True)
    descriptor_path = out_dir / "descriptors.npy"
    descriptor_meta_path = out_dir / "descriptor_meta.json"
    retrieval_report_path = out_dir / "loop_retrieval_report.json"
    loop_capture_dir = out_dir / "loop_capture"

    bundle = read_json(args.capture_dir / "photo_bundle.json")
    base_plan = read_json(args.capture_dir / "da3_k_windows.json")
    frames = list(bundle.get("frames") or [])
    frame_ids = [str(frame["id"]) for frame in frames]
    image_paths = image_paths_for_frames(args.capture_dir, frames)

    if args.resume and descriptor_path.exists() and descriptor_meta_path.exists():
        descriptors = np.load(descriptor_path)
        descriptor_meta = read_json(descriptor_meta_path)
    else:
        model, device, transform = load_backend(args.backend, args.device)
        descriptors = extract_descriptors(
            model=model,
            device=device,
            transform=transform,
            image_paths=image_paths,
            batch_size=args.batch_size,
        )
        descriptor_meta = {
            "backend": args.backend,
            "device": str(device),
            "frame_count": len(frame_ids),
            "descriptor_shape": list(descriptors.shape),
            "descriptor_dtype": str(descriptors.dtype),
            "elapsed_s": round(time.perf_counter() - started, 3),
        }
        np.save(descriptor_path, descriptors)
        write_json(descriptor_meta_path, descriptor_meta)

    raw_loop_closures, threshold_sweep = find_loop_closures(
        descriptors=descriptors,
        top_k=args.top_k,
        threshold=args.similarity_threshold,
        min_frame_gap=args.min_frame_gap,
        nms_threshold=args.nms_threshold,
    )
    chunk_indices = chunk_indices_from_plan(base_plan)
    loop_pairs = [(int(i), int(j)) for i, j, _ in raw_loop_closures]
    loop_results = remove_duplicate_chunk_pairs(
        process_loop_list(chunk_indices, loop_pairs, half_window=args.loop_half_window)
    )
    loop_windows = build_loop_windows(
        loop_results=loop_results,
        raw_loop_closures=raw_loop_closures,
        frame_ids=frame_ids,
        window_size=args.window_size,
    )
    create_loop_capture(
        source_capture=args.capture_dir,
        out_capture=loop_capture_dir,
        base_plan=base_plan,
        loop_windows=loop_windows,
        args=args,
    )

    report = {
        "schema_version": "aether_official_da3_k35_vpr_loop_retrieval_v1",
        "backend": args.backend,
        "license": backend_license(args.backend),
        "commercial_safe": True,
        "official_route": [
            "DA3-BASE K35@476x742 sequential chunks already exported",
            "VPR loop retrieval backend proposes loop pairs",
            "official process_loop_list maps loop pairs to chunk-local ranges",
            "fixed K35 CoreML loop capture is generated for official loop chunk forward",
        ],
        "fixed_coreml_k35_note": (
            "Official Python DA3 can forward variable loop chunks. The production "
            "CoreML model is fixed at K=35, so loopHalfWindow is capped so the "
            "two official ranges fit into one K35 loop chunk; any unused slots "
            "are explicit duplicate padding and excluded from Sim3 range metadata."
        ),
        "parameters": {
            "top_k": args.top_k,
            "similarity_threshold": args.similarity_threshold,
            "min_frame_gap": args.min_frame_gap,
            "nms_threshold": args.nms_threshold,
            "loop_half_window": args.loop_half_window,
            "window_size": args.window_size,
        },
        "descriptor_meta": descriptor_meta,
        "frame_count": len(frame_ids),
        "base_window_count": int(base_plan.get("windowCount") or len(base_plan.get("windows", []))),
        "chunk_indices": chunk_indices,
        "raw_loop_pair_count": len(raw_loop_closures),
        "loop_result_count": len(loop_results),
        "loop_window_count": len(loop_windows),
        "threshold_sweep": threshold_sweep,
        "top_loop_pairs": [
            {
                "later_index": int(i),
                "earlier_index": int(j),
                "similarity": float(score),
                "later_frame_id": frame_ids[int(i)] if 0 <= int(i) < len(frame_ids) else None,
                "earlier_frame_id": frame_ids[int(j)] if 0 <= int(j) < len(frame_ids) else None,
            }
            for i, j, score in raw_loop_closures[:20]
        ],
        "loop_capture_dir": str(loop_capture_dir),
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    write_json(retrieval_report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def load_backend(backend: str, requested_device: str) -> tuple[torch.nn.Module, torch.device, Any]:
    device = resolve_device(requested_device)
    if backend == "boq-dinov2":
        model = torch.hub.load(
            str(BOQ_REPO),
            "get_trained_boq",
            source="local",
            backbone_name="dinov2",
            output_dim=12288,
        )
        image_size = (322, 322)
    elif backend == "selavprpp":
        model = torch.hub.load(
            str(SELAVPR_REPO),
            "SelaVPRplusplus",
            source="local",
            backbone="dinov2-base",
            aggregation="gem",
            hashing=False,
            rerank=False,
        )
        if isinstance(model, torch.nn.DataParallel):
            model = model.module
        image_size = (322, 322)
    else:
        raise ValueError(f"Unknown backend: {backend}")

    model.eval()
    model.to(device)
    transform = T.Compose(
        [
            T.ToTensor(),
            T.Resize(image_size, interpolation=T.InterpolationMode.BICUBIC, antialias=True),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    return model, device, transform


def resolve_device(raw: str) -> torch.device:
    if raw == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    if raw == "cuda" and not torch.cuda.is_available():
        return torch.device("cpu")
    if raw == "mps":
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(raw)


def extract_descriptors(
    *,
    model: torch.nn.Module,
    device: torch.device,
    transform: Any,
    image_paths: list[Path],
    batch_size: int,
) -> np.ndarray:
    descriptors: list[np.ndarray] = []
    for start in range(0, len(image_paths), batch_size):
        batch_paths = image_paths[start : start + batch_size]
        batch = []
        for path in batch_paths:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                batch.append(transform(image))
        tensor = torch.stack(batch, dim=0).to(device)
        with torch.inference_mode():
            output = model(tensor)
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, list):
            output = output[0]
        if isinstance(output, tuple):
            output = output[0]
        desc = output.detach().float().cpu().numpy()
        descriptors.append(desc)
        print(f"descriptor_batch {min(start + batch_size, len(image_paths))}/{len(image_paths)}")
    all_desc = np.concatenate(descriptors, axis=0).astype(np.float32)
    norm = np.linalg.norm(all_desc, axis=1, keepdims=True)
    return all_desc / np.maximum(norm, 1e-12)


def find_loop_closures(
    *,
    descriptors: np.ndarray,
    top_k: int,
    threshold: float,
    min_frame_gap: int,
    nms_threshold: int,
) -> tuple[list[tuple[int, int, float]], list[dict[str, Any]]]:
    similarities = descriptors @ descriptors.T
    np.fill_diagonal(similarities, -np.inf)
    sweep = []
    for candidate_threshold in [0.70, 0.75, 0.80, 0.85, 0.90]:
        pairs = raw_pairs_from_similarity(similarities, top_k, candidate_threshold, min_frame_gap)
        sweep.append(
            {
                "threshold": candidate_threshold,
                "raw_pair_count": len(pairs),
                "nms_pair_count": len(apply_official_nms(pairs, nms_threshold)),
            }
        )
    pairs = raw_pairs_from_similarity(similarities, top_k, threshold, min_frame_gap)
    return apply_official_nms(pairs, nms_threshold), sweep


def raw_pairs_from_similarity(
    similarities: np.ndarray,
    top_k: int,
    threshold: float,
    min_frame_gap: int,
) -> list[tuple[int, int, float]]:
    pairs: dict[tuple[int, int], float] = {}
    for i in range(similarities.shape[0]):
        row = similarities[i]
        if top_k + 1 >= row.shape[0]:
            indices = np.argsort(row)[::-1]
        else:
            indices = np.argpartition(row, -(top_k + 1))[-(top_k + 1) :]
            indices = indices[np.argsort(row[indices])[::-1]]
        kept = 0
        for j in indices:
            score = float(row[j])
            if not np.isfinite(score):
                continue
            if kept >= top_k:
                break
            kept += 1
            if score <= threshold or abs(i - int(j)) <= min_frame_gap:
                continue
            earlier, later = sorted((int(i), int(j)))
            key = (later, earlier)
            pairs[key] = max(score, pairs.get(key, -np.inf))
    rows = [(later, earlier, score) for (later, earlier), score in pairs.items()]
    rows.sort(key=lambda item: item[2], reverse=True)
    return rows


def apply_official_nms(
    loop_closures: list[tuple[int, int, float]], nms_threshold: int
) -> list[tuple[int, int, float]]:
    if not loop_closures or nms_threshold <= 0:
        return loop_closures
    sorted_loops = sorted(loop_closures, key=lambda x: x[2], reverse=True)
    filtered = []
    suppressed: set[int] = set()
    max_frame = max(max(idx1, idx2) for idx1, idx2, _ in loop_closures)
    for idx1, idx2, sim in sorted_loops:
        if idx1 in suppressed or idx2 in suppressed:
            continue
        filtered.append((idx1, idx2, sim))
        suppress_range: set[int] = set()
        start1 = max(0, idx1 - nms_threshold)
        end1 = min(idx1 + nms_threshold + 1, idx2)
        suppress_range.update(range(start1, end1))
        start2 = max(idx1 + 1, idx2 - nms_threshold)
        end2 = min(idx2 + nms_threshold + 1, max_frame + 1)
        suppress_range.update(range(start2, end2))
        suppressed.update(suppress_range)
    return filtered


def remove_duplicate_chunk_pairs(data: list[tuple[int, tuple[int, int], int, tuple[int, int]]]) -> list[tuple[int, tuple[int, int], int, tuple[int, int]]]:
    seen = set()
    result = []
    for item in data:
        if item[0] == item[2]:
            continue
        key = (item[0], item[2])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def find_chunk_index(chunks: list[tuple[int, int]], idx: int) -> int:
    """Official DA3-Streaming sim3utils.find_chunk_index, kept local to avoid Triton import."""
    starts = [chunk[0] for chunk in chunks]
    pos = int(np.searchsorted(starts, idx, side="right") - 1)
    if pos < 0 or pos >= len(chunks):
        raise ValueError(f"Index {idx} not found in any chunk")
    chunk_begin, chunk_end = chunks[pos]
    if idx < chunk_begin or idx > chunk_end:
        raise ValueError(f"Index {idx} not found in any chunk")
    return pos


def get_frame_range(chunk: tuple[int, int], idx: int, half_window: int = 10) -> tuple[int, int]:
    """Official DA3-Streaming sim3utils.get_frame_range."""
    begin, end = chunk
    window_size = 2 * half_window
    if idx - half_window < begin:
        start = begin
        end = min(end, begin + window_size)
    elif idx + half_window > end:
        end_candidate = end
        start = max(begin, end - window_size)
        end = end_candidate
    else:
        start = idx - half_window
        end = idx + half_window
    return (start, end)


def process_loop_list(
    chunk_index: list[tuple[int, int]],
    loop_list: list[tuple[int, int]],
    half_window: int = 10,
) -> list[tuple[int, tuple[int, int], int, tuple[int, int]]]:
    """Official DA3-Streaming sim3utils.process_loop_list."""
    results = []
    for idx1, idx2 in loop_list:
        try:
            chunk_idx1_0based = find_chunk_index(chunk_index, idx1)
            chunk1 = chunk_index[chunk_idx1_0based]
            range1 = get_frame_range(chunk1, idx1, half_window)

            chunk_idx2_0based = find_chunk_index(chunk_index, idx2)
            chunk2 = chunk_index[chunk_idx2_0based]
            range2 = get_frame_range(chunk2, idx2, half_window)

            result = (chunk_idx1_0based, range1, chunk_idx2_0based, range2)
            results.append(result)
        except ValueError as exc:
            print(f"Skipping pair ({idx1}, {idx2}): {exc}")
    return results


def build_loop_windows(
    *,
    loop_results: list[tuple[int, tuple[int, int], int, tuple[int, int]]],
    raw_loop_closures: list[tuple[int, int, float]],
    frame_ids: list[str],
    window_size: int,
) -> list[dict[str, Any]]:
    score_by_pair = {(int(i), int(j)): float(score) for i, j, score in raw_loop_closures}
    windows = []
    for index, (chunk_a, range_a, chunk_b, range_b) in enumerate(loop_results):
        ids_a = frame_ids[range_a[0] : range_a[1]]
        ids_b = frame_ids[range_b[0] : range_b[1]]
        combined = ids_a + ids_b
        if not combined:
            continue
        if len(combined) > window_size:
            combined = combined[:window_size]
        pad_count = max(0, window_size - len(combined))
        padding = [combined[-1]] * pad_count
        frame_ids_k = combined + padding
        windows.append(
            {
                "id": f"loop_window_{index:03d}",
                "modelTag": "da3:base:k35:476x742:official-loop",
                "modelResourceName": "DA3BASE_476x742_N35_pose",
                "selectionMode": "official_da3_streaming_loop_chunk",
                "frameIDs": frame_ids_k,
                "uniqueFrameIDs": list(dict.fromkeys(frame_ids_k)),
                "coreFrameIDs": frame_ids_k,
                "bridgeFrameIDs": [],
                "parentWindowID": None,
                "loopChunk": {
                    "chunkIndexA": int(chunk_a),
                    "chunkIndexB": int(chunk_b),
                    "rangeA": [int(range_a[0]), int(range_a[1])],
                    "rangeB": [int(range_b[0]), int(range_b[1])],
                    "slotRangeA": [0, len(ids_a)],
                    "slotRangeB": [len(ids_a), len(ids_a) + len(ids_b)],
                    "paddingSlotCount": pad_count,
                    "paddingFrameIDs": padding,
                    "candidateSimilarity": score_by_pair.get((range_a[0], range_b[0])),
                },
            }
        )
    return windows


def create_loop_capture(
    *,
    source_capture: Path,
    out_capture: Path,
    base_plan: dict[str, Any],
    loop_windows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    out_capture.mkdir(parents=True, exist_ok=True)
    for name in ["photo_bundle.json", "da3_input_manifest.json", "model_policy.json"]:
        link_or_copy(source_capture / name, out_capture / name)
    for name in ["photos_depth", "photos_highres", "previews"]:
        src = source_capture / name
        if src.exists():
            link_or_copy(src, out_capture / name)
    plan = {
        "schemaVersion": "aether_da3_k_windows_v1",
        "sourceManifest": "photo_bundle.json",
        "sourceViewGraph": "official_da3_streaming_vpr_loop_chunks",
        "model": base_plan.get("model", {}),
        "windowSize": args.window_size,
        "windowingPolicy": {
            "policy": "official_da3_streaming_loop_chunk_forward_scaled_to_fixed_k35",
            "sourceSequentialWindowingPolicy": base_plan.get("windowingPolicy", {}),
        },
        "loopClosurePolicy": {
            "policy": "official_process_loop_list",
            "backend": args.backend,
            "topK": args.top_k,
            "similarityThreshold": args.similarity_threshold,
            "minFrameGap": args.min_frame_gap,
            "nmsThreshold": args.nms_threshold,
            "loopHalfWindow": args.loop_half_window,
            "fixedK35PaddingPolicy": "repeat_last_frame_for_unused_slots",
        },
        "inputSizeLocked": True,
        "inputHeight": int(base_plan.get("inputHeight") or 476),
        "inputWidth": int(base_plan.get("inputWidth") or 742),
        "bridgeGraph": [],
        "loopCandidates": [],
        "uncoveredFrameIDs": [],
        "uncoveredFrameCount": 0,
        "windowCount": len(loop_windows),
        "windows": loop_windows,
    }
    write_json(out_capture / "da3_k_windows.json", plan)


def chunk_indices_from_plan(plan: dict[str, Any]) -> list[tuple[int, int]]:
    chunks = []
    for window in plan.get("windows", []):
        chunks.append(
            (
                int(window.get("chunkStartIndex", 0)),
                int(window.get("chunkEndIndexExclusive", 0)),
            )
        )
    return chunks


def image_paths_for_frames(capture_dir: Path, frames: list[dict[str, Any]]) -> list[Path]:
    manifest = read_json(capture_dir / "da3_input_manifest.json") if (capture_dir / "da3_input_manifest.json").exists() else {}
    by_id = {str(frame.get("id")): frame for frame in manifest.get("frames", [])}
    paths = []
    for frame in frames:
        frame_id = str(frame["id"])
        rel = by_id.get(frame_id, {}).get("depthImageRelativePath") or f"photos_depth/{frame_id}.jpg"
        paths.append(capture_dir / str(rel))
    return paths


def backend_license(backend: str) -> str:
    if backend == "boq-dinov2":
        return "MIT (Bag-of-Queries repo) + DINOv2 weights/code license must stay documented"
    if backend == "selavprpp":
        return "MIT (SelaVPR++ repo) + DINOv2 weights/code license must stay documented"
    return "unknown"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        return
    if not src.exists():
        return
    src = src.resolve()
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            raise RuntimeError(f"Could not symlink directory {src} -> {dst}")
        dst.write_bytes(src.read_bytes())


if __name__ == "__main__":
    raise SystemExit(main())
