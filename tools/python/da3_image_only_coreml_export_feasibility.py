#!/usr/bin/env python3
"""Document feasibility and exact contract for exporting image-only DA3 CoreML."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--current-coreml", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_only_coreml_export_feasibility.json", report)
    write_markdown(
        args.out_dir / "official_da3_image_only_coreml_export_feasibility_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    config = read_json(args.model_dir / "config.json")
    current_signature = inspect_coreml_signature(args.current_coreml)
    official_sources = official_source_evidence(args.official_da3_repo)
    env = python_env()
    export_scripts = discover_export_scripts(args.official_da3_repo)
    decision = derive_decision(config, current_signature, env, export_scripts)
    return {
        "schema_version": "aether_official_da3_image_only_coreml_export_feasibility_v1",
        "date": args.date,
        "purpose": (
            "Define the exact image-only CoreML wrapper needed to match official "
            "DA3-Streaming before mobile-specific tuning."
        ),
        "inputs": {
            "official_da3_repo": str(args.official_da3_repo),
            "model_dir": str(args.model_dir),
            "current_coreml": str(args.current_coreml),
        },
        "official_source_evidence": official_sources,
        "model_config_evidence": {
            "model_name": config.get("model_name"),
            "has_cam_enc": bool(config.get("config", {}).get("cam_enc")),
            "has_cam_dec": bool(config.get("config", {}).get("cam_dec")),
            "backbone_name": config.get("config", {}).get("net", {}).get("name"),
            "alt_start": config.get("config", {}).get("net", {}).get("alt_start"),
            "out_layers": config.get("config", {}).get("net", {}).get("out_layers"),
        },
        "current_coreml_signature": current_signature,
        "environment": env,
        "official_export_scripts_found": export_scripts,
        "required_image_only_wrapper": required_wrapper_contract(),
        "decision": decision,
        "next_commands": next_commands(args),
    }


def official_source_evidence(repo: Path) -> dict[str, Any]:
    api = repo / "src/depth_anything_3/api.py"
    da3 = repo / "src/depth_anything_3/model/da3.py"
    vit = repo / "src/depth_anything_3/model/dinov2/vision_transformer.py"
    streaming = repo / "da3_streaming/da3_streaming.py"
    return {
        "api_inference_flow": {
            "path": str(api),
            "lines": [
                "195-210 preprocess -> prepare -> normalize optional extrinsics -> _run_model_forward",
                "341-365 align only when input extrinsics are present",
            ],
        },
        "da3_forward_contract": {
            "path": str(da3),
            "lines": [
                "100-109 forward(x, extrinsics=None, intrinsics=None, ...)",
                "126-130 if extrinsics is None, cam_token=None",
                "211-226 cam_dec predicts pose encoding, then outputs extrinsics/intrinsics",
                "336-365 DepthAnything3Metric forwards optional cameras through anyview branch",
            ],
        },
        "reference_view_selection": {
            "path": str(vit),
            "lines": [
                "314-330 image-only path selects reference view and uses learned camera tokens",
                "323-326 pose-conditioned path uses user-provided camera condition tokens",
            ],
        },
        "streaming_entry": {
            "path": str(streaming),
            "lines": [
                "253-274 DA3-Streaming calls model.inference(images, ref_view_strategy=...)",
                "880-915 CLI accepts image_dir/config/output_dir, not camera files",
            ],
        },
    }


def required_wrapper_contract() -> dict[str, Any]:
    return {
        "coreml_inputs": [
            {
                "name": "image",
                "shape": [1, 35, 3, 476, 742],
                "dtype": "float32",
                "preprocess": "already ImageNet-normalized RGB CHW tensor",
            }
        ],
        "forbidden_coreml_inputs": ["extrinsics", "intrinsics"],
        "torch_call_semantics": {
            "call": (
                "da3_model(image, extrinsics=None, intrinsics=None, "
                "export_feat_layers=[], infer_gs=False, use_ray_pose=False, "
                "ref_view_strategy='saddle_balanced')"
            ),
            "must_not_do": [
                "do not feed identity extrinsics",
                "do not feed ARKit/VIO extrinsics",
                "do not feed ARKit intrinsics",
            ],
        },
        "coreml_outputs": [
            {"name": "depth", "shape": [1, 35, 476, 742]},
            {"name": "depth_conf", "shape": [1, 35, 476, 742]},
            {"name": "pred_extrinsics", "shape": [1, 35, 3, 4]},
            {"name": "pred_intrinsics", "shape": [1, 35, 3, 3]},
        ],
        "post_export_acceptance": [
            "coreml signature required_inputs exactly ['image']",
            "readiness gate passes",
            "Mac exporter model_input_contract reports image_only",
            "same-window CoreML image-only output is compared against PyTorch image-only reference",
        ],
    }


def derive_decision(
    config: dict[str, Any],
    current_signature: dict[str, Any],
    env: dict[str, Any],
    export_scripts: list[str],
) -> dict[str, Any]:
    has_cam_dec = bool(config.get("config", {}).get("cam_dec"))
    has_cam_enc = bool(config.get("config", {}).get("cam_enc"))
    coremltools_available = bool(env.get("coremltools_available"))
    torch_warning = bool(env.get("torch_coremltools_warning"))
    official_export_script_found = bool(export_scripts)
    current_is_pose = bool(current_signature.get("is_pose_conditioned_coreml_signature"))
    return {
        "status": "ready_to_attempt_export" if coremltools_available else "blocked_no_coremltools",
        "image_only_wrapper_contract_known": has_cam_dec and has_cam_enc,
        "current_coreml_is_pose_conditioned": current_is_pose,
        "official_repo_contains_coreml_export_script": official_export_script_found,
        "local_coremltools_available": coremltools_available,
        "torch_coremltools_version_mismatch_warning": torch_warning,
        "full_k35_coreml_conversion_attempted": False,
        "highest_priority_action": (
            "write_or_recover_the_original_coreml_export_wrapper_for_image_only_da3"
        ),
        "why_not_identity_camera": (
            "Identity extrinsics would still create a camera-conditioned token path; "
            "official streaming default requires extrinsics=None so the backbone uses "
            "learned camera tokens and cam_dec predicts poses from image features."
        ),
    }


def python_env() -> dict[str, Any]:
    env: dict[str, Any] = {"python": sys.version.split()[0]}
    try:
        import torch

        env["torch_available"] = True
        env["torch_version"] = torch.__version__
    except Exception as exc:  # pragma: no cover
        env["torch_available"] = False
        env["torch_error"] = f"{type(exc).__name__}: {exc}"

    try:
        import coremltools as ct

        env["coremltools_available"] = True
        env["coremltools_version"] = ct.__version__
    except Exception as exc:  # pragma: no cover
        env["coremltools_available"] = False
        env["coremltools_error"] = f"{type(exc).__name__}: {exc}"

    torch_version = str(env.get("torch_version") or "")
    env["torch_coremltools_warning"] = bool(
        env.get("coremltools_available") and torch_version.startswith("2.12")
    )
    return env


def discover_export_scripts(repo: Path) -> list[str]:
    hits: list[str] = []
    for path in repo.rglob("*"):
        if path.is_dir() or path.suffix.lower() not in {".py", ".sh", ".md"}:
            continue
        name = path.name.lower()
        if "coreml" in name or "export" in name or "convert" in name:
            if "__pycache__" not in path.parts:
                hits.append(str(path))
    return sorted(hits)


def inspect_coreml_signature(model_path: Path) -> dict[str, Any]:
    if not model_path.exists():
        return {"model_path": str(model_path), "available": False}
    try:
        with tempfile.TemporaryDirectory(prefix="da3_coreml_feasibility_") as tmp:
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
    except Exception as exc:  # pragma: no cover
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
    return {
        "model_path": str(model_path),
        "available": True,
        "input_names": input_names,
        "output_names": output_names,
        "required_inputs": required_inputs,
        "is_pose_conditioned_coreml_signature": (
            {"image", "extrinsics", "intrinsics"}.issubset(set(required_inputs))
        ),
        "is_image_only_signature": required_inputs == ["image"],
    }


def next_commands(args: argparse.Namespace) -> list[str]:
    out_model = (
        args.current_coreml.parent / "DA3BASE_476x742_N35_image_only.mlpackage"
    )
    readiness_out = (
        "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/"
        "official_da3_image_only_coreml_readiness_gate_2026_06_04"
    )
    return [
        "# implement export wrapper, then convert to CoreML",
        f"# expected output: {out_model}",
        (
            "python3.11 tools/python/da3_image_only_coreml_readiness_gate.py "
            "--app-repo /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter "
            "--capture-services-dir /Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services "
            f"--out-dir {readiness_out} --date 2026-06-04"
        ),
        (
            "python3.11 tools/python/da3_mac_window_export.py "
            "--capture-dir data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict "
            "--out-dir data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_image_only_probe "
            f"--model {out_model} --compute-unit cpu --max-windows 1"
        ),
    ]


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    env = report["environment"]
    lines = [
        "# Official DA3 image-only CoreML export feasibility",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        "image-only CoreML 的语义已经明确，但当前仓库没有官方提供的 CoreML export 脚本，也还没有真正执行 full K35 CoreML conversion。",
        "",
        "要贴官方 DA3-Streaming，CoreML wrapper 必须只暴露 `image` 输入；`extrinsics/intrinsics` 不能作为输入，也不能用 identity camera 替代。DA3 会通过模型内部 `cam_dec` 从多视图图像特征预测 `pred_extrinsics/pred_intrinsics`。",
        "",
        "## Decision",
        "",
    ]
    for key, value in decision.items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Required Wrapper",
            "",
            f"- `coreml_inputs`: `{report['required_image_only_wrapper']['coreml_inputs']}`",
            f"- `forbidden_coreml_inputs`: `{report['required_image_only_wrapper']['forbidden_coreml_inputs']}`",
            f"- `torch_call`: `{report['required_image_only_wrapper']['torch_call_semantics']['call']}`",
            f"- `must_not_do`: `{report['required_image_only_wrapper']['torch_call_semantics']['must_not_do']}`",
            f"- `coreml_outputs`: `{report['required_image_only_wrapper']['coreml_outputs']}`",
            "",
            "## Model Config Evidence",
            "",
        ]
    )
    for key, value in report["model_config_evidence"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Current CoreML Signature",
            "",
        ]
    )
    for key, value in report["current_coreml_signature"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Environment",
            "",
        ]
    )
    for key, value in env.items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Official Source Evidence",
            "",
        ]
    )
    for group, evidence in report["official_source_evidence"].items():
        lines.append(f"### {group}")
        lines.append("")
        lines.append(f"- `path`: `{evidence['path']}`")
        for row in evidence["lines"]:
            lines.append(f"- `{row}`")
        lines.append("")

    lines.extend(
        [
            "## Official Export Scripts Found",
            "",
        ]
    )
    if report["official_export_scripts_found"]:
        for row in report["official_export_scripts_found"]:
            lines.append(f"- `{row}`")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Next Commands",
            "",
        ]
    )
    for row in report["next_commands"]:
        lines.append(f"```bash\n{row}\n```")

    lines.extend(
        [
            "",
            "## 大白话",
            "",
            "DA3 不靠 AR 也能有位姿，是因为它把位姿估计做进神经网络了：image-only 分支先从图像抽多视图特征，再由 camera decoder 回归位姿和内参。",
            "",
            "所以 image-only CoreML 不是少输出 pose，而是少输入 pose。输出里的 `pred_extrinsics/pred_intrinsics` 仍然必须保留。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "model_config": report["model_config_evidence"],
        "environment": report["environment"],
    }


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
