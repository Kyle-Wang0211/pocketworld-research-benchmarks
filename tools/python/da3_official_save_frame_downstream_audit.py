#!/usr/bin/env python3
"""Audit DA3 official save-frame downstream selection after Dart window refresh."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
SUSPECT_FRAME_IDS = [
    "cap-1396",
    "cap-1459",
    "cap-1488",
    "cap-1514",
    "cap-1529",
    "cap-1555",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_save_frame_downstream_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_save_frame_downstream_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    dataset = args.dataset_dir
    capture = dataset / "capture_seq_k35_strict"
    k_windows_path = capture / "da3_k_windows.json"
    old_post = (
        dataset
        / "da3_seq_k35_coreml_pose_dart_camera_contract_window016_cpu_official_postprocess_2026_06_05"
    )
    new_post = (
        dataset
        / "da3_seq_k35_coreml_pose_dart_camera_contract_window016_cpu_official_save_postprocess_2026_06_05"
    )
    k_windows = read_json(k_windows_path)
    old_depth_index = maybe_read_json(old_post / "depth_index.json")
    new_depth_index = maybe_read_json(new_post / "depth_index.json")
    windows_by_id = {str(row.get("id")): row for row in k_windows.get("windows", [])}
    window016 = windows_by_id["window_016"]

    old_frames = old_depth_index.get("frames", [])
    new_frames = new_depth_index.get("frames", [])
    suspect_roles = {frame_id: frame_roles(k_windows, frame_id) for frame_id in SUSPECT_FRAME_IDS}
    downstream_saved_ids = flatten_unique(
        row.get("officialSaveFrameIDs", []) for row in k_windows.get("windows", [])
    )
    all_frame_ids = [
        str(row.get("id"))
        for row in read_json(capture / "photo_bundle.json").get("frames", [])
    ]

    decision_status = (
        "official_save_frame_downstream_aligned"
        if new_depth_index.get("frame_count") == len(window016.get("officialSaveFrameIDs", [])) == 17
        and set(frame["frameID"] for frame in new_frames) == set(window016.get("officialSaveFrameIDs", []))
        and set(downstream_saved_ids) == set(all_frame_ids)
        else "official_save_frame_downstream_incomplete"
    )
    return {
        "schema_version": "aether_official_da3_save_frame_downstream_audit_v1",
        "date": args.date,
        "decision": {
            "status": decision_status,
            "goal_complete": False,
            "conclusion": (
                "Dart refreshed da3_k_windows.json now carries officialSaveFrameIDs/downstreamFrameIDs, "
                "and the corrected official postprocess depth_index for window_016 keeps 17 official downstream frames instead of all 35 CoreML slots."
            ),
            "next_best_action": (
                "Re-run thickness attribution on the corrected official-save depth_index and adjacent window_017 ownership; "
                "do not treat full-chunk tail slots as window_016 downstream evidence."
            ),
        },
        "inputs": {
            "k_windows": str(k_windows_path),
            "k_windows_sha256": sha256(k_windows_path),
            "old_full_chunk_postprocess_depth_index": str(old_post / "depth_index.json"),
            "new_official_save_postprocess_depth_index": str(new_post / "depth_index.json"),
        },
        "official_window_policy": k_windows.get("windowingPolicy", {}),
        "window016": {
            "id": window016.get("id"),
            "chunkStartIndex": window016.get("chunkStartIndex"),
            "chunkEndIndexExclusive": window016.get("chunkEndIndexExclusive"),
            "frameCount": len(window016.get("frameIDs", [])),
            "officialChunkFrameCount": len(window016.get("officialChunkFrameIDs", [])),
            "officialSaveFrameCount": len(window016.get("officialSaveFrameIDs", [])),
            "withheldForNextOverlapFrameCount": len(
                window016.get("withheldForNextOverlapFrameIDs", [])
            ),
            "officialSaveFrameIDs": window016.get("officialSaveFrameIDs", []),
            "withheldForNextOverlapFrameIDs": window016.get(
                "withheldForNextOverlapFrameIDs", []
            ),
            "continuityAudit": window016.get("continuityAudit", {}),
        },
        "depth_index_comparison": {
            "old_full_chunk_frame_count": old_depth_index.get("frame_count"),
            "old_full_chunk_ids_first_last": first_last_ids(old_frames),
            "new_official_save_frame_count": new_depth_index.get("frame_count"),
            "new_official_save_ids_first_last": first_last_ids(new_frames),
            "new_all_frames_marked_official_downstream": all(
                bool(frame.get("officialDownstreamFrame")) for frame in new_frames
            ),
        },
        "global_coverage": {
            "photo_bundle_frame_count": len(all_frame_ids),
            "official_saved_unique_frame_count": len(downstream_saved_ids),
            "uncoveredFrameCount": k_windows.get("uncoveredFrameCount"),
        },
        "suspect_frame_roles": suspect_roles,
        "plain_language": [
            "官方 CoreML/PyTorch chunk 可以算 35 帧，但官方 results_output 不把 35 帧全都交给 downstream。",
            "window_016 的官方 downstream 只有前 17 帧：cap-1346 到 cap-1448；cap-1453 之后是 withheld overlap。",
            "cap-1396 是 window_016 官方 downstream 帧，所以它仍然是 window_016 厚层/几何一致性嫌疑。",
            "cap-1514/cap-1529 不是 window_016 官方 downstream；它们属于 window_016 full-chunk tail，并在 window_017 被官方 downstream 接收。",
            "因此之前 full 35-slot 厚层分析不是废掉，而是要改口径：它说明模型在一个 K35 输入内会产生 tail inconsistency；产品/官方 downstream 应按 save-frame ownership 归因。",
        ],
    }


def frame_roles(k_windows: dict[str, Any], frame_id: str) -> list[dict[str, Any]]:
    roles = []
    for window in k_windows.get("windows", []):
        frame_ids = [str(value) for value in window.get("frameIDs", [])]
        if frame_id not in frame_ids:
            continue
        roles.append(
            {
                "windowID": window.get("id"),
                "localSlot": frame_ids.index(frame_id),
                "officialDownstream": frame_id
                in set(str(value) for value in window.get("officialSaveFrameIDs", [])),
                "withheldForNextOverlap": frame_id
                in set(str(value) for value in window.get("withheldForNextOverlapFrameIDs", [])),
                "bridgeFrame": frame_id
                in set(str(value) for value in window.get("bridgeFrameIDs", [])),
                "coreFrame": frame_id
                in set(str(value) for value in window.get("coreFrameIDs", [])),
            }
        )
    return roles


def first_last_ids(frames: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [str(frame.get("frameID")) for frame in frames]
    return {
        "count": len(ids),
        "first": ids[:5],
        "last": ids[-5:],
    }


def flatten_unique(groups: Any) -> list[str]:
    seen = set()
    out = []
    for group in groups:
        for value in group:
            text = str(value)
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def maybe_read_json(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "window016": {
            "frameCount": report["window016"]["frameCount"],
            "officialSaveFrameCount": report["window016"]["officialSaveFrameCount"],
            "withheldForNextOverlapFrameCount": report["window016"][
                "withheldForNextOverlapFrameCount"
            ],
        },
        "depth_index_comparison": report["depth_index_comparison"],
        "suspect_frame_roles": report["suspect_frame_roles"],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 save-frame downstream audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- goal complete: `{report['decision']['goal_complete']}`",
        "",
        report["decision"]["conclusion"],
        "",
        report["decision"]["next_best_action"],
        "",
        "## 大白话",
        "",
    ]
    for item in report["plain_language"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Window 016",
            "",
            f"- full CoreML slots: `{report['window016']['frameCount']}`",
            f"- official downstream frames: `{report['window016']['officialSaveFrameCount']}`",
            f"- withheld overlap frames: `{report['window016']['withheldForNextOverlapFrameCount']}`",
            f"- old full-chunk depth_index frames: `{report['depth_index_comparison']['old_full_chunk_frame_count']}`",
            f"- new official-save depth_index frames: `{report['depth_index_comparison']['new_official_save_frame_count']}`",
            "",
            "## Suspect Frame Ownership",
            "",
            "| frame | windows / local slots |",
            "|---|---|",
        ]
    )
    for frame_id, roles in report["suspect_frame_roles"].items():
        summary = "; ".join(
            "{windowID}[slot={localSlot}, downstream={officialDownstream}, withheld={withheldForNextOverlap}, bridge={bridgeFrame}, core={coreFrame}]".format(
                **role
            )
            for role in roles
        )
        lines.append(f"| `{frame_id}` | {summary} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
