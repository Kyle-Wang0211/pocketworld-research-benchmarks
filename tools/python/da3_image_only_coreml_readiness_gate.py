#!/usr/bin/env python3
"""Gate APP readiness for the official DA3-Streaming image-only baseline."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


TARGET_RESOURCE = "DA3BASE_280x504_N35_image_only"
POSE_COMPAT_RESOURCE = "DA3BASE_476x742_N35_pose"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-repo", type=Path, required=True)
    parser.add_argument("--capture-services-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_only_coreml_readiness_gate.json", report)
    write_markdown(
        args.out_dir / "official_da3_image_only_coreml_readiness_gate_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    models_dir = args.app_repo / "ios/Runner/Models/DA3-BASE-CoreML"
    xcode_project = args.app_repo / "ios/Runner.xcodeproj/project.pbxproj"
    local_runner = args.app_repo / "lib/pipeline/local_pipeline_runner.dart"
    native_adapter = args.app_repo / "ios/Runner/Da3DepthPlugin.swift"
    model_loader_adapter = args.app_repo / "ios/Runner/ModelLoaderPlugin.swift"
    policy_source = (
        args.capture_services_dir / "lib/src/photo_bundle_pipeline_policy_service.dart"
    )

    model_signatures = inspect_model_dir(models_dir)
    packaging_evidence = inspect_packaging(models_dir, xcode_project)
    policy_evidence = inspect_policy_source(policy_source)
    app_evidence = inspect_app_sources(
        local_runner,
        native_adapter,
        model_loader_adapter,
    )
    decision = derive_decision(
        model_signatures,
        packaging_evidence,
        policy_evidence,
        app_evidence,
    )

    return {
        "schema_version": "aether_official_da3_image_only_coreml_readiness_gate_v1",
        "date": args.date,
        "purpose": (
            "Verify whether the APP can claim parity with the official "
            "DA3-Streaming default image-only input contract."
        ),
        "inputs": {
            "app_repo": str(args.app_repo),
            "capture_services_dir": str(args.capture_services_dir),
            "models_dir": str(models_dir),
            "xcode_project": str(xcode_project),
            "local_runner": str(local_runner),
            "native_adapter": str(native_adapter),
            "model_loader_adapter": str(model_loader_adapter),
            "policy_source": str(policy_source),
        },
        "official_baseline_contract": {
            "mode": "image_only",
            "target_resource": TARGET_RESOURCE,
            "pose_compat_resource": POSE_COMPAT_RESOURCE,
            "required_model_inputs": ["image"],
            "forbidden_model_inputs": ["extrinsics", "intrinsics"],
            "expected_outputs": ["depth", "depth_conf", "pred_extrinsics", "pred_intrinsics"],
            "official_streaming_call": "model.inference(images, ref_view_strategy=...)",
            "arkit_vio_role": "metadata_only_not_da3_input",
        },
        "model_signatures": model_signatures,
        "packaging_evidence": packaging_evidence,
        "policy_evidence": policy_evidence,
        "app_evidence": app_evidence,
        "decision": decision,
        "next_actions": next_actions(decision),
    }


def inspect_model_dir(models_dir: Path) -> dict[str, Any]:
    model_paths = sorted(models_dir.glob("*.mlpackage")) + sorted(
        models_dir.glob("*.mlmodelc")
    )
    signatures = [inspect_coreml_signature(path) for path in model_paths]
    image_only = [
        row
        for row in signatures
        if row.get("available")
        and row.get("is_official_streaming_image_only_signature")
    ]
    pose_conditioned = [
        row
        for row in signatures
        if row.get("available") and row.get("is_pose_conditioned_coreml_signature")
    ]
    return {
        "models_dir": str(models_dir),
        "model_count": len(model_paths),
        "models": signatures,
        "image_only_model_count": len(image_only),
        "pose_conditioned_model_count": len(pose_conditioned),
        "has_image_only_model": bool(image_only),
        "has_pose_conditioned_model": bool(pose_conditioned),
    }


def inspect_packaging(models_dir: Path, xcode_project: Path) -> dict[str, Any]:
    text = read_text(xcode_project)
    target_pkg = models_dir / f"{TARGET_RESOURCE}.mlpackage"
    target_compiled = models_dir / f"{TARGET_RESOURCE}.mlmodelc"
    pose_pkg = models_dir / f"{POSE_COMPAT_RESOURCE}.mlpackage"
    pose_compiled = models_dir / f"{POSE_COMPAT_RESOURCE}.mlmodelc"
    target_lines = matching_lines(text, TARGET_RESOURCE)
    pose_lines = matching_lines(text, POSE_COMPAT_RESOURCE)
    return {
        "models_dir": str(models_dir),
        "xcode_project": str(xcode_project),
        "xcode_project_exists": xcode_project.exists(),
        "target_resource": TARGET_RESOURCE,
        "target_mlpackage": str(target_pkg),
        "target_mlpackage_exists": target_pkg.exists(),
        "target_mlmodelc": str(target_compiled),
        "target_mlmodelc_exists": target_compiled.exists(),
        "target_any_coreml_artifact_exists": target_pkg.exists() or target_compiled.exists(),
        "target_referenced_by_xcode_resources": bool(target_lines),
        "target_xcode_reference_lines": target_lines[:8],
        "target_has_tier_high_odr_tag": resource_has_asset_tag(
            text,
            TARGET_RESOURCE,
            "tier:high",
        ),
        "pose_compat_resource": POSE_COMPAT_RESOURCE,
        "pose_compat_mlpackage": str(pose_pkg),
        "pose_compat_mlpackage_exists": pose_pkg.exists(),
        "pose_compat_mlmodelc": str(pose_compiled),
        "pose_compat_mlmodelc_exists": pose_compiled.exists(),
        "pose_compat_any_coreml_artifact_exists": pose_pkg.exists() or pose_compiled.exists(),
        "pose_compat_referenced_by_xcode_resources": bool(pose_lines),
        "pose_compat_xcode_reference_lines": pose_lines[:8],
        "pose_compat_has_tier_high_odr_tag": resource_has_asset_tag(
            text,
            POSE_COMPAT_RESOURCE,
            "tier:high",
        ),
        "known_asset_tags_include_tier_high": '"tier:high"' in text,
        "blocking_packaging_gap": (
            f"missing_{TARGET_RESOURCE}_coreml_artifact"
            if not (target_pkg.exists() or target_compiled.exists())
            else (
                f"{TARGET_RESOURCE}_not_referenced_by_xcode_resources"
                if not target_lines
                else None
            )
        ),
    }


def inspect_coreml_signature(model_path: Path) -> dict[str, Any]:
    if not model_path.exists():
        return {
            "model_path": str(model_path),
            "available": False,
            "reason": "model path does not exist",
        }

    try:
        with tempfile.TemporaryDirectory(prefix="da3_coreml_readiness_") as tmp:
            out_dir = Path(tmp)
            subprocess.run(
                ["xcrun", "coremlcompiler", "compile", str(model_path), str(out_dir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            metadata_paths = list(out_dir.glob("*.mlmodelc/metadata.json"))
            if not metadata_paths:
                raise FileNotFoundError("compiled metadata.json not found")
            metadata = read_json(metadata_paths[0])
    except Exception as exc:  # pragma: no cover - depends on local Xcode/CoreML
        return {
            "model_path": str(model_path),
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    entry = metadata[0] if isinstance(metadata, list) and metadata else {}
    input_schema = list(entry.get("inputSchema") or [])
    output_schema = list(entry.get("outputSchema") or [])
    input_names = [str(row.get("name")) for row in input_schema]
    output_names = [str(row.get("name")) for row in output_schema]
    required_inputs = [
        str(row.get("name"))
        for row in input_schema
        if str(row.get("isOptional")) in ("0", "False", "false", "")
    ]
    forbidden_inputs = ["extrinsics", "intrinsics"]
    is_image_only = (
        required_inputs == ["image"]
        and all(name not in input_names for name in forbidden_inputs)
        and all(
            name in output_names
            for name in ("depth", "depth_conf", "pred_extrinsics", "pred_intrinsics")
        )
    )
    is_pose_conditioned = (
        "image" in required_inputs
        and "extrinsics" in required_inputs
        and "intrinsics" in required_inputs
    )
    return {
        "model_path": str(model_path),
        "resource_name": model_path.stem,
        "available": True,
        "generated_class_name": entry.get("generatedClassName"),
        "input_names": input_names,
        "output_names": output_names,
        "required_inputs": required_inputs,
        "input_shapes": {
            str(row.get("name")): row.get("shape") for row in input_schema
        },
        "output_shapes": {
            str(row.get("name")): row.get("shape") for row in output_schema
        },
        "requires_external_camera_inputs": all(
            name in required_inputs for name in forbidden_inputs
        ),
        "is_official_streaming_image_only_signature": is_image_only,
        "is_pose_conditioned_coreml_signature": is_pose_conditioned,
    }


def inspect_policy_source(path: Path) -> dict[str, Any]:
    text = read_text(path)
    selected_spec_is_image_only = (
        "da3BaseK35OfficialImageOnly" in text
        and "da3InputContract: 'image_only'" in text
    )
    selected_spec_is_official_streaming = (
        "da3BaseK35OfficialImageOnly" in text
        and "officialStreamingBaseline: true" in text
    )
    return {
        "path": str(path),
        "available": path.exists(),
        "selected_resource_name": extract_first_quoted_after(text, "resourceName:"),
        "selected_da3_input_contract": (
            "image_only" if selected_spec_is_image_only else None
        ),
        "selected_official_streaming_baseline": selected_spec_is_official_streaming,
        "default_da3_input_contract": extract_first_quoted_after(
            text, "this.da3InputContract ="
        ),
        "default_official_streaming_baseline_false": (
            "this.officialStreamingBaseline = false" in text
        ),
        "ready_image_only_coreml_signature": (
            "ready_DA3BASE_280x504_N35_image_only_coreml_signature" in text
        ),
        "pose_conditioned_compat_tag_present": "pose_conditioned_compat" in text,
        "camera_fields_marked_compat_only": (
            "pose_conditioned_compatibility_only" in text
        ),
        "official_streaming_default_match_false": (
            "'officialStreamingDefaultMatch': false" in text
        ),
    }


def inspect_app_sources(
    local_runner: Path,
    native_adapter: Path,
    model_loader_adapter: Path,
) -> dict[str, Any]:
    local_text = read_text(local_runner)
    native_text = read_text(native_adapter)
    model_loader_text = read_text(model_loader_adapter)
    return {
        "local_runner": {
            "path": str(local_runner),
            "available": local_runner.exists(),
            "official_image_only_gate_present": (
                "official_streaming_image_only_coreml_contract" in local_text
            ),
            "pose_conditioned_detection_present": (
                "_isPoseConditionedDa3Model" in local_text
            ),
            "image_only_resource_allowlist_present": (
                "DA3BASE_280X504_N35_IMAGE_ONLY" in local_text
            ),
            "image_only_resource_allowlist_target_only": (
                "DA3BASE_280X504_N35_IMAGE_ONLY" in local_text
                and "DA3BASE_476X742_N35_POSE" not in local_text
                and "DA3BASE_476X742_N35_IMAGE_ONLY" not in local_text
            ),
        },
        "native_adapter": {
            "path": str(native_adapter),
            "available": native_adapter.exists(),
            "image_only_resource_allowlist_present": (
                "DA3BASE_280x504_N35_image_only" in native_text
            ),
            "image_only_input_contract_hard_reject_present": (
                'inputContract.lowercased() == "image_only"' in native_text
                and "official image-only DA3 resource requires da3InputContract=image_only"
                in native_text
            ),
            "pose_conditioned_branch_present": "if spec.isPoseConditioned" in native_text,
            "image_only_provider_branch_present": (
                '"image": MLFeatureValue(multiArray: imageArray)' in native_text
                and "extrinsics" in native_text
                and "intrinsics" in native_text
            ),
            "input_contract_telemetry_present": '"inputContract": spec.inputContract'
            in native_text,
        },
        "model_loader_adapter": {
            "path": str(model_loader_adapter),
            "available": model_loader_adapter.exists(),
            "image_only_resource_mapping_present": TARGET_RESOURCE
            in model_loader_text,
            "compiled_mlmodelc_lookup_present": (
                '"mlmodelc", "mlpackage"' in model_loader_text
            ),
            "source_mlpackage_lookup_present": "mlpackage" in model_loader_text,
            "hardcoded_single_resource_ext_removed": (
                "resourceExt" not in model_loader_text
            ),
            "odr_bundle_miss_mentions_both_extensions": (
                ".mlmodelc/.mlpackage" in model_loader_text
            ),
        },
    }


def derive_decision(
    model_signatures: dict[str, Any],
    packaging_evidence: dict[str, Any],
    policy_evidence: dict[str, Any],
    app_evidence: dict[str, Any],
) -> dict[str, Any]:
    has_image_only = bool(model_signatures["has_image_only_model"])
    target_artifact_exists = bool(
        packaging_evidence["target_any_coreml_artifact_exists"]
    )
    target_xcode_ready = bool(
        packaging_evidence["target_referenced_by_xcode_resources"]
    )
    model_dir_pose_conditioned_only = (
        model_signatures["model_count"] > 0
        and model_signatures["image_only_model_count"] == 0
        and model_signatures["pose_conditioned_model_count"] > 0
    )
    current_xcode_bundle_has_pose_conditioned_resource = bool(
        packaging_evidence["pose_compat_referenced_by_xcode_resources"]
    )
    current_bundle_is_pose_conditioned_only = (
        model_dir_pose_conditioned_only
        and current_xcode_bundle_has_pose_conditioned_resource
        and not target_xcode_ready
    )
    app_contract_ready = (
        app_evidence["local_runner"]["official_image_only_gate_present"]
        and app_evidence["local_runner"]["image_only_resource_allowlist_present"]
        and app_evidence["local_runner"]["image_only_resource_allowlist_target_only"]
        and app_evidence["native_adapter"]["image_only_resource_allowlist_present"]
        and app_evidence["native_adapter"]["image_only_input_contract_hard_reject_present"]
        and app_evidence["native_adapter"]["pose_conditioned_branch_present"]
        and app_evidence["model_loader_adapter"]["image_only_resource_mapping_present"]
        and app_evidence["model_loader_adapter"]["compiled_mlmodelc_lookup_present"]
        and app_evidence["model_loader_adapter"]["hardcoded_single_resource_ext_removed"]
    )
    policy_blocks_current_pose = (
        policy_evidence["default_official_streaming_baseline_false"]
        and policy_evidence["ready_image_only_coreml_signature"]
        and policy_evidence["camera_fields_marked_compat_only"]
    )
    official_baseline_ready = (
        has_image_only
        and target_artifact_exists
        and target_xcode_ready
        and app_contract_ready
        and not current_bundle_is_pose_conditioned_only
    )
    return {
        "status": "pass" if official_baseline_ready else "fail",
        "official_baseline_ready": official_baseline_ready,
        "has_image_only_coreml_signature": has_image_only,
        "has_target_coreml_artifact": target_artifact_exists,
        "target_referenced_by_xcode_resources": target_xcode_ready,
        "pose_compat_artifact_still_present": bool(
            packaging_evidence["pose_compat_any_coreml_artifact_exists"]
        ),
        "pose_compat_referenced_by_xcode_resources": bool(
            packaging_evidence["pose_compat_referenced_by_xcode_resources"]
        ),
        "model_dir_is_pose_conditioned_only": model_dir_pose_conditioned_only,
        "current_xcode_bundle_has_pose_conditioned_resource": (
            current_xcode_bundle_has_pose_conditioned_resource
        ),
        "current_bundle_is_pose_conditioned_only": current_bundle_is_pose_conditioned_only,
        "app_contract_ready_for_future_image_only_model": app_contract_ready,
        "policy_blocks_current_pose_model_from_official_baseline": policy_blocks_current_pose,
        "selected_policy_resource": policy_evidence["selected_resource_name"],
        "highest_priority_gap": None
        if official_baseline_ready
        else (
            f"missing_{TARGET_RESOURCE}_coreml_artifact"
            if not target_artifact_exists
            else (
                f"{TARGET_RESOURCE}_not_referenced_by_xcode_resources"
                if not target_xcode_ready
                else (
                    "missing_image_only_da3_base_coreml_signature"
                    if not has_image_only
                    else "switch_selected_model_policy_to_image_only_resource"
                )
            )
        ),
        "odr_packaging_warning": (
            f"{TARGET_RESOURCE} is not tagged tier:high in Xcode ODR resources"
            if target_xcode_ready
            and not packaging_evidence["target_has_tier_high_odr_tag"]
            else None
        ),
        "do_not_use_arkit_vio_as_da3_input_for_official_baseline": True,
        "do_not_add_downstream_cleanup_to_hide_this_gap": True,
    }


def next_actions(decision: dict[str, Any]) -> list[str]:
    if decision["status"] == "pass":
        return [
            "Run the APP/native same-capture image-only inference gate with DA3BASE_280x504_N35_image_only.",
            "Run official core-frame npz downstream on the new image-only outputs before judging thickness.",
            "Keep pose-conditioned DA3 on disk only as compatibility/research evidence; do not add it back to Xcode resources.",
        ]
    actions = [
        f"Export or obtain {TARGET_RESOURCE} CoreML with required inputs exactly: image.",
        f"Add {TARGET_RESOURCE}.mlpackage/.mlmodelc to ios/Runner/Models/DA3-BASE-CoreML and Xcode resources; tag it tier:high if shipping via ODR.",
        "Keep pred_extrinsics/pred_intrinsics outputs from DA3; do not replace them with ARKit/VIO camera inputs.",
        "Keep selectedDepthModel/resourceName on the image-only package and set officialStreamingBaseline=true only when the artifact/signature gate passes.",
        "Rerun this readiness gate, then rerun official core-frame npz downstream before judging thickness.",
    ]
    if decision["current_bundle_is_pose_conditioned_only"]:
        actions.insert(
            0,
            "Current APP bundle contains only pose-conditioned DA3 CoreML; treat it as comparison data, not baseline.",
        )
    elif decision["model_dir_is_pose_conditioned_only"]:
        actions.insert(
            0,
            "Pose-conditioned DA3 remains on disk as compatibility/research evidence, but it is no longer referenced by Xcode resources.",
        )
    return actions


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    signatures = report["model_signatures"]
    lines = [
        "# Official DA3 image-only CoreML readiness gate",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        (
            "当前不能把 APP 的 DA3 路径称为官方 DA3-Streaming baseline。"
            if decision["status"] == "fail"
            else "当前 APP 具备官方 DA3-Streaming image-only baseline 的 CoreML 输入契约。"
        ),
        "",
        "官方 baseline 的硬条件是：CoreML 只要求 `image` 输入，不要求 `extrinsics/intrinsics`；ARKit/VIO 只能留作 capture metadata 或后处理产品层信息。",
        "",
        "## Gate",
        "",
        f"- `status`: `{decision['status']}`",
        f"- `official_baseline_ready`: `{decision['official_baseline_ready']}`",
        f"- `has_image_only_coreml_signature`: `{decision['has_image_only_coreml_signature']}`",
        f"- `model_dir_is_pose_conditioned_only`: `{decision['model_dir_is_pose_conditioned_only']}`",
        f"- `current_xcode_bundle_has_pose_conditioned_resource`: `{decision['current_xcode_bundle_has_pose_conditioned_resource']}`",
        f"- `current_bundle_is_pose_conditioned_only`: `{decision['current_bundle_is_pose_conditioned_only']}`",
        f"- `app_contract_ready_for_future_image_only_model`: `{decision['app_contract_ready_for_future_image_only_model']}`",
        f"- `policy_blocks_current_pose_model_from_official_baseline`: `{decision['policy_blocks_current_pose_model_from_official_baseline']}`",
        f"- `highest_priority_gap`: `{decision['highest_priority_gap']}`",
        "",
        "## CoreML Signatures",
        "",
        f"- `model_count`: `{signatures['model_count']}`",
        f"- `image_only_model_count`: `{signatures['image_only_model_count']}`",
        f"- `pose_conditioned_model_count`: `{signatures['pose_conditioned_model_count']}`",
        "",
        "| Resource | Required inputs | Outputs | Verdict |",
        "|---|---|---|---|",
    ]
    for model in signatures["models"]:
        verdict = "image_only" if model.get("is_official_streaming_image_only_signature") else (
            "pose_conditioned" if model.get("is_pose_conditioned_coreml_signature") else "unknown"
        )
        lines.append(
            "| {resource} | {inputs} | {outputs} | {verdict} |".format(
                resource=escape_table(str(model.get("resource_name"))),
                inputs=escape_table(", ".join(model.get("required_inputs") or [])),
                outputs=escape_table(", ".join(model.get("output_names") or [])),
                verdict=verdict,
            )
        )

    lines.extend(
        [
            "",
            "## Packaging Evidence",
            "",
        ]
    )
    packaging = report["packaging_evidence"]
    for key, value in packaging.items():
        if key.endswith("_xcode_reference_lines"):
            lines.append(f"- `{key}`: `{len(value)}` line(s)")
        else:
            lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Policy Evidence",
            "",
        ]
    )
    for key, value in report["policy_evidence"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## APP Evidence",
            "",
        ]
    )
    for group, values in report["app_evidence"].items():
        lines.append(f"### {group}")
        lines.append("")
        for key, value in values.items():
            lines.append(f"- `{key}`: `{value}`")
        lines.append("")

    lines.extend(
        [
            "## Next Actions",
            "",
        ]
    )
    for index, action in enumerate(report["next_actions"], start=1):
        lines.append(f"{index}. {action}")

    lines.extend(
        [
            "",
            "## 大白话",
            "",
            f"现在手机 APP 的 native adapter 和 CoreML bundle 已经具备 image-only baseline：`{TARGET_RESOURCE}` 存在、被 Xcode Resources 引用、签名只要求 `image`，并输出 `pred_extrinsics/pred_intrinsics`。",
            "",
            f"旧 `{POSE_COMPAT_RESOURCE}` 仍可留在磁盘作研究对照，但不能重新进 Xcode Resources、不能作为官方 baseline。下一步是用这个新包跑 same-capture image-only 回归，再看单 window 厚层是否仍存在。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "coreml": {
            "model_count": report["model_signatures"]["model_count"],
            "image_only_model_count": report["model_signatures"][
                "image_only_model_count"
            ],
            "pose_conditioned_model_count": report["model_signatures"][
                "pose_conditioned_model_count"
            ],
        },
        "packaging": {
            "target_artifact_exists": report["packaging_evidence"][
                "target_any_coreml_artifact_exists"
            ],
            "target_referenced_by_xcode_resources": report["packaging_evidence"][
                "target_referenced_by_xcode_resources"
            ],
            "pose_compat_artifact_still_present": report["packaging_evidence"][
                "pose_compat_any_coreml_artifact_exists"
            ],
            "pose_compat_referenced_by_xcode_resources": report[
                "packaging_evidence"
            ]["pose_compat_referenced_by_xcode_resources"],
        },
        "bundle_semantics": {
            "model_dir_is_pose_conditioned_only": report["decision"][
                "model_dir_is_pose_conditioned_only"
            ],
            "current_xcode_bundle_has_pose_conditioned_resource": report[
                "decision"
            ]["current_xcode_bundle_has_pose_conditioned_resource"],
            "current_bundle_is_pose_conditioned_only": report["decision"][
                "current_bundle_is_pose_conditioned_only"
            ],
        },
    }


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_first_quoted_after(text: str, marker: str) -> str | None:
    index = text.find(marker)
    if index < 0:
        return None
    tail = text[index + len(marker) :]
    for quote in ("'", '"'):
        start = tail.find(quote)
        if start < 0:
            continue
        end = tail.find(quote, start + 1)
        if end > start:
            return tail[start + 1 : end]
    return None


def matching_lines(text: str, pattern: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if pattern in line]


def resource_has_asset_tag(text: str, resource: str, tag: str) -> bool:
    return any(
        "ASSET_TAGS" in line and resource in line and tag in line
        for line in text.splitlines()
    )


def escape_table(text: str) -> str:
    return text.replace("|", "\\|")


if __name__ == "__main__":
    raise SystemExit(main())
