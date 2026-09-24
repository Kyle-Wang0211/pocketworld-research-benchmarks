#!/usr/bin/env python3
"""Create a strict timestamp-ordered DA3-BASE K35 capture mirror.

This is a research-only data organizer. It does not score images, build graph
patches, retrieve neighbors, or change DA3 inputs. It sorts the existing
capture manifests by the recorded capture timestamp and writes fixed K=35,
overlap=18 sliding windows.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--out-capture", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=35)
    parser.add_argument("--overlap", type=int, default=18)
    parser.add_argument("--order-field", default="timestamp")
    args = parser.parse_args()

    source = args.source_capture.resolve()
    out = args.out_capture.resolve()
    out.mkdir(parents=True, exist_ok=True)

    bundle = read_json(source / "photo_bundle.json")
    input_manifest = read_json(source / "da3_input_manifest.json")
    model_policy = read_json(source / "model_policy.json")

    sorted_frames = sort_frames(bundle.get("frames") or [], args.order_field)
    frame_ids = [str(frame["id"]) for frame in sorted_frames]
    input_by_id = {str(frame["id"]): frame for frame in input_manifest.get("frames", [])}
    missing_input = [frame_id for frame_id in frame_ids if frame_id not in input_by_id]
    if missing_input:
        raise ValueError(f"Missing da3_input_manifest rows for {len(missing_input)} frames")

    sorted_inputs = [input_by_id[frame_id] for frame_id in frame_ids]
    sorted_bundle = dict(bundle)
    sorted_bundle["frames"] = sorted_frames
    sorted_bundle["frameCount"] = len(sorted_frames)
    sorted_input_manifest = dict(input_manifest)
    sorted_input_manifest["frames"] = sorted_inputs
    sorted_input_manifest["frameCount"] = len(sorted_inputs)

    selected_model = dict(model_policy.get("selectedDepthModel") or {})
    if not selected_model:
        selected_model = {
            "id": "DA3-BASE",
            "license": "Apache-2.0",
            "resourceName": "DA3BASE_476x742_N35_pose",
            "windowSize": args.chunk_size,
            "inputWidth": 742,
            "inputHeight": 476,
            "commercialSafe": True,
        }

    windows = build_windows(frame_ids, args.chunk_size, args.overlap)
    order_values = [float(frame[args.order_field]) for frame in sorted_frames]
    plan: dict[str, Any] = {
        "schemaVersion": "aether_da3_k_windows_v1",
        "sourceManifest": "photo_bundle.json",
        "sourceViewGraph": "strict_capture_timestamp_order",
        "model": selected_model,
        "windowSize": args.chunk_size,
        "windowingPolicy": {
            "policy": "strict_official_da3_streaming_timestamp_sliding_window",
            "chunkSize": args.chunk_size,
            "overlap": args.overlap,
            "step": args.chunk_size - args.overlap,
            "orderBasis": {
                "manifest": "photo_bundle.json",
                "field": f"frames[].{args.order_field}",
                "tieBreak": "original manifest index",
                "ascending": True,
            },
        },
        "loopClosurePolicy": {"policy": "disabled_for_strict_baseline"},
        "inputSizeLocked": True,
        "inputHeight": int(selected_model.get("inputHeight") or 476),
        "inputWidth": int(selected_model.get("inputWidth") or 742),
        "bridgeGraph": build_bridge_graph(windows),
        "loopCandidates": [],
        "uncoveredFrameIDs": [],
        "uncoveredFrameCount": 0,
        "windowCount": len(windows),
        "windows": windows,
    }

    write_json(out / "photo_bundle.json", sorted_bundle)
    write_json(out / "da3_input_manifest.json", sorted_input_manifest)
    link_or_copy(source / "model_policy.json", out / "model_policy.json")
    for name in ("photos_depth", "photos_highres", "previews"):
        src = source / name
        if src.exists():
            link_or_copy(src, out / name)
    write_json(out / "da3_k_windows.json", plan)
    write_json(
        out / "official_streaming_capture_manifest.json",
        {
            "sourceCapture": str(source),
            "outCapture": str(out),
            "frameCount": len(frame_ids),
            "windowCount": len(windows),
            "chunkSize": args.chunk_size,
            "overlap": args.overlap,
            "step": args.chunk_size - args.overlap,
            "orderBasis": {
                "manifest": "photo_bundle.json",
                "field": f"frames[].{args.order_field}",
                "tieBreak": "original manifest index",
                "ascending": True,
            },
            "firstFrameID": frame_ids[0] if frame_ids else None,
            "lastFrameID": frame_ids[-1] if frame_ids else None,
            "firstTimestamp": order_values[0] if order_values else None,
            "lastTimestamp": order_values[-1] if order_values else None,
            "timestampMonotonic": all(
                order_values[index] <= order_values[index + 1]
                for index in range(len(order_values) - 1)
            ),
        },
    )
    return 0


def sort_frames(frames: list[dict[str, Any]], order_field: str) -> list[dict[str, Any]]:
    missing = [str(frame.get("id")) for frame in frames if order_field not in frame]
    if missing:
        raise ValueError(f"Missing {order_field!r} for {len(missing)} frames")
    return [
        dict(frame)
        for _, frame in sorted(
            enumerate(frames),
            key=lambda item: (float(item[1][order_field]), item[0]),
        )
    ]


def build_windows(frame_ids: list[str], chunk_size: int, overlap: int) -> list[dict[str, Any]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not frame_ids:
        return []
    step = chunk_size - overlap
    windows: list[dict[str, Any]] = []
    start = 0
    seen_starts: set[int] = set()
    while start < len(frame_ids):
        end = min(start + chunk_size, len(frame_ids))
        chunk = frame_ids[start:end]
        if len(chunk) < chunk_size:
            if windows:
                start = max(0, len(frame_ids) - chunk_size)
                if start in seen_starts:
                    break
                chunk = frame_ids[start : len(frame_ids)]
            else:
                chunk = chunk + [chunk[-1]] * (chunk_size - len(chunk))
        seen_starts.add(start)
        window_index = len(windows)
        window_id = f"window_{window_index:03d}"
        parent_id = None if window_index == 0 else f"window_{window_index - 1:03d}"
        previous_ids = set(windows[-1]["frameIDs"]) if windows else set()
        bridge_ids = [frame_id for frame_id in chunk if frame_id in previous_ids]
        core_ids = chunk if window_index == 0 else [frame_id for frame_id in chunk if frame_id not in set(bridge_ids)]
        windows.append(
            {
                "id": window_id,
                "modelTag": "da3:base:k35:476x742:strict-timestamp",
                "modelResourceName": "DA3BASE_476x742_N35_pose",
                "selectionMode": "strict_timestamp_sequential_chunk",
                "frameIDs": chunk,
                "uniqueFrameIDs": list(dict.fromkeys(chunk)),
                "coreFrameIDs": core_ids,
                "bridgeFrameIDs": bridge_ids,
                "parentWindowID": parent_id,
                "bridgeRule": "timestamp_order_previous_tail_to_current_head",
                "chunkStartIndex": start,
                "chunkEndIndexExclusive": min(start + chunk_size, len(frame_ids)),
                "officialChunkIndex": window_index,
            }
        )
        if end == len(frame_ids):
            break
        start += step
    return windows


def build_bridge_graph(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for window in windows:
        parent = window.get("parentWindowID")
        if not parent:
            continue
        edges.append(
            {
                "parentWindowID": parent,
                "childWindowID": window["id"],
                "bridgeFrameIDs": window.get("bridgeFrameIDs", []),
                "rule": "timestamp_order_previous_tail_to_current_head",
            }
        )
    return edges


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        return
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            raise RuntimeError(f"Could not symlink directory {src} -> {dst}")
        dst.write_bytes(src.read_bytes())


if __name__ == "__main__":
    raise SystemExit(main())
