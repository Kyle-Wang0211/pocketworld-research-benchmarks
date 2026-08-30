#!/usr/bin/env python3
"""Dependency-free semantic validator for Basalt VIO bench evidence.

The JSON Schemas in ../Schemas are the interchange contract.  This validator
adds cross-field and cross-revision checks that JSON Schema deliberately cannot
express, and can optionally verify manifest entries against file bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_STATES = frozenset({"valid_pass", "valid_fail", "invalid", "aborted"})
STATES = frozenset({"started", *TERMINAL_STATES})
CHANNELS = frozenset({"live_soak", "replay_paced", "replay_max"})
ARTIFACT_ROLES = frozenset(
    {
        "input_manifest", "poses", "receipt", "heartbeat", "telemetry",
        "diagnostics", "checksums", "power_profiler", "ground_truth", "other",
    }
)
IDENTITY_FIELDS = (
    "contract_sha256",
    "app_binary_sha256",
    "engine_artifact_sha256",
    "config_sha256",
    "input_definition_sha256",
    "metric_definitions_sha256",
)
LIVE_RESULT_METRICS = frozenset(
    {
        "processed_fps",
        "p95_pipeline_latency_ms",
        "app_drop_rate",
        "thermal_critical_seconds",
        "thermal_serious_seconds",
        "peak_phys_footprint_mb",
        "finite_pose_ratio",
        "battery_level_delta",
        "cpu_seconds",
    }
)
REPLAY_RESULT_METRICS = frozenset(
    {
        "processed_fps",
        "ate_rmse_m",
        "rpe_translation_rmse_m",
        "rpe_rotation_rmse_deg",
        "ground_truth_coverage",
        "cpu_seconds",
    }
)
REPLAY_REQUIRED_ARTIFACTS = {
    "input_manifest.json": "input_manifest",
    "poses.tum": "poses",
    "receipt.json": "receipt",
    "heartbeat.json": "heartbeat",
    "diagnostics.json": "diagnostics",
    "SHA256SUMS": "checksums",
}
LIVE_REQUIRED_ARTIFACTS = {
    "input_manifest.json": "input_manifest",
    "receipt.json": "receipt",
    "heartbeat.json": "heartbeat",
    "telemetry.jsonl": "telemetry",
    "diagnostics.json": "diagnostics",
    "SHA256SUMS": "checksums",
}


def _mapping(value: Any, path: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return {}
    return value


def _required(document: Mapping[str, Any], fields: Iterable[str], prefix: str, errors: list[str]) -> None:
    for field in fields:
        if field not in document:
            errors.append(f"{prefix}{field} is required")


def _valid_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
        return True
    except ValueError:
        return False


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_common_header(document: Mapping[str, Any], errors: list[str]) -> None:
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not _valid_uuid(document.get("run_id")):
        errors.append("run_id must be a canonical UUID")


def validate_receipt(document: Any) -> list[str]:
    errors: list[str] = []
    receipt = _mapping(document, "receipt", errors)
    _required(
        receipt,
        (
            "schema_version",
            "run_id",
            "experiment_id",
            "state",
            "channel",
            "input_camera_count",
            "started_at_utc",
            "scope",
            "global_default_eligible",
            "app",
            "device",
            "identities",
            "power",
            "accuracy",
            "metrics",
        ),
        "",
        errors,
    )
    _validate_common_header(receipt, errors)
    if receipt.get("experiment_id") != "vio-iphone-three-arm-v1-20260829":
        errors.append("experiment_id is not the frozen experiment")

    state = receipt.get("state")
    if state not in STATES:
        errors.append("state is not recognized")
    channel = receipt.get("channel")
    if channel not in CHANNELS:
        errors.append("channel is not recognized")
    input_camera_count = receipt.get("input_camera_count")
    if input_camera_count not in {1, 2} or isinstance(input_camera_count, bool):
        errors.append("input_camera_count must be 1 or 2")
    elif channel == "live_soak" and input_camera_count != 1:
        errors.append("live_soak input_camera_count must be 1")
    if not _valid_datetime(receipt.get("started_at_utc")):
        errors.append("started_at_utc must be an RFC 3339 UTC timestamp")
    expected_scope = "same_device_same_os_shared_capture_contract_and_identical_replay_manifest"
    if receipt.get("scope") != expected_scope:
        errors.append(f"scope must be {expected_scope}")
    if receipt.get("global_default_eligible") is not False:
        errors.append("global_default_eligible must be false")

    app = _mapping(receipt.get("app"), "app", errors)
    _required(
        app,
        (
            "bundle_id",
            "uses_arkit",
            "backend",
            "algorithm_mode",
            "engine_id",
            "upstream_revision",
            "opencv_version",
        ),
        "app.",
        errors,
    )
    if app.get("bundle_id") == "com.kyle.PocketWorld":
        errors.append("production bundle is forbidden")
    engine = app.get("engine_id")
    expected = {
        "basalt": {
            "bundle_id": "com.kyle.viobench",
            "uses_arkit": False,
            "backend": "cpu",
            "algorithm_mode": "basalt_vio_only_float",
            "upstream_revision": "0f3b2b52c807f70ff4e2973ce253c73329eea7bc",
            "opencv_version": "4.12.0",
        },
        "xrslam": {
            "bundle_id": "com.kyle.viobench",
            "uses_arkit": False,
            "backend": "cpu",
            "algorithm_mode": "xrslam_generic_vio_only",
            "upstream_revision": "4beb1a942f33da9afbfae2d70e2c641cfc2bb675",
            "opencv_version": "4.0.1",
        },
        "arkit_reference": {
            "bundle_id": "com.kyle.viobench",
            "uses_arkit": True,
            "backend": "apple_arkit",
            "algorithm_mode": "arkit_world_tracking_reference",
            "upstream_revision": "apple_arkit_ios26_sdk",
            "opencv_version": "not_applicable",
        },
    }.get(engine)
    if expected is None:
        errors.append("app.engine_id must be basalt, xrslam, or arkit_reference")
    else:
        for key, value in expected.items():
            if app.get(key) != value:
                errors.append(f"app.{key} does not match engine_id")
    if engine == "arkit_reference" and channel != "live_soak":
        errors.append("ARKit reference cannot use replay channels")
    device = _mapping(receipt.get("device"), "device", errors)
    _required(device, ("model_identifier", "operating_system_version"), "device.", errors)
    for field in ("model_identifier", "operating_system_version"):
        if not isinstance(device.get(field), str) or not device.get(field):
            errors.append(f"device.{field} must be non-empty")

    identities = _mapping(receipt.get("identities"), "identities", errors)
    _required(identities, IDENTITY_FIELDS, "identities.", errors)
    for field in IDENTITY_FIELDS:
        if field in identities and not isinstance(identities[field], str) or (
            field in identities and not SHA256_RE.fullmatch(identities[field])
        ):
            errors.append(f"identities.{field} must be 64 lowercase hex characters")

    power = _mapping(receipt.get("power"), "power", errors)
    _required(power, ("power_w", "power_w_status", "battery_and_thermal_are_proxies"), "power.", errors)
    if power.get("power_w", object()) is not None:
        errors.append("power.power_w must be null")
    if power.get("power_w_status") != "unavailable_public_api":
        errors.append("power.power_w_status must be unavailable_public_api")
    if power.get("battery_and_thermal_are_proxies") is not True:
        errors.append("power.battery_and_thermal_are_proxies must be true")

    accuracy = _mapping(receipt.get("accuracy"), "accuracy", errors)
    _required(accuracy, ("status", "ground_truth"), "accuracy.", errors)
    ground_truth = accuracy.get("ground_truth")
    if isinstance(ground_truth, str) and "arkit" in ground_truth.lower():
        errors.append("ARKit ground truth is forbidden")
    if channel == "live_soak":
        if accuracy.get("status") != "not_evaluable":
            errors.append("live_soak accuracy.status must be not_evaluable")
        if ground_truth != "none" and not (isinstance(ground_truth, str) and "arkit" in ground_truth.lower()):
            errors.append("live_soak accuracy.ground_truth must be none")
    elif channel in {"replay_paced", "replay_max"}:
        if accuracy.get("status") != "evaluable":
            errors.append("replay accuracy.status must be evaluable")
        if ground_truth != "euroc":
            errors.append("replay accuracy.ground_truth must be euroc")

    metrics = _mapping(receipt.get("metrics"), "metrics", errors)
    for name, value in metrics.items():
        if not isinstance(name, str) or not _finite_number(value):
            errors.append(f"metrics.{name} must be a finite number")

    if state == "started":
        if "ended_at_utc" in receipt:
            errors.append("ended_at_utc is forbidden for started state")
        if "termination" in receipt:
            errors.append("termination is forbidden for started state")
        if metrics:
            errors.append("metrics must be empty for started state")
    elif state in TERMINAL_STATES:
        if "ended_at_utc" not in receipt:
            errors.append("ended_at_utc is required for terminal states")
        elif not _valid_datetime(receipt.get("ended_at_utc")):
            errors.append("ended_at_utc must be an RFC 3339 UTC timestamp")
        elif _valid_datetime(receipt.get("started_at_utc")):
            start = datetime.fromisoformat(receipt["started_at_utc"][:-1] + "+00:00")
            end = datetime.fromisoformat(receipt["ended_at_utc"][:-1] + "+00:00")
            if end < start:
                errors.append("ended_at_utc must not precede started_at_utc")
        termination = _mapping(receipt.get("termination"), "termination", errors)
        _required(termination, ("reason_code", "recovered_from_interruption"), "termination.", errors)
        if not isinstance(termination.get("reason_code"), str) or not termination.get("reason_code"):
            errors.append("termination.reason_code must be non-empty")
        if not isinstance(termination.get("recovered_from_interruption"), bool):
            errors.append("termination.recovered_from_interruption must be boolean")
        if state == "aborted" and termination.get("reason_code") == "interrupted_recovery":
            if termination.get("recovered_from_interruption") is not True:
                errors.append("interrupted recovery must set recovered_from_interruption true")
        elif termination.get("recovered_from_interruption") is True:
            errors.append("only interrupted_recovery may set recovered_from_interruption true")

        if state in {"valid_pass", "valid_fail"}:
            required_metrics = LIVE_RESULT_METRICS if channel == "live_soak" else REPLAY_RESULT_METRICS
            for name in sorted(required_metrics - metrics.keys()):
                errors.append(f"metrics.{name} is required for a valid {channel} result")
            expected_reason = "thresholds_met" if state == "valid_pass" else "gates_not_met"
            if termination.get("reason_code") != expected_reason:
                errors.append(f"{state} termination.reason_code must be {expected_reason}")

    return errors


def validate_transition(previous: Any | None, current: Any) -> list[str]:
    errors = validate_receipt(current)
    if not isinstance(current, dict):
        return errors
    if previous is None:
        if current.get("state") != "started":
            errors.append("first receipt state must be started")
        return errors
    if not isinstance(previous, dict):
        errors.append("previous receipt must be an object")
        return errors
    previous_errors = validate_receipt(previous)
    if previous_errors:
        errors.extend(f"previous: {error}" for error in previous_errors)
        return errors
    previous_state = previous.get("state")
    current_state = current.get("state")
    if previous_state != "started" or current_state not in TERMINAL_STATES:
        errors.append(f"illegal receipt transition {previous_state} -> {current_state}")
    for field in ("schema_version", "run_id", "experiment_id", "channel", "input_camera_count", "started_at_utc", "scope", "global_default_eligible", "app", "device"):
        if previous.get(field) != current.get(field):
            errors.append(f"{field} must not change across a run")
    if previous.get("identities") != current.get("identities"):
        errors.append("identities must not change across a run")
    if previous.get("power") != current.get("power"):
        errors.append("power evidence policy must not change across a run")
    if previous.get("accuracy") != current.get("accuracy"):
        errors.append("accuracy evidence policy must not change across a run")
    return errors


def validate_heartbeat(document: Any) -> list[str]:
    errors: list[str] = []
    heartbeat = _mapping(document, "heartbeat", errors)
    _required(
        heartbeat,
        ("schema_version", "run_id", "receipt_state", "sequence", "monotonic_ns", "written_at_utc", "started_receipt_sha256"),
        "heartbeat.",
        errors,
    )
    _validate_common_header(heartbeat, errors)
    if heartbeat.get("receipt_state") != "started":
        errors.append("heartbeat.receipt_state must be started")
    sequence = heartbeat.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        errors.append("heartbeat.sequence must be a non-negative integer")
    monotonic_ns = heartbeat.get("monotonic_ns")
    if not isinstance(monotonic_ns, int) or isinstance(monotonic_ns, bool) or monotonic_ns < 0:
        errors.append("heartbeat.monotonic_ns must be a non-negative integer")
    if not _valid_datetime(heartbeat.get("written_at_utc")):
        errors.append("heartbeat.written_at_utc must be an RFC 3339 UTC timestamp")
    if not isinstance(heartbeat.get("started_receipt_sha256"), str) or not SHA256_RE.fullmatch(
        heartbeat.get("started_receipt_sha256", "")
    ):
        errors.append("heartbeat.started_receipt_sha256 must be 64 lowercase hex characters")
    return errors


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def validate_artifact_manifest(
    document: Any,
    *,
    channel: str | None = None,
    base_directory: str | Path | None = None,
) -> list[str]:
    errors: list[str] = []
    manifest = _mapping(document, "artifact_manifest", errors)
    _required(manifest, ("schema_version", "run_id", "generated_at_utc", "artifacts"), "", errors)
    _validate_common_header(manifest, errors)
    if not _valid_datetime(manifest.get("generated_at_utc")):
        errors.append("generated_at_utc must be an RFC 3339 UTC timestamp")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be an array")
        return errors
    seen_paths: set[str] = set()
    available: dict[str, str] = {}
    base = Path(base_directory).resolve() if base_directory is not None else None
    for index, raw_entry in enumerate(artifacts):
        entry = _mapping(raw_entry, f"artifacts[{index}]", errors)
        prefix = f"artifacts[{index}]."
        _required(entry, ("path", "role", "byte_count", "sha256"), prefix, errors)
        path_value = entry.get("path")
        if isinstance(path_value, str):
            if path_value in seen_paths and "artifact paths must be unique" not in errors:
                errors.append("artifact paths must be unique")
            seen_paths.add(path_value)
        if not _safe_relative_path(path_value):
            errors.append(f"{prefix}path must be a safe relative path")
        elif isinstance(path_value, str):
            available[path_value] = entry.get("role")
        byte_count = entry.get("byte_count")
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
            errors.append(f"{prefix}byte_count must be a non-negative integer")
        if entry.get("role") not in ARTIFACT_ROLES:
            errors.append(f"{prefix}role is not recognized")
        sha256 = entry.get("sha256")
        if "sha256" in entry and (not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256)):
            errors.append(f"{prefix}sha256 must be 64 lowercase hex characters")
        if base is not None and _safe_relative_path(path_value):
            artifact_path = (base / path_value).resolve()
            if base not in artifact_path.parents:
                errors.append(f"{prefix}path escapes base directory")
            elif not artifact_path.is_file():
                errors.append(f"{prefix}path does not exist as a file")
            else:
                payload = artifact_path.read_bytes()
                if isinstance(byte_count, int) and byte_count != len(payload):
                    errors.append(f"{prefix}byte_count does not match file bytes")
                if isinstance(sha256, str) and SHA256_RE.fullmatch(sha256) and hashlib.sha256(payload).hexdigest() != sha256:
                    errors.append(f"{prefix}sha256 does not match file bytes")
    if channel is not None and channel not in CHANNELS:
        errors.append("channel is not recognized")
    if channel == "live_soak":
        for path, role in LIVE_REQUIRED_ARTIFACTS.items():
            if available.get(path) != role:
                errors.append(f"live_soak artifact {path} with role {role} is required")
    if channel in {"replay_paced", "replay_max"}:
        for path, role in REPLAY_REQUIRED_ARTIFACTS.items():
            if available.get(path) != role:
                errors.append(f"replay artifact {path} with role {role} is required")
    return errors


def validate_metric_definitions(document: Any) -> list[str]:
    errors: list[str] = []
    catalog = _mapping(document, "metric_definitions", errors)
    _required(catalog, ("schema_version", "catalog_id", "metrics"), "", errors)
    if catalog.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if catalog.get("catalog_id") != "vio-replacement-three-arm-metrics-v1":
        errors.append("catalog_id is not the frozen metric catalog")
    metrics = _mapping(catalog.get("metrics"), "metrics", errors)
    required = LIVE_RESULT_METRICS | REPLAY_RESULT_METRICS | {"power_w"}
    for name in sorted(required - metrics.keys()):
        errors.append(f"metrics.{name} definition is required")
    for name, raw_definition in metrics.items():
        definition = _mapping(raw_definition, f"metrics.{name}", errors)
        for field in ("unit", "aggregation", "definition"):
            value = definition.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"metrics.{name}.{field} must be non-empty")
        channels = definition.get("applicable_channels")
        if not isinstance(channels, list) or not channels or any(channel not in CHANNELS for channel in channels):
            errors.append(f"metrics.{name}.applicable_channels must contain recognized channels")
    power = metrics.get("power_w")
    if isinstance(power, dict) and power.get("availability") != "must_be_null_without_external_calibrated_analyzer":
        errors.append("metrics.power_w.availability must forbid inferred watts")
    return errors


def _load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="kind", required=True)
    receipt_parser = subparsers.add_parser("receipt", help="validate a run receipt")
    receipt_parser.add_argument("path")
    receipt_parser.add_argument("--previous", help="previous receipt for transition validation")
    heartbeat_parser = subparsers.add_parser("heartbeat", help="validate a heartbeat")
    heartbeat_parser.add_argument("path")
    manifest_parser = subparsers.add_parser("manifest", help="validate and optionally verify an artifact manifest")
    manifest_parser.add_argument("path")
    manifest_parser.add_argument("--channel", choices=sorted(CHANNELS))
    manifest_parser.add_argument("--base-directory")
    metrics_parser = subparsers.add_parser("metric-definitions", help="validate the metric catalog")
    metrics_parser.add_argument("path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document = _load_json(args.path)
        if args.kind == "receipt":
            errors = validate_transition(_load_json(args.previous), document) if args.previous else validate_receipt(document)
        elif args.kind == "heartbeat":
            errors = validate_heartbeat(document)
        elif args.kind == "manifest":
            errors = validate_artifact_manifest(document, channel=args.channel, base_directory=args.base_directory)
        else:
            errors = validate_metric_definitions(document)
    except (OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
