#!/usr/bin/env python3
"""Build a transfer manifest for the target DA3 image-only CoreML export kit."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


DATASET = "official_da3_base_k35_strict_seq_2026_06_02"
TARGET_RESOURCE = "DA3BASE_280x504_N35_image_only"
POSE_RESOURCE = "DA3BASE_476x742_N35_pose"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-repo", type=Path, required=True)
    parser.add_argument("--app-repo", type=Path, required=True)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--capture-services-dir", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_only_coreml_export_kit_manifest.json", report)
    write_markdown(
        args.out_dir / "official_da3_image_only_coreml_export_kit_manifest_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    paths = resolve_paths(args)
    items = build_items(paths)
    commands = build_commands(paths)
    decision = derive_decision(items, paths)
    return {
        "schema_version": "aether_da3_image_only_coreml_export_kit_manifest_v1",
        "date": args.date,
        "purpose": (
            "Prepare the minimum transfer kit for exporting "
            f"{TARGET_RESOURCE}.mlpackage in a larger-memory macOS/CoreML environment."
        ),
        "fixed_target": {
            "resource": TARGET_RESOURCE,
            "pose_compat_resource": POSE_RESOURCE,
            "window_size": 35,
            "height": 280,
            "width": 504,
            "process_res": 504,
            "process_res_method": "upper_bound_resize",
            "patch_size": 14,
            "coreml_inputs": ["image"],
            "forbidden_inputs": ["extrinsics", "intrinsics"],
            "outputs": ["depth", "depth_conf", "pred_extrinsics", "pred_intrinsics"],
        },
        "recommended_environment": {
            "preferred_unified_memory_gib": 64,
            "risky_minimum_unified_memory_gib": 32,
            "current_local_unified_memory_gib": local_memory_gib(),
            "requires_macos_coreml": True,
            "a100_h100_role": "PyTorch reference gate only, not CoreML packaging or mobile runtime",
            "note": (
                "This is a CoreML conversion/export envelope, not the product runtime "
                "memory requirement. Current local 18 GiB Mac has failed/preflighted as risky."
            ),
        },
        "paths": paths_for_json(paths),
        "kit_items": items,
        "commands": commands,
        "decision": decision,
    }


def resolve_paths(args: argparse.Namespace) -> dict[str, Path]:
    research = args.research_repo.resolve()
    app = args.app_repo.resolve()
    official = args.official_da3_repo.resolve()
    capture_services = args.capture_services_dir.resolve()
    capture = args.capture_dir.resolve()
    dataset_root = capture.parent
    diagnostics = dataset_root / "diagnostics"
    return {
        "research_repo": research,
        "app_repo": app,
        "official_da3_repo": official,
        "capture_services_dir": capture_services,
        "capture_dir": capture,
        "dataset_root": dataset_root,
        "diagnostics_dir": diagnostics,
        "research_tools_python": research / "tools/python",
        "da3_base_model_dir": app / "ios/Runner/Models/DA3-BASE",
        "coreml_models_dir": app / "ios/Runner/Models/DA3-BASE-CoreML",
        "target_coreml_model": app
        / f"ios/Runner/Models/DA3-BASE-CoreML/{TARGET_RESOURCE}.mlpackage",
        "pose_coreml_model": app
        / f"ios/Runner/Models/DA3-BASE-CoreML/{POSE_RESOURCE}.mlpackage",
        "swift_plugin": app / "ios/Runner/Da3DepthPlugin.swift",
        "local_runner": app / "lib/pipeline/local_pipeline_runner.dart",
        "capture_policy": capture_services
        / "lib/src/photo_bundle_pipeline_policy_service.dart",
        "target_export_runbook": diagnostics
        / "official_da3_image_only_coreml_target_export_runbook_2026_06_04/official_da3_image_only_coreml_target_export_runbook_zh.md",
        "target_export_gate": diagnostics
        / "official_da3_image_only_coreml_target_export_gate_2026_06_05/official_da3_image_only_coreml_target_export_gate.json",
    }


def build_items(paths: dict[str, Path]) -> list[dict[str, Any]]:
    specs = [
        ("research_tools_python", "all Python export/gate scripts"),
        ("capture_dir", "same capture used for window_016 overlap regression"),
        ("official_da3_repo", "official DA3 source for wrapper import and parity audit"),
        ("da3_base_model_dir", "DA3-BASE checkpoint/config; commercial-safe model"),
        ("coreml_models_dir", "CoreML output directory and current pose compat package"),
        ("swift_plugin", "APP native CoreML adapter evidence"),
        ("local_runner", "APP local pipeline gate evidence"),
        ("capture_services_dir", "capture service package for policy/readiness source"),
        ("capture_policy", "Dart policy source used by readiness gate"),
        ("target_export_runbook", "human runbook for fixed target export"),
        ("target_export_gate", "local resource preflight evidence"),
    ]
    rows = []
    for key, role in specs:
        path = paths[key]
        rows.append(
            {
                "id": key,
                "role": role,
                "path": str(path),
                "exists": path.exists(),
                "is_dir": path.is_dir(),
                "size_bytes": du_bytes(path) if path.exists() else None,
            }
        )
    return rows


def derive_decision(items: list[dict[str, Any]], paths: dict[str, Path]) -> dict[str, Any]:
    missing = [item["id"] for item in items if not item["exists"]]
    target_exists = paths["target_coreml_model"].exists()
    pose_exists = paths["pose_coreml_model"].exists()
    return {
        "status": "ready_to_transfer_export_kit" if not missing else "missing_required_items",
        "missing_required_items": missing,
        "target_image_only_coreml_exists": target_exists,
        "pose_compat_coreml_exists": pose_exists,
        "goal_complete": False,
        "why_not_complete": (
            f"{TARGET_RESOURCE}.mlpackage is still missing; this manifest only prepares transfer/export."
        ),
    }


def build_commands(paths: dict[str, Path]) -> dict[str, Any]:
    dataset_rel = f"data/{DATASET}"
    return {
        "transfer_from_current_mac": [
            "export DA3_EXPORT_KIT_ROOT=/path/to/da3_export_kit",
            "mkdir -p \"$DA3_EXPORT_KIT_ROOT\"",
            f"rsync -a \"{paths['research_tools_python']}/\" \"$DA3_EXPORT_KIT_ROOT/research/tools/python/\"",
            f"rsync -a \"{paths['capture_dir']}/\" \"$DA3_EXPORT_KIT_ROOT/research/{dataset_rel}/capture_seq_k35_strict/\"",
            f"rsync -a \"{paths['diagnostics_dir']}/official_da3_image_only_coreml_target_export_runbook_2026_06_04/\" \"$DA3_EXPORT_KIT_ROOT/research/{dataset_rel}/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04/\"",
            f"rsync -a \"{paths['diagnostics_dir']}/official_da3_image_only_coreml_target_export_gate_2026_06_05/\" \"$DA3_EXPORT_KIT_ROOT/research/{dataset_rel}/diagnostics/official_da3_image_only_coreml_target_export_gate_2026_06_05/\"",
            f"rsync -a \"{paths['official_da3_repo']}/\" \"$DA3_EXPORT_KIT_ROOT/official/Depth-Anything-3/\"",
            f"rsync -a \"{paths['da3_base_model_dir']}/\" \"$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE/\"",
            f"rsync -a \"{paths['coreml_models_dir']}/\" \"$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE-CoreML/\"",
            f"rsync -a \"{paths['swift_plugin']}\" \"$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Da3DepthPlugin.swift\"",
            f"rsync -a \"{paths['local_runner']}\" \"$DA3_EXPORT_KIT_ROOT/app/lib/pipeline/local_pipeline_runner.dart\"",
            f"rsync -a \"{paths['capture_services_dir']}/\" \"$DA3_EXPORT_KIT_ROOT/packages/aether_capture_services/\"",
        ],
        "run_on_large_memory_mac": [
            "export DA3_EXPORT_KIT_ROOT=/path/to/da3_export_kit",
            "cd \"$DA3_EXPORT_KIT_ROOT/research\"",
            "mkdir -p data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04",
            "python3.11 tools/python/export_da3_image_only_coreml.py \\",
            "  --official-da3-repo \"$DA3_EXPORT_KIT_ROOT/official/Depth-Anything-3\" \\",
            "  --model-dir \"$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE\" \\",
            f"  --out-model \"$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE-CoreML/{TARGET_RESOURCE}.mlpackage\" \\",
            "  --window-size 35 \\",
            "  --height 280 \\",
            "  --width 504 \\",
            "  --dry-run \\",
            "  --convert \\",
            "  --compute-precision float16 \\",
            "  --minimum-deployment-target iOS18 \\",
            "  --static-shape-export-patches \\",
            "  --allow-duplicate-openmp \\",
            "  --out-report data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04/target_280x504_image_only_export_report.json",
        ],
        "verify_on_large_memory_mac": [
            "export DA3_EXPORT_KIT_ROOT=/path/to/da3_export_kit",
            "cd \"$DA3_EXPORT_KIT_ROOT/research\"",
            "python3.11 tools/python/da3_image_only_coreml_readiness_gate.py \\",
            "  --app-repo \"$DA3_EXPORT_KIT_ROOT/app\" \\",
            "  --capture-services-dir \"$DA3_EXPORT_KIT_ROOT/packages/aether_capture_services\" \\",
            "  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_05 \\",
            "  --date 2026-06-05",
            "python3.11 tools/python/da3_mac_window_export.py \\",
            "  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \\",
            "  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline \\",
            f"  --model \"$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE-CoreML/{TARGET_RESOURCE}.mlpackage\" \\",
            "  --compute-unit all \\",
            "  --resume",
            "python3.11 tools/python/da3_image_only_overlap_regression_gate.py \\",
            "  --capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict \\",
            "  --pose-da3-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict \\",
            "  --image-only-da3-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_official_baseline \\",
            "  --out-dir data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_overlap_regression_gate_2026_06_05 \\",
            "  --window-id window_016 \\",
            "  --npz-conf-threshold-coef 0.5",
        ],
        "return_artifacts_to_current_mac": [
            "export DA3_EXPORT_KIT_ROOT=/path/to/da3_export_kit",
            f"rsync -a \"$DA3_EXPORT_KIT_ROOT/app/ios/Runner/Models/DA3-BASE-CoreML/{TARGET_RESOURCE}.mlpackage\" \"{paths['coreml_models_dir']}/\"",
            f"rsync -a \"$DA3_EXPORT_KIT_ROOT/research/data/{DATASET}/diagnostics/official_da3_image_only_coreml_target_export_runbook_2026_06_04/target_280x504_image_only_export_report.json\" \"{paths['diagnostics_dir']}/official_da3_image_only_coreml_target_export_runbook_2026_06_04/\"",
            f"rsync -a \"$DA3_EXPORT_KIT_ROOT/research/data/{DATASET}/da3_seq_k35_coreml_image_only_official_baseline/\" \"{paths['dataset_root']}/da3_seq_k35_coreml_image_only_official_baseline/\"",
            f"rsync -a \"$DA3_EXPORT_KIT_ROOT/research/data/{DATASET}/diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_05/\" \"{paths['diagnostics_dir']}/official_da3_image_only_coreml_readiness_gate_2026_06_05/\"",
            f"rsync -a \"$DA3_EXPORT_KIT_ROOT/research/data/{DATASET}/diagnostics/official_da3_image_only_overlap_regression_gate_2026_06_05/\" \"{paths['diagnostics_dir']}/official_da3_image_only_overlap_regression_gate_2026_06_05/\"",
        ],
    }


def paths_for_json(paths: dict[str, Path]) -> dict[str, str]:
    return {key: str(value) for key, value in paths.items()}


def local_memory_gib() -> float | None:
    try:
        raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=5)
        return int(raw.strip()) / float(1024**3)
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def du_bytes(path: Path) -> int | None:
    try:
        raw = subprocess.check_output(["du", "-sk", str(path)], text=True, timeout=30)
        return int(raw.split()[0]) * 1024
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def fmt_size(value: Any) -> str:
    if value is None:
        return "-"
    raw = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(raw) < 1024.0 or unit == "TiB":
            return f"{raw:.2f} {unit}"
        raw /= 1024.0
    return "-"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "recommended_environment": report["recommended_environment"],
        "missing": report["decision"]["missing_required_items"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 image-only CoreML export kit manifest",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- target image-only CoreML exists: `{report['decision']['target_image_only_coreml_exists']}`",
        f"- pose compat CoreML exists: `{report['decision']['pose_compat_coreml_exists']}`",
        f"- missing required items: `{', '.join(report['decision']['missing_required_items'])}`",
        "",
        "这份清单用于把固定目标导出任务迁移到大内存 Mac/CoreML 环境。它不改变 K/尺寸，也不允许用 `_pose` 或小尺寸 probe 替代目标。",
        "",
        "## 推荐环境",
        "",
        f"- preferred unified memory: `{report['recommended_environment']['preferred_unified_memory_gib']} GiB`",
        f"- risky minimum unified memory: `{report['recommended_environment']['risky_minimum_unified_memory_gib']} GiB`",
        f"- current local unified memory: `{report['recommended_environment']['current_local_unified_memory_gib']} GiB`",
        f"- A100/H100 role: {report['recommended_environment']['a100_h100_role']}",
        f"- note: {report['recommended_environment']['note']}",
        "",
        "## Kit items",
        "",
        "| id | exists | size | role |",
        "|---|---:|---:|---|",
    ]
    for item in report["kit_items"]:
        lines.append(
            f"| `{item['id']}` | `{item['exists']}` | `{fmt_size(item['size_bytes'])}` | {item['role']} |"
        )

    for section, commands in report["commands"].items():
        lines.extend(["", f"## {section}", "", "```bash"])
        lines.extend(commands)
        lines.append("```")

    lines.extend(
        [
            "",
            "## 完成定义",
            "",
            f"- `{TARGET_RESOURCE}.mlpackage` exists.",
            "- readiness gate passes with required inputs exactly `image`.",
            "- Mac exporter writes same-capture image-only output.",
            "- overlap regression gate gives a pass/fail judgement for `window_016`.",
            "- closure matrix no longer reports `target_missing=true`; remaining status comes from the real same-capture overlap/geometry result.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
