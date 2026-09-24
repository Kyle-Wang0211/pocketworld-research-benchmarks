#!/usr/bin/env python3
"""Evaluate whether a PocketWorld DA3 capture proves mobile viability.

This gate is intentionally conservative. It distinguishes official-baseline
alignment from product viability:

* official hard checks can pass on research artifacts;
* mobile viability cannot pass without real-device telemetry and explicit
  latency / memory thresholds supplied by the caller.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Any


BLOCKED_MODEL_FRAGMENTS = ("LARGE", "GIANT", "NESTED")
OFFICIAL_CONFIDENCE_MODE = "official_da3_streaming_conf_minus_one"


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        out = float(value)
        return out if math.isfinite(out) else None
    if isinstance(value, str):
        try:
            out = float(value)
        except ValueError:
            return None
        return out if math.isfinite(out) else None
    return None


def as_int(value: Any) -> int | None:
    f = as_float(value)
    if f is None:
        return None
    return int(f)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "p50": median(values),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }


def check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    expected: str,
    observed: Any,
    *,
    warning: bool = False,
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "pass" if passed else ("warning" if warning else "fail"),
            "expected": expected,
            "observed": observed,
        }
    )


def resolve_capture_paths(args: argparse.Namespace) -> dict[str, Path | None]:
    capture_dir = Path(args.capture_dir).resolve() if args.capture_dir else None
    depth_index = Path(args.depth_index).resolve() if args.depth_index else None
    pointcloud_report = (
        Path(args.pointcloud_report).resolve() if args.pointcloud_report else None
    )
    real_device_audit = (
        Path(args.real_device_audit).resolve() if args.real_device_audit else None
    )

    if capture_dir is not None:
        depth_index = depth_index or capture_dir / "stages/depth/depth_index.json"
        pointcloud_report = (
            pointcloud_report
            or capture_dir / "stages/pointcloud/official_pointcloud_report.json"
        )
        real_device_audit = (
            real_device_audit or capture_dir / "stages/depth/da3_real_device_audit.json"
        )

    return {
        "capture_dir": capture_dir,
        "depth_index": depth_index,
        "pointcloud_report": pointcloud_report,
        "real_device_audit": real_device_audit,
    }


def collect_window_telemetry(audit: dict[str, Any]) -> dict[str, Any]:
    telemetry = [as_dict(item) for item in as_list(audit.get("windowTelemetry"))]
    inference_ms: list[float] = []
    load_ms: list[float] = []
    rss_peak_mb: list[float] = []
    available_mb: list[float] = []
    cpu_peak_norm: list[float] = []
    thermal_states: dict[str, int] = {}

    for item in telemetry:
        for src_key, out in (
            ("inferenceMs", inference_ms),
            ("loadMs", load_ms),
            ("rssPeakApproxMB", rss_peak_mb),
        ):
            value = as_float(item.get(src_key))
            if value is not None:
                out.append(value)

        cpu = as_dict(item.get("cpu"))
        cpu_peak = as_float(cpu.get("peakDeviceNormalizedPercent"))
        if cpu_peak is not None:
            cpu_peak_norm.append(cpu_peak)

        for system_key in ("systemAtPredictionBegin", "systemAfterPrediction"):
            system = as_dict(item.get(system_key))
            thermal = system.get("thermalState")
            if isinstance(thermal, str) and thermal:
                thermal_states[thermal] = thermal_states.get(thermal, 0) + 1
            available = as_float(
                system.get("availableMemoryMB") or system.get("jetsamAvailableMB")
            )
            if available is not None:
                available_mb.append(available)

    return {
        "telemetry_count": len(telemetry),
        "inference_ms": stats(inference_ms),
        "load_ms": stats(load_ms),
        "rss_peak_mb": stats(rss_peak_mb),
        "available_memory_mb": stats(available_mb),
        "cpu_peak_device_normalized_percent": stats(cpu_peak_norm),
        "thermal_states": thermal_states,
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    paths = resolve_capture_paths(args)
    depth_index = load_json(paths["depth_index"])
    pointcloud_report = load_json(paths["pointcloud_report"])
    file_audit = load_json(paths["real_device_audit"])
    checks: list[dict[str, Any]] = []

    check(
        checks,
        "depth_index_present",
        depth_index is not None,
        "depth_index.json is present",
        str(paths["depth_index"]),
    )
    if depth_index is None:
        return build_report(args, paths, checks, None, None, None, {})

    model = as_dict(depth_index.get("model"))
    resource = str(model.get("resourceName", ""))
    resource_upper = resource.upper()
    check(
        checks,
        "commercial_safe_da3_base_only",
        model.get("id") == "DA3-BASE"
        and str(model.get("license", "")).lower() == "apache-2.0"
        and bool(model.get("commercialSafe", True))
        and not any(fragment in resource_upper for fragment in BLOCKED_MODEL_FRAGMENTS),
        "commercial product path uses Apache-2.0 DA3-BASE only",
        model,
    )
    check(
        checks,
        "sealed_k35_476x742_contract",
        as_int(model.get("windowSize")) == 35
        and as_int(model.get("inputWidth")) == 742
        and as_int(model.get("inputHeight")) == 476
        and bool(depth_index.get("input_size_locked")) is True,
        "sealed DA3-BASE K35@476x742 input contract is used",
        {
            "windowSize": model.get("windowSize"),
            "inputWidth": model.get("inputWidth"),
            "inputHeight": model.get("inputHeight"),
            "input_size_locked": depth_index.get("input_size_locked"),
        },
    )
    check(
        checks,
        "depth_stage_completed",
        depth_index.get("status") == "completed"
        and as_int(depth_index.get("completed_count")) == as_int(depth_index.get("frame_count")),
        "all requested DA3 frames completed",
        {
            "status": depth_index.get("status"),
            "completed_count": depth_index.get("completed_count"),
            "frame_count": depth_index.get("frame_count"),
            "window_count": depth_index.get("window_count"),
        },
    )

    embedded_audit = as_dict(depth_index.get("da3_real_device_audit"))
    audit = file_audit or (embedded_audit if embedded_audit else None)
    audit_required = args.mode == "real-device"
    check(
        checks,
        "real_device_audit_present",
        audit is not None and audit.get("schema_version") == "aether_da3_real_device_audit_v1",
        "real-device audit with native telemetry is present",
        {
            "path": str(paths["real_device_audit"]),
            "embedded_schema": embedded_audit.get("schema_version"),
            "file_schema": None if file_audit is None else file_audit.get("schema_version"),
        },
        warning=not audit_required,
    )

    telemetry_summary: dict[str, Any] = {}
    if audit is not None:
        telemetry_summary = collect_window_telemetry(audit)
        audit_checks = [as_dict(item) for item in as_list(audit.get("checks"))]
        failing_audit_checks = [
            item.get("id") for item in audit_checks if item.get("status") == "fail"
        ]
        check(
            checks,
            "embedded_audit_no_failed_checks",
            not failing_audit_checks,
            "APP real-device audit has no failed official-baseline checks",
            failing_audit_checks,
        )
        check(
            checks,
            "native_window_telemetry_present",
            telemetry_summary.get("telemetry_count", 0) > 0
            and telemetry_summary.get("inference_ms", {}).get("count", 0) > 0
            and telemetry_summary.get("rss_peak_mb", {}).get("count", 0) > 0,
            "each completed DA3 window preserves native load/infer/RSS/CPU telemetry",
            telemetry_summary,
            warning=not audit_required,
        )

    if pointcloud_report is None:
        check(
            checks,
            "official_pointcloud_report_present",
            False,
            "official_pointcloud_report.json is present for downstream baseline gate",
            str(paths["pointcloud_report"]),
            warning=True,
        )
    else:
        check(
            checks,
            "official_core_frame_pointcloud_baseline",
            pointcloud_report.get("schema_version")
            == "aether_official_pointcloud_baseline_report_v1"
            and pointcloud_report.get("status") in ("completed", "completed_empty")
            and as_int(pointcloud_report.get("selected_duplicate_frame_count")) == 0
            and as_float(pointcloud_report.get("conf_threshold_coef")) == 0.5
            and as_float(pointcloud_report.get("sample_ratio")) == 0.015
            and OFFICIAL_CONFIDENCE_MODE
            in [str(x) for x in as_list(pointcloud_report.get("confidence_input_modes"))],
            "pointcloud uses official core-frame npz downstream semantics",
            {
                "status": pointcloud_report.get("status"),
                "selected_frame_count": pointcloud_report.get("selected_frame_count"),
                "selected_duplicate_frame_count": pointcloud_report.get(
                    "selected_duplicate_frame_count"
                ),
                "conf_threshold_coef": pointcloud_report.get("conf_threshold_coef"),
                "sample_ratio": pointcloud_report.get("sample_ratio"),
                "confidence_input_modes": pointcloud_report.get(
                    "confidence_input_modes"
                ),
            },
        )

    threshold_checks(args, checks, telemetry_summary)
    return build_report(args, paths, checks, depth_index, pointcloud_report, audit, telemetry_summary)


def threshold_checks(
    args: argparse.Namespace,
    checks: list[dict[str, Any]],
    telemetry_summary: dict[str, Any],
) -> None:
    thresholds = {
        "max_window_p95_ms": args.max_window_p95_ms,
        "max_window_max_ms": args.max_window_max_ms,
        "max_rss_peak_mb": args.max_rss_peak_mb,
        "min_available_memory_mb": args.min_available_memory_mb,
    }
    supplied = {key: value for key, value in thresholds.items() if value is not None}
    check(
        checks,
        "explicit_product_thresholds_supplied",
        bool(supplied),
        "caller supplies target-device latency/memory thresholds",
        supplied,
        warning=True,
    )
    if not telemetry_summary:
        return

    inference = as_dict(telemetry_summary.get("inference_ms"))
    rss = as_dict(telemetry_summary.get("rss_peak_mb"))
    available = as_dict(telemetry_summary.get("available_memory_mb"))
    thermal_states = as_dict(telemetry_summary.get("thermal_states"))

    if args.max_window_p95_ms is not None:
        observed = as_float(inference.get("p95"))
        check(
            checks,
            "window_inference_p95_within_target",
            observed is not None and observed <= args.max_window_p95_ms,
            "DA3 window p95 inference latency is within target",
            {"p95_ms": observed, "target_ms": args.max_window_p95_ms},
        )
    if args.max_window_max_ms is not None:
        observed = as_float(inference.get("max"))
        check(
            checks,
            "window_inference_max_within_target",
            observed is not None and observed <= args.max_window_max_ms,
            "DA3 worst-window inference latency is within target",
            {"max_ms": observed, "target_ms": args.max_window_max_ms},
        )
    if args.max_rss_peak_mb is not None:
        observed = as_float(rss.get("max"))
        check(
            checks,
            "rss_peak_within_target",
            observed is not None and observed <= args.max_rss_peak_mb,
            "DA3 native RSS peak is within target",
            {"rss_peak_mb": observed, "target_mb": args.max_rss_peak_mb},
        )
    if args.min_available_memory_mb is not None:
        observed = as_float(available.get("min"))
        check(
            checks,
            "available_memory_headroom_within_target",
            observed is not None and observed >= args.min_available_memory_mb,
            "device keeps enough jetsam memory headroom during DA3 inference",
            {"available_memory_min_mb": observed, "target_mb": args.min_available_memory_mb},
        )
    if args.fail_on_serious_thermal:
        serious_or_critical = sum(
            int(count)
            for state, count in thermal_states.items()
            if str(state).lower() in ("serious", "critical")
        )
        check(
            checks,
            "no_serious_or_critical_thermal_samples",
            serious_or_critical == 0,
            "thermal state never reaches serious/critical during DA3 windows",
            thermal_states,
        )
    else:
        critical = sum(
            int(count)
            for state, count in thermal_states.items()
            if str(state).lower() == "critical"
        )
        check(
            checks,
            "no_critical_thermal_samples",
            critical == 0,
            "thermal state never reaches critical during DA3 windows",
            thermal_states,
            warning=True,
        )


def build_report(
    args: argparse.Namespace,
    paths: dict[str, Path | None],
    checks: list[dict[str, Any]],
    depth_index: dict[str, Any] | None,
    pointcloud_report: dict[str, Any] | None,
    audit: dict[str, Any] | None,
    telemetry_summary: dict[str, Any],
) -> dict[str, Any]:
    failed = sum(1 for item in checks if item["status"] == "fail")
    warnings = sum(1 for item in checks if item["status"] == "warning")
    if failed:
        status = "fail"
    elif warnings:
        status = "warning"
    else:
        status = "pass"

    return {
        "schema_version": "aether_da3_mobile_viability_gate_report_v1",
        "status": status,
        "mode": args.mode,
        "meaning": {
            "pass": (
                "official-baseline checks passed, real-device telemetry exists, "
                "and caller-supplied product thresholds were met"
            ),
            "warning": (
                "baseline evidence is useful, but product viability is not proven"
            ),
            "fail": "one or more required official or product gates failed",
        }[status],
        "paths": {key: None if value is None else str(value) for key, value in paths.items()},
        "depth_status": None if depth_index is None else depth_index.get("status"),
        "pointcloud_status": None
        if pointcloud_report is None
        else pointcloud_report.get("status"),
        "audit_status": None if audit is None else audit.get("status"),
        "telemetry_summary": telemetry_summary,
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--capture-dir")
    source.add_argument("--depth-index")
    parser.add_argument("--real-device-audit")
    parser.add_argument("--pointcloud-report")
    parser.add_argument("--out")
    parser.add_argument(
        "--mode",
        choices=("real-device", "research"),
        default="real-device",
        help="In real-device mode, missing APP telemetry is a failure. In research mode, it is a warning.",
    )
    parser.add_argument("--max-window-p95-ms", type=float)
    parser.add_argument("--max-window-max-ms", type=float)
    parser.add_argument("--max-rss-peak-mb", type=float)
    parser.add_argument("--min-available-memory-mb", type=float)
    parser.add_argument("--fail-on-serious-thermal", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = evaluate(args)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
