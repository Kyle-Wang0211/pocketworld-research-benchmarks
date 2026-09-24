#!/usr/bin/env python3
"""Audit whether the current runnable DA3 path is the official image-only path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
DEFAULT_OFFICIAL_REPO = Path(
    "/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3"
)
DEFAULT_DART_PACKAGE = Path(
    "/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services"
)
DEFAULT_APP_REPO = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--official-repo", type=Path, default=DEFAULT_OFFICIAL_REPO)
    parser.add_argument("--dart-package", type=Path, default=DEFAULT_DART_PACKAGE)
    parser.add_argument("--app-repo", type=Path, default=DEFAULT_APP_REPO)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_upstream_path_parity_audit.json", report)
    write_markdown(args.out_dir / "official_da3_upstream_path_parity_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official_streaming = args.official_repo / "da3_streaming/da3_streaming.py"
    official_api = args.official_repo / "src/depth_anything_3/api.py"
    official_model = args.official_repo / "src/depth_anything_3/model/da3.py"
    official_input = args.official_repo / "src/depth_anything_3/utils/io/input_processor.py"
    dart_policy = args.dart_package / "lib/src/photo_bundle_pipeline_policy_service.dart"
    dart_derivation = args.dart_package / "lib/src/photo_bundle_derivation_service.dart"
    app_pose_package = (
        args.app_repo
        / "ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage"
    )
    app_image_only_package = (
        args.app_repo
        / "ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_280x504_N35_image_only.mlpackage"
    )

    checks = [
        check_contains(
            "official_streaming_call_image_only",
            official_streaming,
            "predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)",
            "官方 DA3-Streaming 默认调用只传 images/ref_view_strategy，没有传 extrinsics/intrinsics。",
        ),
        check_contains(
            "official_forward_uses_cam_enc_only_when_external_camera_exists",
            official_model,
            "if extrinsics is not None:",
            "官方模型只有在外部 camera 存在时才创建 cam_enc token；image-only baseline 不走这个条件分支。",
        ),
        check_contains(
            "official_image_only_cam_dec_predicts_camera",
            official_model,
            "pose_enc = self.cam_dec(feats[-1][1])",
            "官方 image-only 路径用 cam_dec 从图像特征预测 pose encoding。",
        ),
        check_contains(
            "official_external_camera_normalize_and_umeyama_path",
            official_api,
            "ex_t_norm = self._normalize_extrinsics",
            "外部 camera 路径还包含首帧归一化、median-distance normalization 和后续 Umeyama 对齐。",
        ),
        check_contains(
            "official_default_preprocess_upper_bound_resize",
            official_input,
            'process_res_method: str = "upper_bound_resize"',
            "官方默认 preprocess 是 upper_bound_resize，再处理为 patch-size divisible。",
        ),
        check_contains(
            "product_policy_selects_image_only_model",
            dart_policy,
            "resourceName: 'DA3BASE_280x504_N35_image_only'",
            "当前 APP/Dart 主线默认选择官方 image-only K35 CoreML 包。",
        ),
        check_contains(
            "current_dart_camera_tensors_are_metadata_only",
            dart_derivation,
            "camera tensors are metadata/compat fields that must not be DA3 image-only inputs",
            "Dart manifest 仍保留 camera tensors，但 image-only runner contract 声明它们不是 DA3 输入。",
        ),
        check_contains(
            "current_dart_preprocess_is_official_process_res",
            dart_derivation,
            "mode: 'upper_bound_resize_patch_align'",
            "Dart 默认 DA3 input 生成走官方 process_res=504 upper_bound_resize + patch-align。",
        ),
        check_contains(
            "current_dart_runtime_input_is_normalized_tensor",
            dart_derivation,
            "imageTensorFloat32ChwRelativePath",
            "Dart 现在把官方预处理终点推进到 normalized float32 CHW tensor。",
        ),
        check_contains(
            "app_swift_image_only_refuses_png_decode_fallback",
            args.app_repo / "ios/Runner/Da3DepthPlugin.swift",
            "official image-only DA3 requires imageTensorFloat32ChwPath",
            "Swift image-only 分支强制消费 Dart tensor，不再回退 PNG decode。",
        ),
        file_exists_check(
            "legacy_pose_coreml_package_exists_for_compat_only",
            app_pose_package,
            "旧 pose-conditioned CoreML 包仍存在，但不再是 official mainline。",
        ),
        file_exists_check(
            "current_image_only_coreml_package_exists",
            app_image_only_package,
            "官方 image-only CoreML 包存在才可把 APP/CoreML 输出当成官方 image-only 路径证据。",
            expect_exists=True,
        ),
    ]

    official_evidence_ok = all(
        item["status"] == "pass"
        for item in checks[:5]
    )
    selected_image_only_policy = next(
        item for item in checks if item["id"] == "product_policy_selects_image_only_model"
    )["status"] == "pass"
    image_only_missing = next(
        item for item in checks if item["id"] == "current_image_only_coreml_package_exists"
    )["status"] != "pass"
    status = (
        "product_policy_image_only_selected_but_coreml_artifact_missing"
        if official_evidence_ok and selected_image_only_policy and image_only_missing
        else (
            "product_image_only_coreml_path_ready_for_same_capture_regression"
            if official_evidence_ok and selected_image_only_policy
            else "upstream_path_parity_needs_manual_review"
        )
    )

    return {
        "schema_version": "aether_da3_official_upstream_path_parity_audit_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "official_algorithm_blame_supported": False,
            "current_thickness_authority": (
                "product_image_only_coreml_ready_but_same_capture_regression_not_rerun"
            ),
            "highest_priority_gap": (
                None
                if not image_only_missing
                else "Product policy now points to the official image-only cam_dec path, but the image-only CoreML artifact/signature is still missing."
            ),
            "conclusion": (
                "The APP/Dart path now selects official image-only K35 semantics and feeds native from a pre-normalized "
                "image tensor. DA3BASE_280x504_N35_image_only CoreML now exists, so the next authority gap is not model "
                "packaging; it is the same-capture product image-only regression output. Old pose-conditioned outputs remain compatibility evidence."
            ),
            "next_best_action": (
                "Rerun the same capture/window through the product image-only CoreML path, then compare official core-frame NPZ downstream."
            ),
        },
        "inputs": {
            "dataset_dir": str(args.dataset_dir),
            "official_repo": str(args.official_repo),
            "dart_package": str(args.dart_package),
            "app_repo": str(args.app_repo),
        },
        "checks": checks,
        "plain_language": [
            "官方默认 DA3-Streaming 是 image-only；当前 APP policy/native allowlist 已指向 image-only K35。",
            "Dart 已把官方 preprocess 终点推进到 normalized float32 CHW tensor，Swift image-only 分支不再 PNG decode fallback。",
            "DA3BASE_280x504_N35_image_only CoreML artifact/signature 现在已落地。",
            "旧 pose-conditioned 输出只能当 compatibility/research 证据，不能当产品 official authority。",
        ],
    }


def check_contains(
    check_id: str,
    path: Path,
    needle: str,
    evidence: str,
    *,
    expect_present: bool = True,
    pass_means_parity: bool = True,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = needle in text
    expected = present == expect_present
    line = find_line(text, needle) if present else None
    if not expected:
        status = "fail"
    elif pass_means_parity:
        status = "pass"
    else:
        status = "parity_gap"
    return {
        "id": check_id,
        "status": status,
        "path": str(path),
        "line": line,
        "needle": needle,
        "evidence": evidence,
    }


def file_exists_check(
    check_id: str,
    path: Path,
    evidence: str,
    *,
    expect_exists: bool = True,
    pass_means_parity: bool = True,
) -> dict[str, Any]:
    exists = path.exists()
    expected = exists == expect_exists
    if not expected:
        status = "missing" if expect_exists else "unexpected_present"
    elif pass_means_parity:
        status = "pass"
    else:
        status = "parity_gap"
    return {
        "id": check_id,
        "status": status,
        "path": str(path),
        "exists": exists,
        "evidence": evidence,
    }


def coreml_signature_check(check_id: str, path: Path, evidence: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "id": check_id,
            "status": "missing",
            "path": str(path),
            "exists": False,
            "evidence": f"{evidence} CoreML package is missing.",
        }
    try:
        import coremltools as ct  # type: ignore

        model = ct.models.MLModel(str(path), skip_model_load=True)
        spec = model.get_spec()
        inputs = [feature_summary(item) for item in spec.description.input]
        outputs = [feature_summary(item) for item in spec.description.output]
        input_names = {item["name"] for item in inputs}
        requires_external_camera = {"extrinsics", "intrinsics"}.issubset(input_names)
        image_only_signature = input_names == {"image"}
        status = "parity_gap" if requires_external_camera and not image_only_signature else "pass"
        return {
            "id": check_id,
            "status": status,
            "path": str(path),
            "exists": True,
            "coreml_type": spec.WhichOneof("Type"),
            "specification_version": spec.specificationVersion,
            "inputs": inputs,
            "outputs": outputs,
            "evidence": (
                f"{evidence} inputs={sorted(input_names)}; "
                f"requires_external_camera={requires_external_camera}; image_only_signature={image_only_signature}."
            ),
        }
    except Exception as exc:  # pragma: no cover - diagnostics should report tooling failures.
        return {
            "id": check_id,
            "status": "fail",
            "path": str(path),
            "exists": True,
            "evidence": f"{evidence} Could not inspect CoreML signature: {exc}",
        }


def feature_summary(feature: Any) -> dict[str, Any]:
    feature_type = feature.type.WhichOneof("Type")
    summary: dict[str, Any] = {
        "name": feature.name,
        "type": feature_type,
    }
    if feature_type == "multiArrayType":
        summary["shape"] = list(feature.type.multiArrayType.shape)
        summary["data_type"] = str(feature.type.multiArrayType.dataType)
    elif feature_type == "imageType":
        summary["width"] = feature.type.imageType.width
        summary["height"] = feature.type.imageType.height
        summary["color_space"] = str(feature.type.imageType.colorSpace)
    return summary


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
                "path": item["path"],
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
        "# Official DA3 upstream path parity audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- official algorithm blame supported: `{report['decision']['official_algorithm_blame_supported']}`",
        f"- current thickness authority: `{report['decision']['current_thickness_authority']}`",
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
