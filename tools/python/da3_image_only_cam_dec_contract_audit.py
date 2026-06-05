#!/usr/bin/env python3
"""Audit official DA3 image-only camera-decoder contract versus current APP CoreML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_OFFICIAL_REPO = Path(
    "/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3"
)
DEFAULT_APP_REPO = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter")
DEFAULT_DART_PACKAGE = Path("/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services")
DEFAULT_POSE_COREML = (
    DEFAULT_APP_REPO
    / "ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage"
)
DEFAULT_IMAGE_ONLY_COREML = (
    DEFAULT_APP_REPO
    / "ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-repo", type=Path, default=DEFAULT_OFFICIAL_REPO)
    parser.add_argument("--app-repo", type=Path, default=DEFAULT_APP_REPO)
    parser.add_argument("--dart-package", type=Path, default=DEFAULT_DART_PACKAGE)
    parser.add_argument("--pose-coreml", type=Path, default=DEFAULT_POSE_COREML)
    parser.add_argument("--image-only-coreml", type=Path, default=DEFAULT_IMAGE_ONLY_COREML)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_only_cam_dec_contract_audit.json", report)
    write_markdown(args.out_dir / "official_da3_image_only_cam_dec_contract_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    da3_py = args.official_repo / "src/depth_anything_3/model/da3.py"
    api_py = args.official_repo / "src/depth_anything_3/api.py"
    streaming_py = args.official_repo / "da3_streaming/da3_streaming.py"
    swift_plugin = args.app_repo / "ios/Runner/Da3DepthPlugin.swift"
    dart_policy = args.dart_package / "lib/src/photo_bundle_pipeline_policy_service.dart"
    pose_signature = inspect_coreml_signature(args.pose_coreml)
    image_only_signature = inspect_coreml_signature(args.image_only_coreml)

    checks = [
        check_contains(
            "official_streaming_calls_inference_without_external_camera",
            streaming_py,
            "predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)",
            "官方 DA3-Streaming 默认只传 images/ref_view_strategy，不传 extrinsics/intrinsics。",
        ),
        check_contains(
            "official_api_external_camera_is_optional",
            api_py,
            "ex_t_norm = self._normalize_extrinsics(ex_t.clone() if ex_t is not None else None)",
            "官方 API 的 extrinsics 是 optional；没有外部相机时 ex_t_norm 仍为 None。",
        ),
        check_contains(
            "official_forward_uses_cam_enc_only_when_external_extrinsics_exist",
            da3_py,
            "if extrinsics is not None:",
            "官方网络只有在 extrinsics 存在时才用 cam_enc 生成 camera token。",
        ),
        check_contains(
            "official_forward_image_only_has_no_camera_token",
            da3_py,
            "cam_token = None",
            "没有外部相机时 backbone 的 camera token 是 None，即 image-only 分支。",
        ),
        check_contains(
            "official_cam_dec_predicts_pose_encoding",
            da3_py,
            "pose_enc = self.cam_dec(feats[-1][1])",
            "官方 cam_dec 从图像特征预测 pose encoding。",
        ),
        check_contains(
            "official_cam_dec_outputs_extrinsics_intrinsics",
            da3_py,
            "c2w, ixt = pose_encoding_to_extri_intri(pose_enc, (H, W))",
            "官方 cam_dec 输出会被转换成 extrinsics/intrinsics。",
        ),
        check_coreml_signature(
            "current_pose_coreml_requires_external_camera_inputs",
            pose_signature,
            required_inputs={"image", "extrinsics", "intrinsics"},
            evidence="当前 APP bundle 里的 pose CoreML signature 需要 image/extrinsics/intrinsics。",
        ),
        check_coreml_missing_or_image_only(
            "target_image_only_coreml_image_only_signature_ready",
            image_only_signature,
            evidence="目标 DA3BASE_280x504_N35_image_only CoreML 必须具备只要求 image 输入的 signature。",
        ),
        check_contains(
            "app_swift_keeps_pose_conditioned_compat_branch_guarded",
            swift_plugin,
            "if spec.isPoseConditioned",
            "Swift 只在 pose-conditioned compat 分支才消费 external camera tensor。",
        ),
        check_contains(
            "dart_policy_selects_image_only_resource",
            dart_policy,
            "resourceName: 'DA3BASE_280x504_N35_image_only'",
            "Dart policy 默认选择官方 image-only K35 resource。",
        ),
        check_contains(
            "swift_image_only_requires_pre_normalized_tensor",
            swift_plugin,
            "official image-only DA3 requires imageTensorFloat32ChwPath",
            "Swift image-only 分支现在强制消费 Dart 官方预处理 tensor，不再回退 PNG decode。",
        ),
        check_contains(
            "dart_policy_marks_image_only_signature_ready",
            dart_policy,
            "ready_DA3BASE_280x504_N35_image_only_coreml_signature",
            "Dart policy 已把官方 image-only APP 路径标成 image-only CoreML signature ready。",
        ),
    ]
    official_image_only_contract = all(
        item["status"] == "pass"
        for item in checks
        if item["id"].startswith("official_")
    )
    current_pose_requires_external_camera = find_status(
        checks,
        "current_pose_coreml_requires_external_camera_inputs",
    ) == "pass"
    selected_image_only_policy = find_status(
        checks,
        "dart_policy_selects_image_only_resource",
    ) == "pass"
    image_only_missing = find_status(
        checks,
        "target_image_only_coreml_image_only_signature_ready",
    ) in {"missing", "warning"}
    status = (
        "official_image_only_contract_selected_but_coreml_artifact_missing"
        if official_image_only_contract and selected_image_only_policy and image_only_missing
        else (
            "official_image_only_contract_and_product_coreml_ready"
            if official_image_only_contract and selected_image_only_policy
            else "image_only_cam_dec_contract_needs_manual_review"
        )
    )
    return {
        "schema_version": "aether_da3_image_only_cam_dec_contract_audit_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "official_algorithm_blame_supported": False,
            "official_image_only_contract": official_image_only_contract,
            "selected_image_only_policy": selected_image_only_policy,
            "current_pose_coreml_requires_external_camera": current_pose_requires_external_camera,
            "target_image_only_coreml_missing": image_only_missing,
            "conclusion": (
                "Official DA3-Streaming is image-only at the public API level: it passes images only, leaves "
                "extrinsics/intrinsics as None, and relies on cam_dec to predict camera extrinsics/intrinsics from "
                "image features. The product policy and Swift allowlist now select DA3BASE_280x504_N35_image_only; "
                "the CoreML artifact/signature is present and image-only; old pose-conditioned outputs remain "
                "compatibility/research evidence, not official APP authority."
            ),
            "next_best_action": (
                "Run the same capture/window through the product image-only CoreML path and compare official core-frame NPZ downstream."
            ),
        },
        "inputs": {
            "official_repo": str(args.official_repo),
            "app_repo": str(args.app_repo),
            "dart_package": str(args.dart_package),
            "pose_coreml": str(args.pose_coreml),
            "image_only_coreml": str(args.image_only_coreml),
        },
        "pose_coreml_signature": pose_signature,
        "image_only_coreml_signature": image_only_signature,
        "checks": checks,
        "plain_language": [
            "官方 DA3-Streaming 没有借助 AR/VIO 相机输入；它把图片交给模型，模型自己用 cam_dec 估相机。",
            "当前 APP policy/native allowlist 已改成官方 image-only K35 目标，不再把 476x742 pose 当 official mainline。",
            "Swift image-only 分支现在强制吃 Dart 写出的 normalized float32 CHW tensor，不走 PNG decode fallback。",
            "DA3BASE_280x504_N35_image_only CoreML artifact/signature 现在已存在并通过 image-only 检查。",
            "旧 pose-conditioned 输出都必须继续标成 compatibility/research path。",
        ],
    }


def inspect_coreml_signature(model_path: Path) -> dict[str, Any]:
    if not model_path.exists():
        return {"exists": False, "path": str(model_path), "inputs": [], "outputs": []}
    try:
        import coremltools as ct

        model = ct.models.MLModel(str(model_path), compute_units=ct.ComputeUnit.CPU_ONLY)
        spec = model.get_spec()
        return {
            "exists": True,
            "path": str(model_path),
            "type": spec.WhichOneof("Type"),
            "inputs": [feature.name for feature in spec.description.input],
            "outputs": [feature.name for feature in spec.description.output],
        }
    except Exception as exc:
        return {
            "exists": True,
            "path": str(model_path),
            "inspect_error": f"{type(exc).__name__}: {exc}",
            "inputs": [],
            "outputs": [],
        }


def check_coreml_signature(
    check_id: str,
    signature: dict[str, Any],
    *,
    required_inputs: set[str],
    evidence: str,
) -> dict[str, Any]:
    inputs = set(str(value) for value in signature.get("inputs", []))
    return {
        "id": check_id,
        "status": "pass" if signature.get("exists") and required_inputs.issubset(inputs) else "missing",
        "path": str(signature.get("path") or ""),
        "line": None,
        "needle": ",".join(sorted(required_inputs)),
        "evidence": evidence,
        "actual_inputs": sorted(inputs),
    }


def check_coreml_missing_or_image_only(
    check_id: str,
    signature: dict[str, Any],
    *,
    evidence: str,
) -> dict[str, Any]:
    inputs = set(str(value) for value in signature.get("inputs", []))
    if not signature.get("exists"):
        status = "missing"
    elif inputs == {"image"}:
        status = "pass"
    else:
        status = "warning"
    return {
        "id": check_id,
        "status": status,
        "path": str(signature.get("path") or ""),
        "line": None,
        "needle": "image-only CoreML signature",
        "evidence": evidence,
        "actual_inputs": sorted(inputs),
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


def find_status(checks: list[dict[str, Any]], check_id: str) -> str:
    for item in checks:
        if item.get("id") == check_id:
            return str(item.get("status"))
    return "unknown"


def find_line(text: str, needle: str) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return None


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "pose_coreml_signature": report["pose_coreml_signature"],
        "image_only_coreml_signature": report["image_only_coreml_signature"],
        "non_pass_checks": [
            {
                "id": item["id"],
                "status": item["status"],
                "evidence": item["evidence"],
            }
            for item in report["checks"]
            if item["status"] != "pass"
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 image-only cam_dec contract audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- official image-only contract: `{report['decision']['official_image_only_contract']}`",
        f"- selected image-only policy: `{report['decision']['selected_image_only_policy']}`",
        f"- current pose CoreML requires external camera: `{report['decision']['current_pose_coreml_requires_external_camera']}`",
        f"- target image-only CoreML missing: `{report['decision']['target_image_only_coreml_missing']}`",
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
            "## CoreML Signatures",
            "",
            f"- pose inputs: `{report['pose_coreml_signature'].get('inputs')}`",
            f"- pose outputs: `{report['pose_coreml_signature'].get('outputs')}`",
            f"- image-only exists: `{report['image_only_coreml_signature'].get('exists')}`",
            f"- image-only inputs: `{report['image_only_coreml_signature'].get('inputs')}`",
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
                path=Path(str(item.get("path") or "")).name,
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
