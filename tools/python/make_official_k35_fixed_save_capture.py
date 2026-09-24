#!/usr/bin/env python3
"""Create fixed-K35 captures with official DA3 streaming save semantics.

Official DA3 streaming saves the non-overlap head of every non-final chunk and
drops each chunk's overlap tail. The next chunk then writes that chronological
region. This script keeps that save rule intact while adapting the final short
chunk to a fixed K=35 CoreML model by repeating the last real frame as padding.
Padding slots are explicit and are never marked as official-save slots.
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
    parser.add_argument("--overlap", type=int, required=True)
    parser.add_argument("--official-default-chunk-size", type=int, default=120)
    parser.add_argument("--official-default-overlap", type=int, default=60)
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
    windows = build_windows(
        frame_ids,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
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

    saved_frame_ids = [
        frame_id
        for window in windows
        for frame_id in window.get("officialSaveFrameIDs", [])
    ]
    missing_frame_ids = [frame_id for frame_id in frame_ids if frame_id not in set(saved_frame_ids)]
    duplicate_count = len(saved_frame_ids) - len(set(saved_frame_ids))

    plan: dict[str, Any] = {
        "schemaVersion": "aether_da3_k_windows_v1",
        "sourceManifest": "photo_bundle.json",
        "sourceViewGraph": "official_da3_streaming_sequential_order",
        "model": selected_model,
        "windowSize": args.chunk_size,
        "windowingPolicy": {
            "policy": "official_da3_streaming_save_depth_conf_fixed_k35",
            "chunkSize": args.chunk_size,
            "overlap": args.overlap,
            "step": args.chunk_size - args.overlap,
            "officialSaveSemantics": "save local slots 0..step-1 for non-final chunks; save all real slots for final chunk; never save padding slots",
            "tailPaddingPolicy": "repeat_last_real_frame_for_fixed_k35_shape_not_saved",
            "officialReference": {
                "chunkSize": args.official_default_chunk_size,
                "overlap": args.official_default_overlap,
                "source": "Depth-Anything-3 da3_streaming.py save_depth_conf_result",
            },
        },
        "inputSizeLocked": True,
        "inputHeight": int(selected_model.get("inputHeight") or 476),
        "inputWidth": int(selected_model.get("inputWidth") or 742),
        "bridgeGraph": build_bridge_graph(windows),
        "loopCandidates": [],
        "uncoveredFrameIDs": missing_frame_ids,
        "uncoveredFrameCount": len(missing_frame_ids),
        "windowCount": len(windows),
        "officialSavedFrameCount": len(saved_frame_ids),
        "officialSavedUniqueFrameCount": len(set(saved_frame_ids)),
        "officialSavedDuplicateFrameCount": duplicate_count,
        "officialSavedFrameOrderMatchesSource": saved_frame_ids == frame_ids,
        "windows": windows,
    }
    write_json(out / "da3_k_windows.json", plan)
    write_json(
        out / "official_save_capture_manifest.json",
        {
            "sourceCapture": str(source),
            "outCapture": str(out),
            "frameCount": len(frame_ids),
            "windowCount": len(windows),
            "chunkSize": args.chunk_size,
            "overlap": args.overlap,
            "step": args.chunk_size - args.overlap,
            "officialSavedFrameCount": len(saved_frame_ids),
            "officialSavedUniqueFrameCount": len(set(saved_frame_ids)),
            "officialSavedDuplicateFrameCount": duplicate_count,
            "officialSavedFrameOrderMatchesSource": saved_frame_ids == frame_ids,
            "lastWindow": windows[-1] if windows else None,
        },
    )
    write_markdown(out / "official_save_capture_manifest_zh.md", plan)
    print(
        json.dumps(
            {
                "out_capture": str(out),
                "frame_count": len(frame_ids),
                "window_count": len(windows),
                "chunk_size": args.chunk_size,
                "overlap": args.overlap,
                "step": args.chunk_size - args.overlap,
                "official_saved_frames": len(saved_frame_ids),
                "duplicates": duplicate_count,
                "missing": len(missing_frame_ids),
                "order_matches_source": saved_frame_ids == frame_ids,
                "last_window": windows[-1] if windows else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_windows(frame_ids: list[str], *, chunk_size: int, overlap: int) -> list[dict[str, Any]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >=0 and smaller than chunk_size")
    if not frame_ids:
        return []

    step = chunk_size - overlap
    starts = official_chunk_starts(len(frame_ids), chunk_size=chunk_size, overlap=overlap)
    windows: list[dict[str, Any]] = []
    for window_index, start in enumerate(starts):
        real_end = min(start + chunk_size, len(frame_ids))
        real_ids = frame_ids[start:real_end]
        if not real_ids:
            raise ValueError(f"empty chunk at start={start}")
        padding_count = max(0, chunk_size - len(real_ids))
        padding_ids = [real_ids[-1]] * padding_count
        frame_ids_k = real_ids + padding_ids
        is_last = window_index == len(starts) - 1
        if is_last:
            save_slots = list(range(len(real_ids)))
        else:
            save_slots = list(range(min(step, len(real_ids))))
        save_ids = [frame_ids_k[slot] for slot in save_slots]
        dropped_tail_slots = [
            slot
            for slot in range(len(real_ids))
            if slot not in set(save_slots)
        ]

        window_id = f"window_{window_index:03d}"
        parent_id = None if window_index == 0 else f"window_{window_index - 1:03d}"
        windows.append(
            {
                "id": window_id,
                "modelTag": "da3:base:k35:476x742:official-save",
                "modelResourceName": "DA3BASE_476x742_N35_pose",
                "selectionMode": "official_da3_streaming_save_depth_conf_fixed_k35",
                "frameIDs": frame_ids_k,
                "realFrameIDs": real_ids,
                "paddingFrameIDs": padding_ids,
                "paddingSlotIndices": list(range(len(real_ids), chunk_size)),
                "uniqueFrameIDs": list(dict.fromkeys(real_ids)),
                "coreFrameIDs": save_ids,
                "officialSaveFrameIDs": save_ids,
                "officialSaveSlotIndices": save_slots,
                "officialDroppedTailFrameIDs": [frame_ids_k[slot] for slot in dropped_tail_slots],
                "officialDroppedTailSlotIndices": dropped_tail_slots,
                "bridgeFrameIDs": [frame_ids_k[slot] for slot in dropped_tail_slots],
                "parentWindowID": parent_id,
                "bridgeRule": "official_da3_drop_tail_overlap_save_next_chunk_head",
                "chunkStartIndex": start,
                "chunkEndIndexExclusive": real_end,
                "realFrameCount": len(real_ids),
                "paddingFrameCount": padding_count,
                "officialSavedFrameCount": len(save_ids),
                "officialChunkIndex": window_index,
            }
        )
    return windows


def official_chunk_starts(frame_count: int, *, chunk_size: int, overlap: int) -> list[int]:
    if frame_count <= chunk_size:
        return [0]
    step = chunk_size - overlap
    starts: list[int] = []
    start = 0
    while start < frame_count:
        starts.append(start)
        if start + chunk_size >= frame_count:
            break
        start += step
    return starts


def build_bridge_graph(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges = []
    for window in windows:
        parent = window.get("parentWindowID")
        if not parent:
            continue
        edges.append(
            {
                "parentWindowID": parent,
                "childWindowID": window["id"],
                "droppedTailFrameIDs": window.get("officialDroppedTailFrameIDs", []),
                "childSavedFrameIDs": window.get("officialSaveFrameIDs", []),
                "rule": "official_save_non_overlap_head_drop_tail_overlap",
            }
        )
    return edges


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, plan: dict[str, Any]) -> None:
    policy = plan["windowingPolicy"]
    lines = [
        "# Official Save Capture",
        "",
        "## 语义",
        "",
        "- 非最后窗口：只保存窗口头部 `step = chunk_size - overlap` 张。",
        "- 尾部 overlap 不保存；它只用于下一窗口对齐。",
        "- 最后窗口：保存所有真实帧。",
        "- 固定 K35 CoreML 的最后短窗口使用重复最后一张做 padding，但 padding 槽位不保存。",
        "",
        "## Summary",
        "",
        f"- chunk_size: {policy['chunkSize']}",
        f"- overlap: {policy['overlap']}",
        f"- step: {policy['step']}",
        f"- window_count: {plan['windowCount']}",
        f"- saved_frames: {plan['officialSavedFrameCount']}",
        f"- saved_unique_frames: {plan['officialSavedUniqueFrameCount']}",
        f"- duplicate_saved_frames: {plan['officialSavedDuplicateFrameCount']}",
        f"- order_matches_source: {plan['officialSavedFrameOrderMatchesSource']}",
        "",
        "## Windows",
        "",
        "| window | start | end | real | padding | saved | save_slots |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for window in plan["windows"]:
        lines.append(
            "| {id} | {start} | {end} | {real} | {pad} | {saved} | {slots} |".format(
                id=window["id"],
                start=window["chunkStartIndex"],
                end=window["chunkEndIndexExclusive"],
                real=window["realFrameCount"],
                pad=window["paddingFrameCount"],
                saved=window["officialSavedFrameCount"],
                slots=",".join(str(v) for v in window["officialSaveSlotIndices"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
