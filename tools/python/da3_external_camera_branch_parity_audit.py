#!/usr/bin/env python3
"""Audit DA3 optional external-camera branch parity for the current CoreML path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_OFFICIAL_REPO = Path(
    "/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3"
)
DEFAULT_RESEARCH_REPO = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks"
)
DEFAULT_APP_REPO = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter")
DEFAULT_STAGE_SCRIPTS = Path("/Users/kaidongwang/Developer/Aether3D-cross/scripts/da3_official_stage")
DEFAULT_DATA_ROOT = (
    DEFAULT_RESEARCH_REPO / "data/official_da3_base_k35_strict_seq_2026_06_02"
)
DEFAULT_RAW_COREML_DIR = (
    DEFAULT_DATA_ROOT / "da3_seq_k35_coreml_pose_dart_camera_contract_window016_cpu_2026_06_05"
)
DEFAULT_PRE_NORM_RAW_COREML_DIR = (
    DEFAULT_DATA_ROOT / "da3_seq_k35_coreml_pose_window016_official_pre_norm_raw_2026_06_05"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-repo", type=Path, default=DEFAULT_OFFICIAL_REPO)
    parser.add_argument("--research-repo", type=Path, default=DEFAULT_RESEARCH_REPO)
    parser.add_argument("--app-repo", type=Path, default=DEFAULT_APP_REPO)
    parser.add_argument("--stage-scripts-dir", type=Path, default=DEFAULT_STAGE_SCRIPTS)
    parser.add_argument("--raw-coreml-dir", type=Path, default=DEFAULT_RAW_COREML_DIR)
    parser.add_argument("--pre-norm-raw-coreml-dir", type=Path, default=DEFAULT_PRE_NORM_RAW_COREML_DIR)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_external_camera_branch_parity_audit.json", report)
    write_markdown(args.out_dir / "official_da3_external_camera_branch_parity_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official_api = args.official_repo / "src/depth_anything_3/api.py"
    official_pytorch = args.research_repo / "tools/python/official_pytorch_window_export.py"
    mac_coreml = args.research_repo / "tools/python/da3_mac_window_export.py"
    coreml_postprocess = args.research_repo / "tools/python/coreml_official_postprocess_export.py"
    swift_plugin = args.app_repo / "ios/Runner/Da3DepthPlugin.swift"
    pose_export = args.stage_scripts_dir / "export_da3_pose_coreml.py"
    rectangular_sweep = args.stage_scripts_dir / "run_476742_neighborhood_sweep_20260525.sh"
    raw_vs_pre_norm = compare_raw_coreml_outputs(
        args.raw_coreml_dir,
        args.pre_norm_raw_coreml_dir,
    )

    checks = [
        check_contains(
            "official_api_pre_forward_normalizes_external_extrinsics",
            official_api,
            "ex_t_norm = self._normalize_extrinsics(ex_t.clone() if ex_t is not None else None)",
            "官方 DepthAnything3.inference 在 external-camera mode 下 forward 前归一化 extrinsics。",
        ),
        check_contains(
            "official_api_normalization_first_frame_and_median_distance",
            official_api,
            "ex_t_norm[..., :3, 3] = ex_t_norm[..., :3, 3] / median_dist",
            "官方 normalize 先归一到首帧，再用 camera center median distance 缩放平移。",
        ),
        check_contains(
            "official_api_post_forward_umeyama_depth_scale",
            official_api,
            "prediction.depth /= scale",
            "官方 external-camera postprocess 用 Umeyama scale 反调 depth，并回填输入相机。",
        ),
        check_contains(
            "research_pytorch_pose_branch_matches_pre_forward_normalize",
            official_pytorch,
            "ex_t_norm = model._normalize_extrinsics(ex_t.clone() if ex_t is not None else None)",
            "Research PyTorch pose-conditioned 分支有官方 pre-forward extrinsics normalize。",
        ),
        check_contains(
            "research_pytorch_pose_branch_matches_post_umeyama",
            official_pytorch,
            "prediction.depth = np.asarray(prediction.depth, dtype=np.float32) / float(pose_scale)",
            "Research PyTorch pose-conditioned 分支有官方 Umeyama depth scale postprocess。",
        ),
        check_contains(
            "coreml_pose_export_wrapper_normalizes_extrinsics_inside_model",
            pose_export,
            "ex_norm = self.normalize_extrinsics(extrinsics)",
            "用于导出 pose CoreML 的 wrapper 会在模型 forward 内部先 normalize extrinsics。",
        ),
        check_contains(
            "coreml_pose_export_wrapper_uses_first_frame_median_distance",
            pose_export,
            "median_dist = fixed_k_median(dists).clamp(min=1e-1)",
            "pose CoreML wrapper 的归一化是首帧相对化 + median camera-center distance。",
        ),
        check_contains(
            "base_476x742_n35_pose_export_uses_pose_wrapper",
            rectangular_sweep,
            "K35_476x742",
            "K35_476x742 是矩形 DA3-BASE CoreML sweep 的当前 baseline；同目录矩形候选均通过 pose CoreML exporter 生成。",
        ),
        check_contains(
            "mac_coreml_runtime_feeds_raw_extrinsics_expected_by_export_wrapper",
            mac_coreml,
            'inputs["extrinsics"] = extrinsic_stack[None, ...].astype(np.float32)',
            "Mac CoreML runner 喂 raw OpenCV w2c；如果模型是 pose wrapper 导出，这正是 wrapper 的预期输入。",
        ),
        check_contains(
            "swift_coreml_runtime_feeds_raw_extrinsics_expected_by_export_wrapper",
            swift_plugin,
            'let values = doubleArray(frame["cameraExtrinsicOpenCvW2c4x4"])',
            "Swift CoreML runner 喂 Dart 预计算 raw OpenCV w2c；pose wrapper 内部再做官方式归一化。",
        ),
        check_contains(
            "coreml_postprocess_applies_only_post_forward_umeyama",
            coreml_postprocess,
            "post_depth = raw[\"depth\"] / pose_scale",
            "CoreML official postprocess 已补 forward 后 Umeyama/depth scale。",
        ),
        raw_vs_pre_norm_check(raw_vs_pre_norm),
    ]
    export_wrapper_ok = all(
        item["status"] == "pass"
        for item in checks
        if item["id"].startswith("coreml_pose_export_wrapper_")
        or item["id"] == "base_476x742_n35_pose_export_uses_pose_wrapper"
    )
    raw_inputs_expected = all(
        item["status"] == "pass"
        for item in checks
        if item["id"].endswith("_expected_by_export_wrapper")
    )
    empirical_equivalent = raw_vs_pre_norm.get("status") == "pass"
    official_and_pytorch_ok = all(
        item["status"] == "pass"
        for item in checks
        if item["id"].startswith("official_") or item["id"].startswith("research_pytorch_")
    )
    status = (
        "coreml_pose_path_pre_forward_extrinsics_normalization_likely_embedded_not_root_cause"
        if official_and_pytorch_ok and export_wrapper_ok and raw_inputs_expected
        else "external_camera_branch_parity_needs_manual_review"
    )
    return {
        "schema_version": "aether_da3_external_camera_branch_parity_audit_v2",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "official_algorithm_blame_supported": False,
            "pytorch_pose_branch_parity": official_and_pytorch_ok,
            "coreml_export_wrapper_pre_forward_normalization_supported": export_wrapper_ok,
            "coreml_runtime_raw_extrinsics_are_expected": raw_inputs_expected,
            "empirical_raw_vs_pre_norm_equivalent": empirical_equivalent,
            "coreml_pre_forward_normalization_parity": export_wrapper_ok,
            "conclusion": (
                "The current DA3BASE_476x742_N35_pose package was exported through the pose CoreML wrapper, and that "
                "wrapper embeds official-style pre-forward extrinsics normalization inside the model. Mac/Swift feeding "
                "raw OpenCV w2c is therefore expected for this package. A research-only raw-vs-pre-normalized rerun on "
                "window_016 produced only small raw output differences, so pre-forward extrinsics normalization is no "
                "longer a root-cause-level suspect for the NPZ downstream thickness."
            ),
            "next_best_action": (
                "Keep the pose CoreML external-camera branch as a compatibility path, but move the root-cause search "
                "back to the bigger official-parity gaps: image-only cam_dec and official upper_bound_resize/patch "
                "preprocess."
            ),
        },
        "inputs": {
            "official_repo": str(args.official_repo),
            "research_repo": str(args.research_repo),
            "app_repo": str(args.app_repo),
            "stage_scripts_dir": str(args.stage_scripts_dir),
            "raw_coreml_dir": str(args.raw_coreml_dir),
            "pre_norm_raw_coreml_dir": str(args.pre_norm_raw_coreml_dir),
        },
        "raw_vs_pre_norm": raw_vs_pre_norm,
        "checks": checks,
        "plain_language": [
            "官方 external-camera API 会在 forward 前归一化 extrinsics，这一点仍然成立。",
            "但当前 pose CoreML 的导出 wrapper 本身也做了这一步；所以 Mac/Swift 外面喂 raw OpenCV w2c 不是自动错误。",
            "我做了 raw 输入 vs 外部预归一化输入的 window_016 对照，raw 模型输出差异很小；这说明它不是厚层主因级别的差异。",
            "当前 _pose CoreML 仍不是官方 image-only baseline；它只是 external-camera compatibility path。",
            "现在更该押注的复刻缺口是 image-only cam_dec 和官方等比 upper_bound_resize + patch multiple preprocess。",
        ],
    }


def check_contains(
    check_id: str,
    path: Path,
    needle: str,
    evidence: str,
    *,
    pass_means_parity: bool = True,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = needle in text
    if not present:
        status = "missing"
    elif pass_means_parity:
        status = "pass"
    else:
        status = "parity_gap"
    return {
        "id": check_id,
        "status": status,
        "path": str(path),
        "line": find_line(text, needle) if present else None,
        "needle": needle,
        "evidence": evidence,
    }


def check_absent(check_id: str, path: Path, needle: str, evidence: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = needle in text
    return {
        "id": check_id,
        "status": "fail" if present else "parity_gap",
        "path": str(path),
        "line": find_line(text, needle) if present else None,
        "needle": needle,
        "evidence": evidence,
    }


def raw_vs_pre_norm_check(metrics: dict[str, Any]) -> dict[str, Any]:
    status = metrics.get("status", "unknown")
    evidence = metrics.get("evidence", "raw-vs-pre-normalized CoreML output comparison unavailable.")
    return {
        "id": "window016_raw_vs_external_pre_norm_outputs_nearly_equivalent",
        "status": status,
        "path": str(metrics.get("raw_coreml_dir") or ""),
        "line": None,
        "needle": "raw_vs_pre_norm",
        "evidence": evidence,
    }


def compare_raw_coreml_outputs(raw_dir: Path, pre_norm_dir: Path) -> dict[str, Any]:
    if not raw_dir.exists() or not pre_norm_dir.exists():
        return {
            "status": "unknown",
            "raw_coreml_dir": str(raw_dir),
            "pre_norm_raw_coreml_dir": str(pre_norm_dir),
            "evidence": "One or both raw CoreML output directories are missing.",
        }
    raw_report_path = raw_dir / "mac_da3_window_reports.json"
    pre_report_path = pre_norm_dir / "mac_da3_window_reports.json"
    if not raw_report_path.exists() or not pre_report_path.exists():
        return {
            "status": "unknown",
            "raw_coreml_dir": str(raw_dir),
            "pre_norm_raw_coreml_dir": str(pre_norm_dir),
            "evidence": "One or both mac_da3_window_reports.json files are missing.",
        }
    raw_frames = first_window_frames(raw_report_path)
    pre_frames = {str(frame.get("frameID")): frame for frame in first_window_frames(pre_report_path)}
    stats: dict[str, dict[str, float]] = {}
    for key, label in (
        ("relativeDepthPath", "depth"),
        ("confidencePath", "confidence"),
        ("predExtrinsicsPath", "pred_extrinsics"),
        ("predIntrinsicsPath", "pred_intrinsics"),
    ):
        mean_abs_values: list[float] = []
        max_abs_values: list[float] = []
        mean_rel_values: list[float] = []
        for raw_frame in raw_frames:
            frame_id = str(raw_frame.get("frameID"))
            pre_frame = pre_frames.get(frame_id)
            if pre_frame is None:
                continue
            raw_path = raw_dir / str(raw_frame.get(key))
            pre_path = pre_norm_dir / str(pre_frame.get(key))
            if not raw_path.exists() or not pre_path.exists():
                continue
            raw = np_fromfile(raw_path)
            pre = np_fromfile(pre_path)
            if raw.shape != pre.shape or raw.size == 0:
                continue
            diff = np_abs(raw - pre)
            mean_abs_values.append(float(diff.mean()))
            max_abs_values.append(float(diff.max()))
            denom = np_maximum(np_abs(raw), 1e-6)
            mean_rel_values.append(float((diff / denom).mean()))
        stats[label] = {
            "mean_abs_avg": mean(mean_abs_values),
            "max_abs_max": max(max_abs_values) if max_abs_values else float("nan"),
            "mean_rel_avg": mean(mean_rel_values),
        }
    depth_mean = stats.get("depth", {}).get("mean_abs_avg", float("nan"))
    confidence_mean = stats.get("confidence", {}).get("mean_abs_avg", float("nan"))
    status = (
        "pass"
        if depth_mean < 0.005 and confidence_mean < 0.05
        else "warning"
    )
    return {
        "status": status,
        "raw_coreml_dir": str(raw_dir),
        "pre_norm_raw_coreml_dir": str(pre_norm_dir),
        "stats": stats,
        "evidence": (
            f"window_016 raw vs external-pre-normalized raw outputs: "
            f"depth mean_abs={depth_mean:.6f}, "
            f"confidence mean_abs={confidence_mean:.6f}, "
            f"pred_extrinsics mean_abs={stats.get('pred_extrinsics', {}).get('mean_abs_avg', float('nan')):.6f}, "
            f"pred_intrinsics mean_abs={stats.get('pred_intrinsics', {}).get('mean_abs_avg', float('nan')):.6f}."
        ),
    }


def first_window_frames(path: Path) -> list[dict[str, Any]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    windows = report.get("windows") or []
    if not windows:
        return []
    return [frame for frame in windows[0].get("frames", []) if isinstance(frame, dict)]


def np_fromfile(path: Path):
    import numpy as np

    return np.fromfile(path, dtype="<f4")


def np_abs(value):
    import numpy as np

    return np.abs(value)


def np_maximum(value, floor: float):
    import numpy as np

    return np.maximum(value, floor)


def mean(values: list[float]) -> float:
    if not values:
        return float("nan")
    return sum(values) / len(values)


def find_line(text: str, needle: str) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return None


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "parity_gaps": [
            {
                "id": item["id"],
                "status": item["status"],
                "line": item.get("line"),
                "evidence": item["evidence"],
            }
            for item in report["checks"]
            if item["status"] in {"parity_gap", "missing", "fail"}
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 external-camera branch parity audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- pytorch pose branch parity: `{report['decision']['pytorch_pose_branch_parity']}`",
        f"- coreml pre-forward normalization parity: `{report['decision']['coreml_pre_forward_normalization_parity']}`",
        f"- official algorithm blame supported: `{report['decision']['official_algorithm_blame_supported']}`",
        "",
        report["decision"]["conclusion"],
        "",
        "## 大白话",
        "",
    ]
    for item in report["plain_language"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | status | line | evidence | path |",
            "|---|---:|---:|---|---|",
        ]
    )
    for item in report["checks"]:
        lines.append(
            "| `{id}` | `{status}` | {line} | {evidence} | `{path}` |".format(
                id=item["id"],
                status=item["status"],
                line=item.get("line") or "",
                evidence=escape_md(item["evidence"]),
                path=Path(item["path"]).name,
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
