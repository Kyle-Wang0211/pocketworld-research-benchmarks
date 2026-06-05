#!/usr/bin/env python3
"""Audit the official DA3 image-only geometry path.

The goal is to keep the current research question narrow:
DA3BASE_476x742_N35 is fixed, AR/VIO is not an official DA3 input, and the
remaining question is whether official image-only upstream geometry reduces the
single-window K35 same-surface thick layer.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


ISSUE_254_API = "https://api.github.com/repos/ByteDance-Seed/Depth-Anything-3/issues/254"
ISSUE_254_URL = "https://github.com/ByteDance-Seed/Depth-Anything-3/issues/254"
OFFICIAL_REPO_URL = "https://github.com/ByteDance-Seed/Depth-Anything-3"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--app-repo", type=Path, required=True)
    parser.add_argument("--research-data-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_only_geometry_path_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_image_only_geometry_path_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official = inspect_official_repo(args.official_da3_repo)
    current = inspect_current_project(args)
    external = inspect_external_state()
    decision = derive_decision(official, current, external)
    return {
        "schema_version": "aether_official_da3_image_only_geometry_path_audit_v1",
        "date": args.date,
        "purpose": (
            "Explain where official DA3 image-only camera geometry comes from and "
            "where single-window K35 overlap thickness can or cannot be removed."
        ),
        "fixed_target": {
            "model": "DA3-BASE",
            "resource": "DA3BASE_476x742_N35_image_only",
            "window_size": 35,
            "height": 476,
            "width": 742,
            "dimension_sweep": "disabled",
            "official_camera_input": "image_only",
        },
        "official_evidence": official,
        "current_project_state": current,
        "external_state": external,
        "decision": decision,
        "source_links": {
            "official_repo": OFFICIAL_REPO_URL,
            "issue_254": ISSUE_254_URL,
        },
    }


def inspect_official_repo(repo: Path) -> dict[str, Any]:
    api_py = repo / "src/depth_anything_3/api.py"
    da3_py = repo / "src/depth_anything_3/model/da3.py"
    cam_dec_py = repo / "src/depth_anything_3/model/cam_dec.py"
    vit_py = repo / "src/depth_anything_3/model/dinov2/vision_transformer.py"
    transform_py = repo / "src/depth_anything_3/model/utils/transform.py"
    streaming_py = repo / "da3_streaming/da3_streaming.py"
    npz_py = repo / "da3_streaming/npz_output_process.py"
    readme = repo / "README.md"
    api_md = repo / "docs/API.md"
    ref_md = repo / "docs/funcs/ref_view_strategy.md"

    return {
        "repo": str(repo),
        "license_and_commercial": {
            "da3_base_license": source_hit(readme, "DA3-BASE"),
            "da3_large_license": source_hit(readme, "DA3-LARGE-1.1"),
            "apache_license_file": str(repo / "LICENSE"),
            "interpretation": (
                "For commercial APP work, DA3-BASE/DA3-SMALL are the safe main-series "
                "choices shown as Apache 2.0; DA3-LARGE/DA3-LARGE-1.1 are CC BY-NC 4.0."
            ),
        },
        "official_image_only_entry": {
            "streaming_inference_call": source_hit(
                streaming_py,
                "predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)",
            ),
            "api_example_no_camera": source_hit(api_md, 'prediction = model.inference(["image1.jpg", "image2.jpg"])'),
            "readme_with_or_without_pose": source_hit(readme, "with or without known camera poses"),
            "meaning": (
                "DA3-Streaming default feeds image paths only. It receives predicted "
                "depth, confidence, extrinsics, and intrinsics from DA3 itself."
            ),
        },
        "camera_generation_path": {
            "optional_camera_api": source_hit(api_py, "extrinsics: np.ndarray | None = None"),
            "normalize_only_if_camera_provided": source_hit(api_py, "if ex_t is None:"),
            "align_returns_prediction_when_no_input_camera": source_hit(api_py, "if extrinsics is None:"),
            "cam_enc_only_when_extrinsics_present": source_hit(da3_py, "if extrinsics is not None:"),
            "backbone_receives_cam_token": source_hit(da3_py, "x, cam_token=cam_token"),
            "camera_decoder_call": source_hit(da3_py, "pose_enc = self.cam_dec(feats[-1][1])"),
            "pose_encoding_conversion": source_hit(da3_py, "pose_encoding_to_extri_intri(pose_enc, (H, W))"),
            "cam_dec_translation_rotation_fov": [
                source_hit(cam_dec_py, "self.fc_t = nn.Linear(output_dim, 3)"),
                source_hit(cam_dec_py, "self.fc_qvec = nn.Linear(output_dim, 4)"),
                source_hit(cam_dec_py, "self.fc_fov = nn.Sequential(nn.Linear(output_dim, 2), nn.ReLU())"),
            ],
            "pose_encoding_to_intrinsics": source_hit(transform_py, "intrinsics[..., 0, 0] = fx"),
            "meaning": (
                "Without AR/VIO/input poses, the network predicts translation, rotation, "
                "and FOV from multi-view features through cam_dec, then converts them "
                "to OpenCV-style w2c extrinsics and intrinsics."
            ),
        },
        "reference_view_and_view_order": {
            "automatic_reference_selection_doc": source_hit(ref_md, "automatic reference view selection"),
            "select_reference_view": source_hit(vit_py, "b_idx = select_reference_view(x, strategy=strategy)"),
            "learned_camera_tokens_when_no_cam_token": source_hit(
                vit_py,
                "ref_token = self.camera_token[:, :1].expand(B, -1, -1)",
            ),
            "restore_original_order": source_hit(vit_py, "out_x = restore_original_order(out_x, b_idx)"),
            "meaning": (
                "The image-only world frame is model-defined. It can reorder views around "
                "a selected reference internally, then restores output order."
            ),
        },
        "downstream_overlap_handling": {
            "save_depth_conf_result": source_hit(streaming_py, "self.save_depth_conf_result(predictions, chunk_idx + 1, s, R, t)"),
            "npz_conf_threshold": source_hit(npz_py, "conf_threshold = np.mean(confs_combined) * conf_threshold_coef"),
            "npz_sampling": source_hit(npz_py, "sample_ratio = args.sample_ratio"),
            "full_chunk_pcd_save": source_hit(streaming_py, "save_confident_pointcloud_batch("),
            "meaning": (
                "Official downstream thresholds and samples points and aligns chunks, but "
                "does not contain an intra-window surface fusion/deduplication step."
            ),
        },
    }


def inspect_current_project(args: argparse.Namespace) -> dict[str, Any]:
    app_model_dir = args.app_repo / "ios/Runner/Models/DA3-BASE-CoreML"
    model_names = sorted(path.name for path in app_model_dir.glob("*.mlpackage"))
    readiness = read_latest_json(
        args.research_data_dir / "diagnostics",
        "official_da3_image_only_coreml_readiness_gate.json",
    )
    overlap_gate = read_latest_json(
        args.research_data_dir / "diagnostics",
        "official_da3_image_only_overlap_regression_gate.json",
    )
    thickness = read_latest_json(
        args.research_data_dir / "diagnostics",
        "official_da3_overlap_vs_window_thickness_attribution.json",
    )
    return {
        "app_model_dir": str(app_model_dir),
        "app_coreml_packages": model_names,
        "has_target_image_only_package": "DA3BASE_476x742_N35_image_only.mlpackage" in model_names,
        "readiness_gate_decision": readiness.get("decision"),
        "overlap_regression_gate_decision": overlap_gate.get("decision"),
        "overlap_thickness_findings": thickness.get("findings"),
    }


def inspect_external_state() -> dict[str, Any]:
    issue = fetch_json(ISSUE_254_API)
    if not issue:
        return {
            "issue_254": {
                "url": ISSUE_254_URL,
                "status": "unavailable",
            }
        }
    return {
        "issue_254": {
            "url": issue.get("html_url") or ISSUE_254_URL,
            "number": issue.get("number"),
            "state": issue.get("state"),
            "title": issue.get("title"),
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "comments": issue.get("comments"),
        }
    }


def derive_decision(
    official: dict[str, Any],
    current: dict[str, Any],
    external: dict[str, Any],
) -> dict[str, Any]:
    has_target = bool(current["has_target_image_only_package"])
    overlap_gate = current.get("overlap_regression_gate_decision") or {}
    return {
        "official_pose_source": "network_cam_dec_from_images_not_arkit_vio",
        "official_default_pose_mode": "camera_decoder_use_ray_pose_false",
        "where_single_window_thickness_can_be_reduced": "upstream_depth_pose_scale_consistency",
        "where_single_window_thickness_is_not_removed": "npz_downstream_threshold_sampling",
        "cross_window_duplicate_policy": "core_frame_npz_path_reduces_overlap_frame_duplicates",
        "current_blocker": (
            "missing_DA3BASE_476x742_N35_image_only_coreml_and_outputs"
            if not has_target
            else overlap_gate.get("status", "run_overlap_regression_gate")
        ),
        "commercial_model_choice": "DA3-BASE",
        "external_issue_status": (external.get("issue_254") or {}).get("state"),
        "no_official_forum_fix_found": (external.get("issue_254") or {}).get("comments") == 0,
        "do_next": [
            "Export or obtain DA3BASE_476x742_N35_image_only.mlpackage.",
            "Run da3_mac_window_export.py against the same capture/window_016 with the image-only package.",
            "Rerun da3_image_only_overlap_regression_gate.py; judge PCA minor first35/first10 against old _pose.",
            "Only after that result, decide whether remaining cleanup is official parity or product adaptation.",
        ],
    }


def source_hit(path: Path, needle: str) -> dict[str, Any]:
    text = read_text(path)
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        if needle in line:
            return {
                "path": str(path),
                "line": index,
                "needle": needle,
                "text": line.strip(),
            }
    return {
        "path": str(path),
        "line": None,
        "needle": needle,
        "text": None,
    }


def read_latest_json(root: Path, filename: str) -> dict[str, Any]:
    paths = sorted(root.glob(f"**/{filename}"), key=lambda path: path.stat().st_mtime)
    if not paths:
        return {}
    return read_json(paths[-1])


def fetch_json(url: str) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "aether-research-audit"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except Exception:
        return {}


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "fixed_target": report["fixed_target"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    official = report["official_evidence"]
    current = report["current_project_state"]
    external = report["external_state"]
    decision = report["decision"]
    fixed = report["fixed_target"]
    lines = [
        "# Official DA3 image-only geometry path audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        "- 官方 DA3-Streaming 默认路径是 image-only：不喂 AR/VIO，不喂外部 `extrinsics/intrinsics`。",
        "- image-only 位姿来自 DA3 网络内部的 camera decoder：多视角特征 -> `cam_dec` -> 平移/旋转/FOV -> `pred_extrinsics/pred_intrinsics`。",
        "- 官方 downstream 的 npz/pointcloud 路径做置信度阈值、采样、chunk 对齐和 core-frame 保存；没有看到单个 K35 window 内同表面点云融合/去重步骤。",
        "- 因此，单 window 厚层如果被官方复刻消掉，应该主要来自上游 image-only depth/pose/scale 一致性，而不是 downstream 隐藏清理。",
        f"- 当前阻塞：`{decision['current_blocker']}`。",
        "",
        "## 固定目标",
        "",
        f"- model: `{fixed['model']}`",
        f"- resource: `{fixed['resource']}`",
        f"- shape: `{fixed['window_size']} x {fixed['height']} x {fixed['width']}`",
        f"- dimension sweep: `{fixed['dimension_sweep']}`",
        f"- official camera input: `{fixed['official_camera_input']}`",
        "",
        "## 官方代码证据",
        "",
        "### Image-only entry",
        "",
        hit_line(official["official_image_only_entry"]["streaming_inference_call"]),
        hit_line(official["official_image_only_entry"]["api_example_no_camera"]),
        hit_line(official["official_image_only_entry"]["readme_with_or_without_pose"]),
        "",
        "### Camera generation",
        "",
        hit_line(official["camera_generation_path"]["cam_enc_only_when_extrinsics_present"]),
        hit_line(official["camera_generation_path"]["camera_decoder_call"]),
        hit_line(official["camera_generation_path"]["pose_encoding_conversion"]),
        *[hit_line(row) for row in official["camera_generation_path"]["cam_dec_translation_rotation_fov"]],
        hit_line(official["camera_generation_path"]["pose_encoding_to_intrinsics"]),
        "",
        "### Reference view",
        "",
        hit_line(official["reference_view_and_view_order"]["automatic_reference_selection_doc"]),
        hit_line(official["reference_view_and_view_order"]["select_reference_view"]),
        hit_line(official["reference_view_and_view_order"]["learned_camera_tokens_when_no_cam_token"]),
        "",
        "### Downstream",
        "",
        hit_line(official["downstream_overlap_handling"]["npz_conf_threshold"]),
        hit_line(official["downstream_overlap_handling"]["npz_sampling"]),
        hit_line(official["downstream_overlap_handling"]["full_chunk_pcd_save"]),
        "",
        "## 商用约束",
        "",
        "- DA3-BASE 在官方 model card 表里是 `Apache 2.0`；DA3-LARGE/DA3-LARGE-1.1 是 `CC BY-NC 4.0`。",
        "- 所以 APP 商用 baseline 继续锁 `DA3-BASE` 是合理的；不要为了质量直接换 Large，除非拿到额外授权。",
        hit_line(official["license_and_commercial"]["da3_base_license"]),
        hit_line(official["license_and_commercial"]["da3_large_license"]),
        "",
        "## 当前项目状态",
        "",
        f"- APP CoreML packages: `{', '.join(current['app_coreml_packages'])}`",
        f"- has target image-only package: `{current['has_target_image_only_package']}`",
        f"- readiness gate: `{json.dumps(current.get('readiness_gate_decision'), ensure_ascii=False)}`",
        f"- overlap regression gate: `{json.dumps(current.get('overlap_regression_gate_decision'), ensure_ascii=False)}`",
        f"- prior overlap/thickness finding: `{json.dumps(current.get('overlap_thickness_findings'), ensure_ascii=False)}`",
        "",
        "## 外部状态",
        "",
        f"- official repo: {OFFICIAL_REPO_URL}",
        f"- issue #254: {ISSUE_254_URL}",
        f"- issue #254 state: `{(external.get('issue_254') or {}).get('state')}`",
        f"- issue #254 comments: `{(external.get('issue_254') or {}).get('comments')}`",
        "",
        "## 下一步",
        "",
    ]
    for index, item in enumerate(decision["do_next"], start=1):
        lines.append(f"{index}. {item}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def hit_line(hit: dict[str, Any]) -> str:
    line = hit.get("line")
    text = hit.get("text")
    path = hit.get("path")
    if line is None:
        return f"- `{path}`: missing `{hit.get('needle')}`"
    return f"- `{path}:{line}`: `{text}`"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
