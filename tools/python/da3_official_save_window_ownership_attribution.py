#!/usr/bin/env python3
"""Attribute official-save DA3 thickness to window ownership and suspect frames."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
WINDOW_AUDITS = {
    "window_016": "window_016_official_save_frame_pose_depth_scale_2026_06_05/window_016_pose_depth_scale_audit.json",
    "window_017": "window_017_official_save_frame_pose_depth_scale_2026_06_05/window_017_pose_depth_scale_audit.json",
}
SUSPECTS = ["cap-1396", "cap-1514", "cap-1529"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_save_window_ownership_attribution.json", report)
    write_markdown(
        args.out_dir / "official_da3_save_window_ownership_attribution_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    dataset = args.dataset_dir
    diag = dataset / "diagnostics"
    capture = dataset / "capture_seq_k35_strict"
    k_windows = read_json(capture / "da3_k_windows.json")
    photo_bundle = read_json(capture / "photo_bundle.json")
    audits = {
        window_id: read_json(diag / rel_path)
        for window_id, rel_path in WINDOW_AUDITS.items()
    }
    summaries = {window_id: summarize_window_audit(report) for window_id, report in audits.items()}
    suspect_roles = {
        frame_id: {
            "ownership": frame_roles(k_windows, frame_id),
            "metadata": frame_metadata(photo_bundle, frame_id),
            "audit_rows": frame_audit_rows(audits, frame_id),
        }
        for frame_id in SUSPECTS
    }
    window016_thick = summaries["window_016"]["npz_minor_ratio_vs_k10"] >= 1.10
    window017_thick = summaries["window_017"]["npz_minor_ratio_vs_k10"] >= 1.10
    return {
        "schema_version": "aether_official_da3_save_window_ownership_attribution_v1",
        "date": args.date,
        "decision": {
            "status": (
                "window016_official_save_thickness_cap1396_primary"
                if window016_thick and not window017_thick
                else "official_save_ownership_attribution_incomplete"
            ),
            "goal_complete": False,
            "conclusion": (
                "After official save-frame downstream alignment, window_016 still thickens, while window_017 does not. "
                "The strongest current upstream consistency suspect is cap-1396 inside window_016 official downstream."
            ),
            "next_best_action": (
                "Inspect/remediate frame acceptance or capture continuity around cap-1369 -> cap-1396. "
                "Keep cap-1514/cap-1529 as window_017 risk signals, but not the current primary thickness cause."
            ),
        },
        "inputs": {
            "dataset_dir": str(dataset),
            "window_audits": {
                window_id: str(diag / rel_path)
                for window_id, rel_path in WINDOW_AUDITS.items()
            },
        },
        "window_summaries": summaries,
        "suspect_frame_roles": suspect_roles,
        "plain_language": [
            "官方 save-frame ownership 已经把 window_016 和 window_017 的 downstream 责任分开。",
            "window_016 official downstream 17 帧仍厚：npz minor vs k10 约 1.429x，bbox 约 1.397x。",
            "window_017 official downstream 17 帧不厚：npz minor vs k10 约 0.970x，bbox 约 0.948x。",
            "cap-1396 在 window_016 的 official downstream 内，且从前一帧 cap-1369 跳了 4.47s / 0.410m / elevation +0.387rad。",
            "cap-1514 和 cap-1529 在 window_017 里是风险信号，但这次没有把 window_017 的官方 downstream 点云拉厚。",
        ],
    }


def summarize_window_audit(report: dict[str, Any]) -> dict[str, Any]:
    scope = report.get("scope", {})
    npz = get_path(report, "summary.styles.npz_streaming_style.k35_over_k10") or {}
    glb = get_path(report, "summary.styles.glb_style.k35_over_k10") or {}
    pose = report.get("summary", {}).get("pose", {})
    depth = report.get("summary", {}).get("depth", {})
    return {
        "frame_source": scope.get("frame_source"),
        "frame_count": scope.get("frame_count"),
        "pose_scale": scope.get("pose_scale"),
        "npz_bbox_ratio_vs_k10": npz.get("bbox_ratio_vs_k10"),
        "npz_minor_ratio_vs_k10": npz.get("minor_ratio_vs_k10"),
        "glb_bbox_ratio_vs_k10": glb.get("bbox_ratio_vs_k10"),
        "glb_minor_ratio_vs_k10": glb.get("minor_ratio_vs_k10"),
        "pose_diag_ratio_vs_k10": pose.get("k35_over_k10_pose_diag"),
        "largest_pose_step": pose.get("largest_step"),
        "depth_p95_ratio_vs_k10": depth.get("k35_over_k10_p95"),
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


def frame_metadata(photo_bundle: dict[str, Any], frame_id: str) -> dict[str, Any]:
    for frame in photo_bundle.get("frames", []):
        if str(frame.get("id")) != frame_id:
            continue
        quality = frame.get("quality") or {}
        return {
            "timestamp": frame.get("timestamp"),
            "azimuth": frame.get("azimuth"),
            "elevation": frame.get("elevation"),
            "cameraRadiusM": frame.get("cameraRadiusM"),
            "qualityScore": quality.get("score"),
            "kWindowWeight": quality.get("kWindowWeight"),
        }
    return {}


def frame_audit_rows(audits: dict[str, dict[str, Any]], frame_id: str) -> list[dict[str, Any]]:
    rows = []
    for window_id, report in audits.items():
        for row in report.get("per_slot", []):
            if str(row.get("frame_id")) != frame_id:
                continue
            rows.append(
                {
                    "windowID": window_id,
                    "slot": row.get("slot"),
                    "frameIndex": row.get("frame_index"),
                    "stepFromPrevious": row.get("step_from_previous"),
                    "cumulativePoseDiag": row.get("cumulative_pose_diag"),
                    "depthP95": (row.get("depth") or {}).get("p95"),
                    "confidenceMedian": (row.get("confidence") or {}).get("median"),
                }
            )
    return rows


def get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "window_summaries": report["window_summaries"],
        "suspect_frame_roles": report["suspect_frame_roles"],
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 save-window ownership attribution",
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
            "## Window Summary",
            "",
            "| window | frames | npz minor/k10 | npz bbox/k10 | glb minor/k10 | pose diag/k10 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for window_id, row in report["window_summaries"].items():
        lines.append(
            "| {window} | {frames} | {npz_minor:.3f} | {npz_bbox:.3f} | {glb_minor:.3f} | {pose:.3f} |".format(
                window=window_id,
                frames=row.get("frame_count") or 0,
                npz_minor=float(row.get("npz_minor_ratio_vs_k10") or 0.0),
                npz_bbox=float(row.get("npz_bbox_ratio_vs_k10") or 0.0),
                glb_minor=float(row.get("glb_minor_ratio_vs_k10") or 0.0),
                pose=float(row.get("pose_diag_ratio_vs_k10") or 0.0),
            )
        )
    lines.extend(
        [
            "",
            "## Suspects",
            "",
            "| frame | ownership | audit row |",
            "|---|---|---|",
        ]
    )
    for frame_id, info in report["suspect_frame_roles"].items():
        ownership = "; ".join(
            "{windowID}[slot={localSlot}, downstream={officialDownstream}, withheld={withheldForNextOverlap}]".format(
                **role
            )
            for role in info["ownership"]
        )
        audit = "; ".join(
            "{windowID}[slot={slot}, step={stepFromPrevious:.3f}, poseDiag={cumulativePoseDiag:.3f}, depthP95={depthP95:.3f}, confMed={confidenceMedian:.3f}]".format(
                **row
            )
            for row in info["audit_rows"]
        )
        lines.append(f"| `{frame_id}` | {ownership} | {audit} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
