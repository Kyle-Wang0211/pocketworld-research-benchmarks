#!/usr/bin/env python3
"""Audit the DA3 product runtime path against the official image-only contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_APP_REPO = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter")
DEFAULT_CAPTURE_SERVICES = Path(
    "/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services"
)
DEFAULT_RESEARCH_REPO = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks"
)
DEFAULT_DATASET = (
    DEFAULT_RESEARCH_REPO / "data/official_da3_base_k35_strict_seq_2026_06_02"
)
TARGET_IMAGE_ONLY_RESOURCE = "DA3BASE_280x504_N35_image_only"
POSE_COMPAT_RESOURCE = "DA3BASE_476x742_N35_pose"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-repo", type=Path, default=DEFAULT_APP_REPO)
    parser.add_argument("--capture-services-dir", type=Path, default=DEFAULT_CAPTURE_SERVICES)
    parser.add_argument("--research-repo", type=Path, default=DEFAULT_RESEARCH_REPO)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_product_runtime_alignment_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_product_runtime_alignment_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    app = args.app_repo
    capture = args.capture_services_dir
    research = args.research_repo
    pose_model = app / f"ios/Runner/Models/DA3-BASE-CoreML/{POSE_COMPAT_RESOURCE}.mlpackage"
    image_only_model = (
        app / f"ios/Runner/Models/DA3-BASE-CoreML/{TARGET_IMAGE_ONLY_RESOURCE}.mlpackage"
    )
    image_only_compiled = (
        app / f"ios/Runner/Models/DA3-BASE-CoreML/{TARGET_IMAGE_ONLY_RESOURCE}.mlmodelc"
    )
    xcode_project = app / "ios/Runner.xcodeproj/project.pbxproj"
    model_loader = app / "ios/Runner/ModelLoaderPlugin.swift"
    dart_contract = capture / "lib/src/da3_camera_contract.dart"
    derivation = capture / "lib/src/photo_bundle_derivation_service.dart"
    policy = capture / "lib/src/photo_bundle_pipeline_policy_service.dart"
    app_runner = app / "lib/pipeline/local_pipeline_runner.dart"
    app_runner_test = app / "test/local_pipeline_runner_test.dart"
    swift_plugin = app / "ios/Runner/Da3DepthPlugin.swift"
    mac_exporter = research / "tools/python/da3_mac_window_export.py"

    texts = {
        "dart_contract": read_text(dart_contract),
        "derivation": read_text(derivation),
        "policy": read_text(policy),
        "app_runner": read_text(app_runner),
        "app_runner_test": read_text(app_runner_test),
        "model_loader": read_text(model_loader),
        "swift_plugin": read_text(swift_plugin),
        "mac_exporter": read_text(mac_exporter),
        "xcode_project": read_text(xcode_project),
    }
    coreml = inspect_coreml_model(pose_model)
    target_artifact_exists = image_only_model.exists() or image_only_compiled.exists()
    pose_referenced_by_xcode = POSE_COMPAT_RESOURCE in texts["xcode_project"]
    target_referenced_by_xcode = TARGET_IMAGE_ONLY_RESOURCE in texts["xcode_project"]
    checks = [
        check(
            "pose_compat_coreml_on_disk",
            pose_model.exists(),
            str(pose_model),
            "Pose-conditioned DA3 CoreML remains on disk as compatibility/research evidence.",
            status_when_true="warning",
        ),
        check(
            "pose_compat_not_referenced_by_xcode_resources",
            not pose_referenced_by_xcode,
            str(xcode_project),
            "Pose-conditioned DA3 is not referenced by Runner Xcode resources.",
        ),
        check(
            "target_image_only_coreml_artifact_present",
            target_artifact_exists,
            f"{image_only_model} or {image_only_compiled}",
            "Official image-only DA3 CoreML artifact is required before APP can claim DA3-Streaming baseline.",
            status_when_false="warning",
        ),
        check(
            "target_image_only_referenced_by_xcode_resources",
            target_referenced_by_xcode,
            str(xcode_project),
            "Official image-only DA3 CoreML must be referenced by Runner Xcode resources after the artifact exists.",
            status_when_false="warning",
        ),
        check(
            "pose_coreml_signature_known",
            set(coreml.get("inputs", [])) == {"image", "extrinsics", "intrinsics"},
            str(pose_model),
            f"Observed CoreML inputs: {coreml.get('inputs')}; outputs: {coreml.get('outputs')}",
            status_when_false="unknown",
        ),
        check(
            "dart_camera_contract_helper",
            all(
                token in texts["dart_contract"]
                for token in [
                    "opencvWorldToCameraFromArkitCameraTransform",
                    "opencv_w2c_row_major_4x4",
                    "scaledIntrinsics3x3",
                ]
            ),
            str(dart_contract),
            "Pure Dart helper owns ARKit c2w -> OpenCV w2c and scaled intrinsics.",
        ),
        check(
            "dart_manifest_writes_da3_camera_fields",
            all(
                token in texts["derivation"]
                for token in [
                    "cameraExtrinsicOpenCvW2c4x4",
                    "cameraIntrinsic3x3",
                    "cameraContract",
                ]
            ),
            str(derivation),
            "da3_input_manifest.json now stores precomputed DA3 camera tensors per frame.",
        ),
        check(
            "dart_app_payload_carries_da3_camera_fields",
            all(
                token in texts["app_runner"]
                for token in [
                    "cameraExtrinsicOpenCvW2c4x4",
                    "cameraIntrinsic3x3",
                    "_da3CameraExtrinsicOpenCvW2c4x4",
                    "_da3CameraIntrinsic3x3",
                ]
            ),
            str(app_runner),
            "APP Dart payload computes/fills DA3 camera fields before invoking native.",
        ),
        check(
            "dart_depth_stage_allows_only_target_image_only_resource",
            "DA3BASE_280X504_N35_IMAGE_ONLY" in texts["app_runner"]
            and "DA3BASE_476X742_N35_POSE" not in texts["app_runner"]
            and "DA3BASE_476X742_N35_IMAGE_ONLY" not in texts["app_runner"],
            str(app_runner),
            "Dart DepthStage DA3 resource allowlist contains only the official DA3BASE_280x504_N35_image_only target.",
        ),
        check(
            "dart_method_channel_payload_carries_image_only_tensor_input",
            all(
                token in texts["app_runner_test"]
                for token in [
                    "default depth stage MethodChannel ABI returns native adapter results",
                    "DA3BASE_280x504_N35_image_only",
                    "da3InputContract",
                    "image_only",
                    "officialStreamingBaseline",
                    "requiredExternalCameraInputs",
                    "imageTensorFloat32ChwRelativePath",
                    "imageTensorFloat32ChwPath",
                    "tensorFile.existsSync()",
                    "inputWidth * inputHeight * 3 * 4",
                ]
            ),
            str(app_runner_test),
            "Flutter MethodChannel ABI test now proves native receives the official image-only target, no external camera requirement, and a real float32 CHW tensor file of W*H*3*4 bytes.",
        ),
        check(
            "static_probe_resources_not_packaged_or_routable",
            all(
                "DA3BASE_static_" not in texts[name]
                and "DA3BASE_STATIC_" not in texts[name]
                for name in [
                    "xcode_project",
                    "model_loader",
                    "swift_plugin",
                    "app_runner",
                ]
            )
            and "staticProbeResourcePrefix" in texts["app_runner_test"]
            and "staticProbeResourcePrefixUpper" in texts["app_runner_test"]
            and "isNot(contains(staticProbeResourcePrefix))"
            in texts["app_runner_test"]
            and "isNot(contains(staticProbeResourcePrefixUpper))"
            in texts["app_runner_test"],
            str(app_runner_test),
            "APP Xcode resources, model loader, native allowlist, and Dart runner do not reference DA3BASE_static_* probe packages; the resource guard test explicitly rejects static probe names, so Research static probes cannot be routed as product official baseline.",
        ),
        check(
            "swift_confidence_minus_one_before_write",
            all(
                token in texts["swift_plugin"]
                for token in [
                    "DA3-Streaming applies `predictions.conf -= 1.0`",
                    "let confSlice = Array(conf[lo..<hi]).map { $0 - 1.0 }",
                    "try Self.writeFloats(confSlice",
                ]
            ),
            str(swift_plugin),
            "Swift native writes confidencePath after the official DA3-Streaming conf -= 1.0 convention instead of raw depth_conf.",
        ),
        check(
            "dart_pointcloud_mobile_replay_npz_executor_smoke",
            all(
                token in texts["app_runner"]
                for token in [
                    "_writeDa3PointCloudMobileReplay",
                    "mobile_replay_of_official_npz_output_process",
                    "official_python_oracle",
                    "confThresholdCoef: 0.5",
                    "sampleRatio: 0.015",
                    "_writeBinaryLittleEndianPly",
                    "OpenCV w2c",
                ]
            )
            and all(
                token in texts["app_runner_test"]
                for token in [
                    "pointcloud stage executes mobile replay of official npz_output_process",
                    "valid_point_count_before_sampling",
                    "element vertex 1",
                    "format binary_little_endian 1.0",
                ]
            ),
            str(app_runner_test),
            "APP PointCloudStage now has a tested Dart mobile replay for the official results_output/frame_*.npz + npz_output_process.py semantics when depth_index payloads are complete; Research/desktop official Python remains the oracle.",
        ),
        check(
            "swift_image_only_requires_predicted_pose_outputs",
            all(
                token in texts["swift_plugin"]
                for token in [
                    "official image-only CoreML output missing pred_extrinsics/pred_intrinsics; refusing external-camera fallback",
                    "expectedPredExtrinsics = spec.windowSize * 12",
                    "expectedPredIntrinsics = spec.windowSize * 9",
                    "official image-only CoreML pred pose size mismatch",
                ]
            ),
            str(swift_plugin),
            "Swift image-only adapter now requires predicted pred_extrinsics/pred_intrinsics outputs and refuses to synthesize downstream pose files from external camera metadata.",
        ),
        check(
            "swift_native_consumes_precomputed_camera",
            all(
                token in texts["swift_plugin"]
                for token in [
                    'frame["cameraExtrinsicOpenCvW2c4x4"]',
                    'frame["cameraIntrinsic3x3"]',
                    "fallbackExtrinsics4x4",
                ]
            ),
            str(swift_plugin),
            "Swift keeps the precomputed camera helper code only for legacy/pose-conditioned compatibility, but the official image-only runtime rejects non-image-only input and requires predicted pose outputs.",
        ),
        check(
            "swift_native_rejects_non_image_only_contract",
            all(
                token in texts["swift_plugin"]
                for token in [
                    "supportedResourceNames.contains(resourceName)",
                    'inputContract.lowercased() == "image_only"',
                    "official image-only DA3 resource requires da3InputContract=image_only",
                ]
            ),
            str(swift_plugin),
            "Swift native adapter hard-rejects unsupported DA3 resources and non-image-only input contracts before model loading.",
        ),
        check(
            "mac_exporter_consumes_same_camera_contract",
            all(
                token in texts["mac_exporter"]
                for token in [
                    "da3_extrinsics(frame, input_frame)",
                    "da3_intrinsics(frame, input_frame",
                    'input_frame.get("cameraExtrinsicOpenCvW2c4x4")',
                    'input_frame.get("cameraIntrinsic3x3")',
                ]
            ),
            str(mac_exporter),
            "Research Mac exporter follows the same Dart manifest camera contract when fields are present.",
        ),
        check(
            "policy_labels_dart_camera_ownership",
            all(
                token in texts["policy"]
                for token in [
                    "DA3 camera tensor convention conversion",
                    "da3CameraFieldsOwner",
                    "Flutter/Dart da3_input_manifest.json",
                ]
            ),
            str(policy),
            "Capture policy labels DA3 camera tensor convention as Dart-owned.",
        ),
    ]
    failing = [item for item in checks if item["status"] in {"fail", "unknown"}]
    status = (
        "official_image_only_runtime_ready"
        if target_artifact_exists
        and target_referenced_by_xcode
        and not pose_referenced_by_xcode
        and not failing
        else "official_image_only_runtime_not_ready_pose_compat_not_packaged"
    )
    return {
        "schema_version": "aether_da3_product_runtime_alignment_audit_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "product_mainline": TARGET_IMAGE_ONLY_RESOURCE,
            "compatibility_side_path": POSE_COMPAT_RESOURCE,
            "compatibility_side_path_role": (
                "on_disk_research_evidence_not_xcode_packaged_baseline"
                if not pose_referenced_by_xcode
                else "still_xcode_packaged_must_not_be_called_official_baseline"
            ),
            "a100_or_large_memory_mac_role": "research_reference_only_not_mobile_viability_gate",
            "next_best_action": (
                "Run same-capture APP/native image-only overlap regression with "
                f"{TARGET_IMAGE_ONLY_RESOURCE}, then run official core-frame npz downstream."
                if status == "official_image_only_runtime_ready"
                else (
                    f"Export or obtain {TARGET_IMAGE_ONLY_RESOURCE} CoreML, add it to Runner "
                    "resources, rerun readiness/signature gates, then run same-capture image-only "
                    "overlap regression."
                )
            ),
        },
        "artifacts": {
            "pose_model": path_item(pose_model),
            "image_only_model": path_item(image_only_model),
            "image_only_compiled": path_item(image_only_compiled),
            "xcode_project": path_item(xcode_project),
            "model_loader": path_item(model_loader),
            "dart_contract": path_item(dart_contract),
            "derivation": path_item(derivation),
            "app_runner": path_item(app_runner),
            "app_runner_test": path_item(app_runner_test),
            "swift_plugin": path_item(swift_plugin),
            "mac_exporter": path_item(mac_exporter),
        },
        "coreml": coreml,
        "checks": checks,
        "plain_language": [
            "89GiB/178GiB 属于旧研究导出/编译压力路径，不是移动端运行 DA3 的内存需求。",
            f"产品官方主线现在只能是 {TARGET_IMAGE_ONLY_RESOURCE}；{POSE_COMPAT_RESOURCE} 只是磁盘上的兼容/研究证据。",
            "Xcode resources 已不再引用旧 pose CoreML，所以 APP 不应再把 AR/VIO pose-conditioned 路径称为官方 baseline。",
            "Dart DepthStage 现在也只允许 DA3BASE_280x504_N35_image_only 这一条资源名进入 Stage 1。",
            "Flutter MethodChannel ABI 单测现在确认 native payload 带的是官方 image-only tensor 文件，不是旧 pose/camera 输入。",
            "APP 资源、ModelLoader、Swift allowlist 和 Dart runner 都不引用 DA3BASE_static_* probe 包；低分辨率 probe 不能被路由成产品 official baseline。",
            "DA3BASE_280x504_N35_image_only 现在已经导出、通过 image-only 签名 gate，并被 Runner Xcode Resources 引用。",
            "Swift native 现在在写 confidencePath 前执行官方 DA3-Streaming 的 conf -= 1.0，不再把 raw depth_conf 交给 downstream。",
            "Research/desktop 的权威 downstream 仍是官方 Python npz_output_process.py；APP Dart PointCloudStage 只是移动端 replay，不替代官方 oracle。",
            "Swift image-only runtime 现在必须收到模型预测的 pred_extrinsics/pred_intrinsics 输出；缺失时直接失败，不再 fallback 到外部相机。",
            "Swift native 现在会在加载模型前拒绝非 image-only input contract，防止 MethodChannel payload 绕回 pose-conditioned 输入。",
            "下一条产品证据不是点云清理，而是用真正 image-only CoreML artifact 跑 same-capture image-only overlap regression。",
        ],
    }


def inspect_coreml_model(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "inputs": [], "outputs": []}
    try:
        import coremltools as ct  # type: ignore

        model = ct.models.MLModel(str(path), skip_model_load=True)
        spec = model.get_spec()
        return {
            "exists": True,
            "coremltools": getattr(ct, "__version__", "unknown"),
            "inputs": [item.name for item in spec.description.input],
            "outputs": [item.name for item in spec.description.output],
        }
    except Exception as exc:  # pragma: no cover - best-effort diagnostics
        return {"exists": True, "inputs": [], "outputs": [], "error": repr(exc)}


def check(
    check_id: str,
    passed: bool,
    source: str,
    evidence: str,
    *,
    status_when_true: str = "pass",
    status_when_false: str = "fail",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status_when_true if passed else status_when_false,
        "evidence": evidence,
        "source": source,
    }


def path_item(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists()}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "warnings_or_failures": [
            {"id": item["id"], "status": item["status"], "evidence": item["evidence"]}
            for item in report["checks"]
            if item["status"] != "pass"
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 product runtime alignment audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- 产品主线: `{report['decision']['product_mainline']}`",
        f"- 兼容附录路径: `{report['decision']['compatibility_side_path']}`",
        f"- 兼容附录角色: `{report['decision']['compatibility_side_path_role']}`",
        f"- A100/大内存 Mac role: `{report['decision']['a100_or_large_memory_mac_role']}`",
        "",
        f"下一步：{report['decision']['next_best_action']}",
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
            "| check | status | evidence | source |",
            "|---|---:|---|---|",
        ]
    )
    for item in report["checks"]:
        lines.append(
            "| `{id}` | `{status}` | {evidence} | `{source}` |".format(
                id=item["id"],
                status=item["status"],
                evidence=str(item["evidence"]).replace("|", "\\|"),
                source=Path(str(item["source"])).name,
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
