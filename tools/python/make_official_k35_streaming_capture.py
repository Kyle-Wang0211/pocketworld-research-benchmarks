#!/usr/bin/env python3
"""Create a DA3-BASE K35 capture directory that follows official streaming chunks.

This script does not choose a new algorithm. It only converts an existing
PocketWorld capture into the same kind of sequential sliding-window chunk plan
used by the official DA3-Streaming runner, scaled to the fixed commercial
DA3-BASE CoreML K=35 model.
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
    parser.add_argument("--loop-chunk-half-window", type=int, default=8)
    args = parser.parse_args()

    source = args.source_capture.resolve()
    out = args.out_capture.resolve()
    out.mkdir(parents=True, exist_ok=True)

    for name in ["photo_bundle.json", "da3_input_manifest.json", "model_policy.json"]:
      link_or_copy(source / name, out / name)
    for name in ["photos_depth", "photos_highres", "previews"]:
      src = source / name
      if src.exists():
        link_or_copy(src, out / name)

    bundle = read_json(source / "photo_bundle.json")
    model_policy = read_json(source / "model_policy.json")
    frames = list(bundle.get("frames") or [])
    frame_ids = [str(frame["id"]) for frame in frames]
    windows = build_windows(frame_ids, args.chunk_size, args.overlap)

    selected_model = dict(model_policy.get("selectedDepthModel") or {})
    if not selected_model:
      selected_model = {
          "id": "DA3-BASE",
          "license": "Apache-2.0",
          "resourceName": "DA3BASE_476x742_N35_pose",
          "windowSize": 35,
          "inputWidth": 742,
          "inputHeight": 476,
          "commercialSafe": True,
      }

    plan: dict[str, Any] = {
        "schemaVersion": "aether_da3_k_windows_v1",
        "sourceManifest": "photo_bundle.json",
        "sourceViewGraph": "official_da3_streaming_sequential_order",
        "model": selected_model,
        "windowSize": args.chunk_size,
        "windowingPolicy": {
            "policy": "official_da3_streaming_sliding_window_scaled_to_k35",
            "chunkSize": args.chunk_size,
            "overlap": args.overlap,
            "step": args.chunk_size - args.overlap,
            "officialReference": {
                "chunkSize": 120,
                "overlap": 60,
                "scalingReason": "commercial DA3-BASE CoreML bundle is fixed at K=35",
            },
        },
        "loopClosurePolicy": {
            "policy": "official_da3_streaming_loop_scaled_to_k35",
            "loopChunkHalfWindow": args.loop_chunk_half_window,
            "loopChunkForwardSlots": args.chunk_size,
            "note": "Official process_loop_list returns two local ranges around a proposed loop pair. The K35 CoreML runner keeps the combined loop chunk <=35 slots, then pads unused slots explicitly for the fixed K=35 model shape.",
        },
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
    write_json(out / "da3_k_windows.json", plan)
    write_json(out / "official_streaming_capture_manifest.json", {
        "sourceCapture": str(source),
        "outCapture": str(out),
        "frameCount": len(frame_ids),
        "windowCount": len(windows),
        "chunkSize": args.chunk_size,
        "overlap": args.overlap,
        "step": args.chunk_size - args.overlap,
    })
    return 0


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
    while start < len(frame_ids):
        end = min(start + chunk_size, len(frame_ids))
        chunk = frame_ids[start:end]
        if len(chunk) < chunk_size:
            if windows:
                start = max(0, len(frame_ids) - chunk_size)
                chunk = frame_ids[start:len(frame_ids)]
            else:
                chunk = chunk + [chunk[-1]] * (chunk_size - len(chunk))
        window_index = len(windows)
        window_id = f"window_{window_index:03d}"
        parent_id = None if window_index == 0 else f"window_{window_index - 1:03d}"
        bridge_ids = [] if window_index == 0 else chunk[:overlap]
        core_ids = chunk if window_index == 0 else chunk[overlap:]
        windows.append({
            "id": window_id,
            "modelTag": "da3:base:k35:476x742:official-streaming",
            "modelResourceName": "DA3BASE_476x742_N35_pose",
            "selectionMode": "official_da3_streaming_sequential_chunk",
            "frameIDs": chunk,
            "uniqueFrameIDs": list(dict.fromkeys(chunk)),
            "coreFrameIDs": core_ids,
            "bridgeFrameIDs": bridge_ids,
            "parentWindowID": parent_id,
            "bridgeRule": "official_overlap_previous_tail_to_current_head",
            "chunkStartIndex": start,
            "chunkEndIndexExclusive": min(start + chunk_size, len(frame_ids)),
            "officialChunkIndex": window_index,
        })
        if end == len(frame_ids):
            break
        start += step
    return windows


def build_bridge_graph(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges = []
    for window in windows:
        parent = window.get("parentWindowID")
        if not parent:
            continue
        edges.append({
            "parentWindowID": parent,
            "childWindowID": window["id"],
            "bridgeFrameIDs": window.get("bridgeFrameIDs", []),
            "rule": "official_overlap_previous_tail_to_current_head",
        })
    return edges


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        return
    if not src.exists():
        return
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            raise RuntimeError(f"Could not symlink directory {src} -> {dst}")
        dst.write_bytes(src.read_bytes())


if __name__ == "__main__":
    raise SystemExit(main())
