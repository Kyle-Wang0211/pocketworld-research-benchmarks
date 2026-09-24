#!/usr/bin/env python3
"""Preflight the official-preprocess DA3 image-only CoreML export.

This gate does not run CoreML conversion. It reads existing static export probes
and estimates the target K35@280x504 global-attention resource floor so the
official image-only path can be advanced without accidentally turning the task
back into a dimension sweep.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any


TARGET_RESOURCE = "DA3BASE_280x504_N35_image_only"
POSE_RESOURCE = "DA3BASE_476x742_N35_pose"
PATCH_SIZE = 14
DTYPE_BYTES = {"float16": 2, "float32": 4}
VIT_HEADS = {"vits": 6, "vitb": 12, "vitl": 16, "vitg": 24, "vitg2": 24}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-repo", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--probe-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-size", type=int, default=35)
    parser.add_argument("--height", type=int, default=280)
    parser.add_argument("--width", type=int, default=504)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_only_coreml_target_export_gate.json", report)
    write_markdown(args.out_dir / "official_da3_image_only_coreml_target_export_gate_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    model = inspect_model(args.model_dir)
    artifacts = inspect_app_artifacts(args.app_repo)
    probes = inspect_probes(args.probe_dir)
    probe_guard = inspect_probe_substitution_guard(args.probe_dir, probes)
    direct_attempts = inspect_direct_attempts(args.out_dir, artifacts)
    target = shape_resource(
        height=args.height,
        width=args.width,
        window_size=args.window_size,
        patch_size=PATCH_SIZE,
        num_heads=model["num_heads"],
    )
    system = inspect_system()
    estimates = estimate_target_from_probes(target, probes)
    decision = derive_decision(
        artifacts,
        probes,
        target,
        estimates,
        system,
        probe_guard,
    )
    return {
        "schema_version": "aether_da3_image_only_coreml_target_export_gate_v1",
        "date": args.date,
        "purpose": (
            "Preflight the DA3BASE_280x504_N35 image-only CoreML export "
            "without running another conversion or changing K."
        ),
        "fixed_target": {
            "resource": TARGET_RESOURCE,
            "pose_compat_resource": POSE_RESOURCE,
            "window_size": args.window_size,
            "height": args.height,
            "width": args.width,
            "patch_size": PATCH_SIZE,
            "dimension_sweep": "disabled; dimensions come from official process_res=504 upper_bound_resize + patch align for 16:9 inputs",
            "official_semantics": "image_only_no_extrinsics_no_intrinsics",
        },
        "model": model,
        "system": system,
        "app_artifacts": artifacts,
        "direct_export_attempts": direct_attempts,
        "target_resource_floor": target,
        "existing_static_export_probes": probes,
        "probe_substitution_guard": probe_guard,
        "target_estimates": estimates,
        "decision": decision,
        "next_actions": next_actions(decision),
    }


def inspect_model(model_dir: Path) -> dict[str, Any]:
    config_path = model_dir / "config.json"
    config = maybe_read_json(config_path)
    net = config.get("config", {}).get("net", {})
    name = str(net.get("name") or "vitb")
    return {
        "model_dir": str(model_dir),
        "config_exists": config_path.exists(),
        "model_name": config.get("model_name"),
        "backbone_name": name,
        "patch_size": PATCH_SIZE,
        "num_heads": VIT_HEADS.get(name, 12),
        "num_heads_source": "official vit preset mapping",
        "has_cam_dec": bool(config.get("config", {}).get("cam_dec")),
        "has_cam_enc": bool(config.get("config", {}).get("cam_enc")),
    }


def inspect_app_artifacts(app_repo: Path) -> dict[str, Any]:
    coreml_dir = app_repo / "ios/Runner/Models/DA3-BASE-CoreML"
    target_pkg = coreml_dir / f"{TARGET_RESOURCE}.mlpackage"
    target_compiled = coreml_dir / f"{TARGET_RESOURCE}.mlmodelc"
    pose_pkg = coreml_dir / f"{POSE_RESOURCE}.mlpackage"
    return {
        "coreml_dir": str(coreml_dir),
        "target_mlpackage": str(target_pkg),
        "target_mlpackage_exists": target_pkg.exists(),
        "target_mlmodelc": str(target_compiled),
        "target_mlmodelc_exists": target_compiled.exists(),
        "pose_compat_mlpackage_exists": pose_pkg.exists(),
    }


def inspect_probe_substitution_guard(
    probe_dir: Path,
    probes: dict[str, Any],
) -> dict[str, Any]:
    packages = sorted(probe_dir.rglob("*.mlpackage")) + sorted(
        probe_dir.rglob("*.mlmodelc")
    )
    rows = [
        {
            "path": str(path),
            "resource_name": path.stem,
            "is_exact_product_target": path.stem == TARGET_RESOURCE,
            "classification": (
                "exact_product_target_outside_app_model_dir"
                if path.stem == TARGET_RESOURCE
                else "research_static_export_probe_not_product_target"
            ),
        }
        for path in packages
    ]
    exact_targets = [row for row in rows if row["is_exact_product_target"]]
    pass_probe_count = len(
        [
            row
            for row in probes.get("rows", [])
            if isinstance(row, dict) and row.get("conversion_status") == "pass"
        ]
    )
    return {
        "status": (
            "warning_exact_target_package_outside_app_model_dir"
            if exact_targets
            else "pass_static_probes_are_research_only_not_product_target"
        ),
        "probe_dir": str(probe_dir),
        "package_count": len(rows),
        "passed_static_conversion_probe_count": pass_probe_count,
        "exact_target_package_count": len(exact_targets),
        "exact_target_packages": exact_targets,
        "do_not_accept_probe_as_product_target": True,
        "required_product_location":
            "ios/Runner/Models/DA3-BASE-CoreML/"
            f"{TARGET_RESOURCE}.mlpackage_or_mlmodelc",
        "rows": rows,
    }


def inspect_probes(probe_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(probe_dir.rglob("official_da3_image_only_coreml_static_k35_*_convert_probe*.json")):
        data = maybe_read_json(path)
        inputs = data.get("inputs", {})
        conversion = data.get("conversion", {})
        height = as_int(inputs.get("height"))
        width = as_int(inputs.get("width"))
        window_size = as_int(inputs.get("window_size"))
        out_model = Path(str(inputs.get("out_model") or ""))
        row = {
            "report": str(path),
            "height": height,
            "width": width,
            "window_size": window_size,
            "precision": inputs.get("compute_precision"),
            "conversion_status": conversion.get("status"),
            "conversion_elapsed_s": conversion.get("elapsed_s") or conversion.get("time_l_real_s"),
            "conversion_peak_memory_footprint_bytes": conversion.get("time_l_peak_memory_footprint_bytes"),
            "conversion_max_rss_bytes": conversion.get("time_l_maximum_resident_set_size_bytes"),
            "package_path": str(out_model) if str(out_model) else None,
            "package_exists": out_model.exists() if str(out_model) else False,
            "package_size_bytes": directory_size(out_model) if out_model.exists() else None,
            "dry_run": data.get("dry_run"),
        }
        if height and width and window_size:
            row["shape_resource"] = shape_resource(
                height=height,
                width=width,
                window_size=window_size,
                patch_size=PATCH_SIZE,
                num_heads=12,
            )
        rows.append(row)

    passed = [row for row in rows if row.get("conversion_status") == "pass"]
    failed = [row for row in rows if row.get("conversion_status") == "fail"]
    highest_pass = max(passed, key=lambda row: int(row.get("height") or 0) * int(row.get("width") or 0), default=None)
    highest_failed = max(failed, key=lambda row: int(row.get("height") or 0) * int(row.get("width") or 0), default=None)
    return {
        "probe_dir": str(probe_dir),
        "probe_count": len(rows),
        "rows": rows,
        "highest_conversion_pass": slim_probe(highest_pass),
        "highest_conversion_fail": slim_probe(highest_failed),
    }


def inspect_direct_attempts(out_dir: Path, artifacts: dict[str, Any]) -> dict[str, Any]:
    dry_run_path = out_dir / "official_da3_image_only_k35_280x504_dry_run_report.json"
    convert_path = out_dir / "official_da3_image_only_k35_280x504_convert_report.json"
    dry_run = maybe_read_json(dry_run_path)
    convert = maybe_read_json(convert_path)
    target_exists = bool(
        artifacts.get("target_mlpackage_exists")
        or artifacts.get("target_mlmodelc_exists")
    )
    dry_status = get_path(dry_run, "dry_run.status")
    convert_status = get_path(convert, "conversion.status")
    status = "not_attempted"
    if dry_run_path.exists() and dry_status == "pass" and target_exists:
        status = "target_package_exists_after_dry_run"
    elif dry_run_path.exists() and dry_status == "pass" and convert_path.exists():
        status = f"convert_report_{convert_status or 'unknown'}"
    elif dry_run_path.exists() and dry_status == "pass" and not target_exists:
        status = "dry_run_passed_conversion_not_completed_no_package"
    return {
        "dry_run_report": str(dry_run_path),
        "dry_run_report_exists": dry_run_path.exists(),
        "dry_run_status": dry_status,
        "dry_run_output_shapes": get_path(dry_run, "dry_run.output_shapes"),
        "convert_report": str(convert_path),
        "convert_report_exists": convert_path.exists(),
        "convert_status": convert_status,
        "target_package_exists": target_exists,
        "status": status,
        "interpretation": (
            "PyTorch image-only wrapper is valid at 1x35x3x280x504, but CoreML conversion has not produced the target package."
            if status == "dry_run_passed_conversion_not_completed_no_package"
            else None
        ),
    }


def shape_resource(
    *,
    height: int,
    width: int,
    window_size: int,
    patch_size: int,
    num_heads: int,
) -> dict[str, Any]:
    patch_h = height // patch_size
    patch_w = width // patch_size
    token_count_per_view = 1 + patch_h * patch_w
    global_tokens = window_size * token_count_per_view
    attention_score_elements_no_heads = global_tokens * global_tokens
    attention_score_elements_with_heads = attention_score_elements_no_heads * num_heads
    return {
        "height": height,
        "width": width,
        "window_size": window_size,
        "patch_grid": [patch_h, patch_w],
        "token_count_per_view_with_cls": token_count_per_view,
        "global_tokens": global_tokens,
        "num_heads": num_heads,
        "attention_score_elements_no_heads": attention_score_elements_no_heads,
        "attention_score_elements_with_heads": attention_score_elements_with_heads,
        "attention_score_buffer_gib": {
            dtype: bytes_to_gib(attention_score_elements_with_heads * size)
            for dtype, size in DTYPE_BYTES.items()
        },
    }


def estimate_target_from_probes(target: dict[str, Any], probes: dict[str, Any]) -> dict[str, Any]:
    highest_pass = probes.get("highest_conversion_pass") or {}
    highest_fail = probes.get("highest_conversion_fail") or {}
    target_elems = as_float(target.get("attention_score_elements_with_heads"))
    estimates: dict[str, Any] = {}
    for label, row in (("from_highest_pass", highest_pass), ("from_highest_fail", highest_fail)):
        resource = row.get("shape_resource") or {}
        ref_elems = as_float(resource.get("attention_score_elements_with_heads"))
        ratio = safe_div(target_elems, ref_elems)
        estimate: dict[str, Any] = {"attention_elements_ratio": ratio}
        peak = as_float(row.get("conversion_peak_memory_footprint_bytes"))
        if peak is not None and ratio is not None:
            estimate["rough_conversion_peak_memory_footprint_bytes"] = peak * ratio
            estimate["rough_conversion_peak_memory_footprint_gib"] = bytes_to_gib(peak * ratio)
        package_size = as_float(row.get("package_size_bytes"))
        if package_size is not None and ratio is not None:
            estimate["rough_package_size_bytes"] = package_size * math.sqrt(ratio)
            estimate["rough_package_size_gib"] = bytes_to_gib(package_size * math.sqrt(ratio))
        estimates[label] = estimate
    return estimates


def inspect_system() -> dict[str, Any]:
    mem = sysctl_int("hw.memsize")
    return {
        "hw_model": sysctl_str("hw.model"),
        "physical_cpu": sysctl_int("hw.physicalcpu"),
        "logical_cpu": sysctl_int("hw.logicalcpu"),
        "physical_memory_bytes": mem,
        "physical_memory_gib": None if mem is None else bytes_to_gib(mem),
    }


def derive_decision(
    artifacts: dict[str, Any],
    probes: dict[str, Any],
    target: dict[str, Any],
    estimates: dict[str, Any],
    system: dict[str, Any],
    probe_guard: dict[str, Any],
) -> dict[str, Any]:
    if artifacts["target_mlpackage_exists"] or artifacts["target_mlmodelc_exists"]:
        return {
            "status": "pass_target_image_only_coreml_artifact_exists",
            "can_run_image_only_overlap_gate": True,
            "highest_priority_gap": None,
            "probe_substitution_guard_status": probe_guard.get("status"),
        }

    target_fp16_gib = target["attention_score_buffer_gib"]["float16"]
    system_gib = as_float(system.get("physical_memory_gib"))
    highest_fail = probes.get("highest_conversion_fail") or {}
    fail_peak_gib = bytes_to_gib(as_float(highest_fail.get("conversion_peak_memory_footprint_bytes")))
    rough_from_fail = estimates.get("from_highest_fail", {}).get(
        "rough_conversion_peak_memory_footprint_gib"
    )
    local_memory_insufficient = (
        system_gib is not None
        and target_fp16_gib is not None
        and target_fp16_gib > system_gib
    )
    has_failed_above_pass = bool(highest_fail)
    return {
        "status": "fail_local_target_conversion_preflight",
        "can_run_image_only_overlap_gate": False,
        "highest_priority_gap": f"{TARGET_RESOURCE}.mlpackage_or_mlmodelc_missing",
        "target_coreml_semantics_known": True,
        "highest_full_conversion_pass": probes.get("highest_conversion_pass"),
        "highest_conversion_failure": highest_fail,
        "local_memory_insufficient_for_attention_floor": local_memory_insufficient,
        "target_fp16_attention_score_buffer_gib": target_fp16_gib,
        "local_physical_memory_gib": system_gib,
        "highest_failed_conversion_peak_gib": fail_peak_gib,
        "rough_target_conversion_peak_from_failed_probe_gib": rough_from_fail,
        "do_not_change_dimension": True,
        "do_not_use_pose_or_arkit_fallback": True,
        "probe_substitution_guard_status": probe_guard.get("status"),
        "do_not_accept_static_probe_as_product_target": True,
        "interpretation": (
            "image-only wrapper 的官方语义已经明确，中等 K35 CoreML 导出也已经通过；"
            "但固定目标模型包仍缺失。在没有更大内存导出环境或 memory-efficient "
            "attention/conversion 路径之前，本机继续硬转目标包需要先看 280x504 preflight。"
        ),
    }


def next_actions(decision: dict[str, Any]) -> list[str]:
    if decision["status"] == "pass_target_image_only_coreml_artifact_exists":
        return [
            "运行 da3_image_only_coreml_readiness_gate.py。",
            "用同一 capture/window 运行 da3_mac_window_export.py。",
            "对 window_016 运行 da3_image_only_overlap_regression_gate.py。",
        ]
    return [
        "生成或取得 DA3BASE_280x504_N35_image_only 包；这是官方 process_res=504 输入，不是旧 476x742 固定尺寸。",
        "A100/H100 只用于单独关闭官方 PyTorch full-resolution reference gate；CoreML 打包仍需要 CoreML 可用的导出/编译环境。",
        "不要用更小 probe 包替代目标，也不要为了 official baseline 回退到 _pose/ARKit。",
    ]


def slim_probe(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        key: row.get(key)
        for key in (
            "report",
            "height",
            "width",
            "window_size",
            "precision",
            "conversion_status",
            "conversion_elapsed_s",
            "conversion_peak_memory_footprint_bytes",
            "conversion_max_rss_bytes",
            "package_path",
            "package_exists",
            "package_size_bytes",
            "shape_resource",
        )
    }


def maybe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def directory_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def sysctl_str(name: str) -> str | None:
    try:
        return subprocess.check_output(["sysctl", "-n", name], text=True, timeout=5).strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def sysctl_int(name: str) -> int | None:
    raw = sysctl_str(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def as_int(value: Any) -> int | None:
    raw = as_float(value)
    return None if raw is None else int(raw)


def safe_div(num: Any, den: Any) -> float | None:
    n = as_float(num)
    d = as_float(den)
    if n is None or d is None or abs(d) <= 1e-12:
        return None
    return n / d


def bytes_to_gib(value: Any) -> float | None:
    raw = as_float(value)
    if raw is None:
        return None
    return raw / float(1024**3)


def fmt(value: Any) -> str:
    raw = as_float(value)
    if raw is None:
        return "-"
    if abs(raw) >= 100:
        return f"{raw:.2f}"
    return f"{raw:.4g}"


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "probe_substitution_guard": {
            key: report["probe_substitution_guard"].get(key)
            for key in (
                "status",
                "package_count",
                "exact_target_package_count",
                "do_not_accept_probe_as_product_target",
            )
        },
        "direct_export_attempts": report.get("direct_export_attempts"),
        "target_resource_floor": report["target_resource_floor"],
        "system": report["system"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    target = report["target_resource_floor"]
    probes = report["existing_static_export_probes"]
    probe_guard = report["probe_substitution_guard"]
    attempts = report.get("direct_export_attempts", {})
    system = report["system"]
    estimates = report["target_estimates"]
    highest_pass = probes.get("highest_conversion_pass") or {}
    highest_fail = probes.get("highest_conversion_fail") or {}
    lines = [
        "# Official DA3 image-only CoreML target export gate",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{decision['status']}`",
        f"- highest priority gap: `{decision.get('highest_priority_gap')}`",
        f"- can run image-only overlap gate: `{decision['can_run_image_only_overlap_gate']}`",
        f"- local memory insufficient for attention floor: `{decision.get('local_memory_insufficient_for_attention_floor')}`",
        f"- probe substitution guard: `{probe_guard.get('status')}`",
        "",
        "这个 gate 不跑新的转换，也不改 K。它只回答：当前本机是否适合继续导出官方 preprocess 目标 `DA3BASE_280x504_N35_image_only`。",
        "",
        "## 固定目标",
        "",
        f"- target: `{report['fixed_target']['resource']}`",
        f"- window: `K{report['fixed_target']['window_size']}`",
        f"- input: `{report['fixed_target']['height']}x{report['fixed_target']['width']}`",
        f"- semantics: `{report['fixed_target']['official_semantics']}`",
        f"- dimension sweep: `{report['fixed_target']['dimension_sweep']}`",
        "",
        "## 资源下限",
        "",
        f"- patch grid: `{target['patch_grid'][0]}x{target['patch_grid'][1]}`",
        f"- global tokens: `{target['global_tokens']}`",
        f"- attention heads: `{target['num_heads']}`",
        f"- fp16 attention score buffer: `{fmt(target['attention_score_buffer_gib']['float16'])} GiB`",
        f"- fp32 attention score buffer: `{fmt(target['attention_score_buffer_gib']['float32'])} GiB`",
        f"- local physical memory: `{fmt(system.get('physical_memory_gib'))} GiB`",
        "",
        "这里的 buffer 是单个 global attention score 的理论下限，不包含 q/k/v、MLProgram conversion 中间图、编译缓存、Python/CoreMLTools 开销。所以它只能低估目标导出压力。",
        "",
        "## Direct Attempt",
        "",
        f"- dry-run status: `{attempts.get('dry_run_status')}`",
        f"- dry-run output shapes: `{attempts.get('dry_run_output_shapes')}`",
        f"- convert report exists: `{attempts.get('convert_report_exists')}`",
        f"- target package exists: `{attempts.get('target_package_exists')}`",
        f"- status: `{attempts.get('status')}`",
        "",
        "## 已有 probe",
        "",
        "| probe | status | peak memory | package |",
        "|---|---:|---:|---:|",
        probe_row("highest pass", highest_pass),
        probe_row("highest fail", highest_fail),
        "",
        "## Probe 替代保护",
        "",
        f"- package count: `{probe_guard.get('package_count')}`",
        f"- exact target package count: `{probe_guard.get('exact_target_package_count')}`",
        f"- passed static conversion probe count: `{probe_guard.get('passed_static_conversion_probe_count')}`",
        f"- do not accept probe as product target: `{probe_guard.get('do_not_accept_probe_as_product_target')}`",
        f"- required product location: `{probe_guard.get('required_product_location')}`",
        "",
        "这些 probe 只能证明较小 shape 的 image-only CoreML conversion 路线；它们不是 `DA3BASE_280x504_N35_image_only`，也不在 APP CoreML 资源目录里，所以不能解锁 official image-only overlap gate。",
        "",
        "## 目标估算",
        "",
        f"- from highest failed probe ratio: `{fmt(estimates.get('from_highest_fail', {}).get('attention_elements_ratio'))}x`",
        f"- rough target conversion peak from failed probe: `{fmt(estimates.get('from_highest_fail', {}).get('rough_conversion_peak_memory_footprint_gib'))} GiB`",
        f"- from highest pass ratio: `{fmt(estimates.get('from_highest_pass', {}).get('attention_elements_ratio'))}x`",
        f"- rough target package size from highest pass: `{fmt(estimates.get('from_highest_pass', {}).get('rough_package_size_gib'))} GiB`",
        "",
        "## 判断",
        "",
        decision.get("interpretation", ""),
        "",
        "## 下一步",
        "",
    ]
    for action in report["next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def probe_row(label: str, row: dict[str, Any]) -> str:
    if not row:
        return f"| {label} | - | - | - |"
    shape = f"{row.get('height')}x{row.get('width')}"
    status = row.get("conversion_status")
    peak = fmt(bytes_to_gib(row.get("conversion_peak_memory_footprint_bytes")))
    package_size = fmt(bytes_to_gib(row.get("package_size_bytes")))
    return f"| {label} `{shape}` | `{status}` | `{peak} GiB` | `{package_size} GiB` |"


if __name__ == "__main__":
    raise SystemExit(main())
