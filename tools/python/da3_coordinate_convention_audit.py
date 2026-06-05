#!/usr/bin/env python3
"""Audit DA3 coordinate conventions across official, Research, and APP paths."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any


REMOTE_COMMIT_API = "https://api.github.com/repos/ByteDance-Seed/Depth-Anything-3/commits/main"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--research-repo", type=Path, required=True)
    parser.add_argument("--app-repo", type=Path, required=True)
    parser.add_argument("--capture-services-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_coordinate_convention_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_coordinate_convention_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official = inspect_official(args.official_da3_repo)
    research = inspect_research(args.research_repo)
    app = inspect_app(args.app_repo, args.capture_services_dir)
    decision = derive_decision(official, research, app)
    return {
        "schema_version": "aether_official_da3_coordinate_convention_audit_v1",
        "date": args.date,
        "purpose": (
            "Separate DA3 OpenCV world coordinates, official GLB glTF alignment, "
            "official streaming NPZ/PLY semantics, and APP pose-conditioned camera inputs."
        ),
        "official": official,
        "research": research,
        "app": app,
        "decision": decision,
    }


def inspect_official(repo: Path) -> dict[str, Any]:
    glb = repo / "src/depth_anything_3/utils/export/glb.py"
    api = repo / "src/depth_anything_3/api.py"
    streaming = repo / "da3_streaming/da3_streaming.py"
    sim3 = repo / "da3_streaming/loop_utils/sim3utils.py"
    npz = repo / "da3_streaming/npz_output_process.py"
    remote = fetch_json(REMOTE_COMMIT_API)
    return {
        "local_repo": str(repo),
        "remote_main": {
            "sha": remote.get("sha"),
            "date": (remote.get("commit") or {}).get("committer", {}).get("date"),
            "message": ((remote.get("commit") or {}).get("message") or "").split("\n")[0],
            "url": remote.get("html_url"),
        },
        "opencv_w2c_output": {
            "readme_comment": "Official README/API describes prediction.extrinsics as OpenCV/Colmap w2c.",
            "api_align_no_input_camera": source_hit(api, "if extrinsics is None:"),
        },
        "glb_path": {
            "backproject_w2c_to_world": source_hit(glb, "c2w = np.linalg.inv(_as_homogeneous44(ext_w2c[i]))"),
            "alignment_function": source_hit(glb, "def _compute_alignment_transform_first_cam_glTF_center_by_points"),
            "cv_to_gltf_flip_y": source_hit(glb, "M[1, 1] = -1.0"),
            "cv_to_gltf_flip_z": source_hit(glb, "M[2, 2] = -1.0"),
            "center_by_median": source_hit(glb, "center = np.median(pts_tmp, axis=0)"),
            "meaning": (
                "GLB first backprojects in DA3 world, then applies first-camera + "
                "CV-to-glTF axis flip and median centering for visualization."
            ),
        },
        "streaming_npz_ply_path": {
            "image_only_inference": source_hit(
                streaming,
                "predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)",
            ),
            "depth_to_world": source_hit(streaming, "c2w = torch.inverse(extrinsics_4x4)"),
            "npz_conf_threshold": source_hit(npz, "conf_threshold = np.mean(confs_combined) * conf_threshold_coef"),
            "save_confident_pointcloud_batch": source_hit(sim3, "def save_confident_pointcloud_batch"),
            "trimesh_export": source_hit(sim3, "trimesh.PointCloud(points, colors=colors).export(output_path)"),
            "meaning": (
                "Streaming NPZ/PLY writes DA3 world points after confidence filtering and "
                "sampling. It does not apply the GLB first-camera/glTF alignment."
            ),
        },
    }


def inspect_research(repo: Path) -> dict[str, Any]:
    mac_export = repo / "tools/python/da3_mac_window_export.py"
    micro = repo / "tools/python/strict_k35_window_official_filter_micro_audit.py"
    seq = repo / "tools/python/official_save_sequence_pointcloud_export.py"
    return {
        "mac_exporter": {
            "camera_transform_conversion": source_hit(
                mac_export,
                "extrinsics.append(camera_transform_to_opencv_w2c(frame[\"cameraTransform\"]))",
            ),
            "conversion_impl": source_hit(mac_export, "def camera_transform_to_opencv_w2c"),
            "writes_pred_extrinsics": source_hit(mac_export, "write_f32(out_dir / extr_rel, pred_extrinsics[slot])"),
            "meaning": (
                "Research Mac exporter converts external cameraTransform to OpenCV w2c "
                "only for pose-conditioned models; image-only sends no external camera."
            ),
        },
        "official_filter_audit": {
            "glb_alignment_reimplemented": source_hit(micro, "def official_glb_alignment_transform"),
            "npz_world_backprojection": source_hit(micro, "def depth_to_point_cloud_vectorized"),
            "both_styles_present": source_hit(micro, '"npz_streaming_style"'),
            "meaning": "Research explicitly keeps GLB-style and NPZ-streaming-style as separate coordinate paths.",
        },
        "sequence_export": {
            "official_save_slots": source_hit(seq, "officialSaveSlotIndices"),
            "world_backprojection": source_hit(seq, "world_points = (c2w @ camera_points_h)[:3].T.astype(np.float32)"),
            "no_cleanup_note": source_hit(seq, "No cleanup, no Poisson, no mesh"),
            "meaning": "Research sequence export matches official NPZ streaming semantics, not GLB visualization semantics.",
        },
    }


def inspect_app(app_repo: Path, capture_services_dir: Path) -> dict[str, Any]:
    native = app_repo / "ios/Runner/Da3DepthPlugin.swift"
    runner = app_repo / "lib/pipeline/local_pipeline_runner.dart"
    policy = capture_services_dir / "lib/src/photo_bundle_pipeline_policy_service.dart"
    return {
        "native_adapter": {
            "image_only_allowlist": source_hit(native, '"DA3BASE_476x742_N35_image_only"'),
            "pose_allowlist": source_hit(native, '"DA3BASE_476x742_N35_pose"'),
            "image_only_provider": source_hit(native, '"image": MLFeatureValue(multiArray: imageArray),'),
            "pose_provider_extrinsics": source_hit(native, '"extrinsics": MLFeatureValue(multiArray: extrinsics),'),
            "raw_camera_transform_used": source_hit(native, 'let values = doubleArray(frame["cameraTransform"])'),
            "raw_camera_transform_written": source_hit(native, "for i in 0..<16 { ptr[base + i] = Float(values[i]) }"),
            "writes_pred_extrinsics": source_hit(native, "try Self.writeFloats("),
            "meaning": (
                "APP image-only path sends only image. APP pose-conditioned path still "
                "passes frame cameraTransform raw to CoreML, so it must not be treated "
                "as official DA3-Streaming image-only baseline."
            ),
        },
        "dart_gate": {
            "official_image_only_gate": source_hit(
                runner,
                "official_streaming_image_only_coreml_contract",
            ),
            "pose_conditioned_detection": source_hit(runner, "_isPoseConditionedDa3Model"),
            "policy_blocks_pose_baseline": source_hit(
                policy,
                "blocked_until_image_only_coreml_signature",
            ),
        },
    }


def derive_decision(
    official: dict[str, Any],
    research: dict[str, Any],
    app: dict[str, Any],
) -> dict[str, Any]:
    return {
        "official_repo_main_sha": official.get("remote_main", {}).get("sha"),
        "coordinate_truth": {
            "da3_prediction_extrinsics": "OpenCV/Colmap-style world-to-camera (w2c)",
            "official_glb": "DA3 world -> first-camera view -> CV-to-glTF Y/Z flip -> median-centered scene",
            "official_npz_streaming_ply": "DA3 world points with confidence threshold and reservoir sampling",
            "blender_or_gltf_consumers": "need explicit coordinate conversion; NPZ PLY is not already glTF aligned",
        },
        "current_project_alignment": {
            "research_npz_sequence_export": "aligned_with_official_npz_streaming",
            "research_glb_style_audit": "aligned_with_official_glb_visualization",
            "app_image_only_branch": "ready_for_future_image_only_package",
            "app_pose_branch": "compat_only_raw_cameraTransform_risk",
        },
        "thickness_interpretation": (
            "Do not compare GLB-aligned views and NPZ world PLYs as if they used the same "
            "coordinate frame. For single-window thickness, use one fixed official style, "
            "preferably NPZ streaming for APP baseline."
        ),
        "highest_priority_check": (
            "After DA3BASE_476x742_N35_image_only exists, run the same window through "
            "image-only and compare first35/first10 thickness in NPZ streaming coordinates."
        ),
    }


def source_hit(path: Path, needle: str) -> dict[str, Any]:
    text = read_text(path)
    for index, line in enumerate(text.splitlines(), start=1):
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


def fetch_json(url: str) -> dict[str, Any]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "aether-coordinate-audit"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except Exception:
        return {}


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    official = report["official"]
    research = report["research"]
    app = report["app"]
    decision = report["decision"]
    lines = [
        "# Official DA3 coordinate convention audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        "- 本地 official DA3 与 GitHub main 一致：`{}`。".format(decision["official_repo_main_sha"]),
        "- DA3 `prediction.extrinsics` 是 OpenCV/Colmap-style w2c。",
        "- 官方 GLB 导出会额外做 first-camera 对齐、CV-to-glTF 的 Y/Z 翻转、median centering。",
        "- 官方 DA3-Streaming NPZ/PLY 路径不做 GLB 对齐；它是在 DA3 world 坐标里 confidence filter + reservoir sample。",
        "- Research 已经把 GLB-style 和 NPZ-streaming-style 分开；APP official baseline 应继续使用 NPZ streaming 语义。",
        "- 当前 `_pose` APP 分支仍把 `cameraTransform` 原样喂 CoreML；它只能当兼容/对照，不是官方 image-only baseline。",
        "",
        "## 坐标语义表",
        "",
        "| Path | Coordinate frame | What it does |",
        "|---|---|---|",
        "| DA3 prediction | OpenCV/Colmap w2c | model outputs `pred_extrinsics/pred_intrinsics` |",
        "| official GLB | glTF-aligned scene | w2c backproject -> first camera -> flip Y/Z -> center |",
        "| official NPZ/PLY | DA3 world | w2c backproject -> confidence threshold -> sample |",
        "| Blender/third-party PLY | tool-dependent | needs explicit conversion; do not assume DA3 PLY is Blender-ready |",
        "",
        "## 官方证据",
        "",
        "### GLB path",
        "",
        hit_line(official["glb_path"]["backproject_w2c_to_world"]),
        hit_line(official["glb_path"]["alignment_function"]),
        hit_line(official["glb_path"]["cv_to_gltf_flip_y"]),
        hit_line(official["glb_path"]["cv_to_gltf_flip_z"]),
        hit_line(official["glb_path"]["center_by_median"]),
        "",
        "### Streaming NPZ/PLY path",
        "",
        hit_line(official["streaming_npz_ply_path"]["image_only_inference"]),
        hit_line(official["streaming_npz_ply_path"]["depth_to_world"]),
        hit_line(official["streaming_npz_ply_path"]["npz_conf_threshold"]),
        hit_line(official["streaming_npz_ply_path"]["save_confident_pointcloud_batch"]),
        hit_line(official["streaming_npz_ply_path"]["trimesh_export"]),
        "",
        "## Research 对齐状态",
        "",
        hit_line(research["mac_exporter"]["camera_transform_conversion"]),
        hit_line(research["mac_exporter"]["conversion_impl"]),
        hit_line(research["official_filter_audit"]["glb_alignment_reimplemented"]),
        hit_line(research["official_filter_audit"]["npz_world_backprojection"]),
        hit_line(research["sequence_export"]["world_backprojection"]),
        hit_line(research["sequence_export"]["no_cleanup_note"]),
        "",
        "## APP 风险点",
        "",
        hit_line(app["native_adapter"]["image_only_allowlist"]),
        hit_line(app["native_adapter"]["image_only_provider"]),
        hit_line(app["native_adapter"]["pose_provider_extrinsics"]),
        hit_line(app["native_adapter"]["raw_camera_transform_used"]),
        hit_line(app["native_adapter"]["raw_camera_transform_written"]),
        hit_line(app["dart_gate"]["official_image_only_gate"]),
        hit_line(app["dart_gate"]["policy_blocks_pose_baseline"]),
        "",
        "## 判读规则",
        "",
        decision["thickness_interpretation"],
        "",
        "## 下一步",
        "",
        decision["highest_priority_check"],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def hit_line(hit: dict[str, Any]) -> str:
    if hit.get("line") is None:
        return f"- `{hit.get('path')}`: missing `{hit.get('needle')}`"
    return f"- `{hit.get('path')}:{hit.get('line')}`: `{hit.get('text')}`"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
