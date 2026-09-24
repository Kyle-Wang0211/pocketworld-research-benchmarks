#!/usr/bin/env python3
"""Convert APP/Research depth_index outputs into official npz_output_process.py inputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


DEFAULT_OFFICIAL_REPO = Path(
    "/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument(
        "--depth-index",
        type=Path,
        required=True,
        help="Path to APP/Research stages/depth/depth_index.json",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--official-repo", type=Path, default=DEFAULT_OFFICIAL_REPO)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--run-official", action="store_true")
    parser.add_argument("--conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--sample-ratio", type=float, default=0.015)
    parser.add_argument(
        "--confidence-contract",
        choices=["auto", "raw_api", "streaming_npz"],
        default="auto",
        help=(
            "Source confidencePath contract. raw_api applies DA3-Streaming's "
            "`prediction.conf -= 1.0` while materializing frame_*.npz; "
            "streaming_npz writes confidence as-is. auto treats min>=0.9 as raw_api."
        ),
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = materialize_official_inputs(args)
        if args.run_official:
            report["official_run"] = run_official_npz_output_process(args, report)
    except Exception as exc:
        report = failure_report(args, exc)
    write_json(args.out_dir / "official_npz_oracle_bridge_report.json", report)
    write_markdown(args.out_dir / "official_npz_oracle_bridge_report_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    if report["status"].startswith("failed"):
        return 2
    return 0 if report.get("official_run", {}).get("returncode", 0) == 0 else 2


def materialize_official_inputs(args: argparse.Namespace) -> dict[str, Any]:
    depth_index = read_json(args.depth_index)
    depth_dir = args.depth_index.parent
    npz_dir = args.out_dir / "results_output"
    npz_dir.mkdir(parents=True, exist_ok=True)

    frames = [
        frame
        for frame in maps(depth_index.get("frames"))
        if str(frame.get("status", "completed")) == "completed"
    ]
    frames.sort(key=lambda item: int(item.get("frameIndex", item.get("frame_index", 0))))

    pose_lines: list[str] = []
    frame_reports: list[dict[str, Any]] = []
    seen_indices: set[int] = set()
    for ordinal, frame in enumerate(frames):
        frame_index = int(frame.get("frameIndex", frame.get("frame_index", ordinal)))
        if frame_index in seen_indices:
            raise ValueError(f"duplicate frameIndex for official frame_*.npz: {frame_index}")
        seen_indices.add(frame_index)

        width = required_int(frame, "depthWidth")
        height = required_int(frame, "depthHeight")
        image_path = resolve_existing(
            args.capture_dir,
            required_str(frame, "imageRelativePath"),
            alternate_suffixes=[".png", ".jpg", ".jpeg"],
        )
        depth_path = resolve(depth_dir, required_str(frame, "relativeDepthPath"))
        conf_path = resolve(depth_dir, required_str(frame, "confidencePath"))
        extrinsics_path = resolve(depth_dir, required_str(frame, "predExtrinsicsPath"))
        intrinsics_path = resolve(depth_dir, required_str(frame, "predIntrinsicsPath"))

        image = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.uint8)
        if image.shape[:2] != (height, width):
            raise ValueError(
                f"image/depth shape mismatch for {frame.get('frameID')}: "
                f"image={image.shape[1]}x{image.shape[0]}, depth={width}x{height}"
            )
        depth = np.fromfile(depth_path, dtype="<f4").reshape(height, width)
        raw_conf = np.fromfile(conf_path, dtype="<f4").reshape(height, width)
        conf, conf_contract = to_streaming_npz_conf(raw_conf, args.confidence_contract)
        intrinsics = np.fromfile(intrinsics_path, dtype="<f4").reshape(3, 3)
        extrinsics = np.fromfile(extrinsics_path, dtype="<f4").reshape(3, 4)

        npz_path = npz_dir / f"frame_{frame_index}.npz"
        np.savez_compressed(
            npz_path,
            image=image,
            depth=depth,
            conf=conf,
            intrinsics=intrinsics,
        )

        c2w = c2w_from_w2c(extrinsics)
        sim3 = sim3_from_frame(frame)
        if sim3 is not None:
            c2w = apply_official_c2w_sim3(c2w, sim3)
        pose_lines.append(" ".join(str(float(value)) for value in c2w.reshape(-1)))
        frame_reports.append(
            {
                "frameID": frame.get("frameID") or frame.get("id"),
                "frameIndex": frame_index,
                "npz": str(npz_path),
                "image": str(image_path),
                "depth": str(depth_path),
                "confidence": str(conf_path),
                "confidence_contract": conf_contract,
                "intrinsics": str(intrinsics_path),
                "extrinsics_w2c": str(extrinsics_path),
                "windowToRootSim3Applied": sim3 is not None,
            }
        )

    pose_file = args.out_dir / "camera_poses.txt"
    pose_file.write_text("\n".join(pose_lines) + ("\n" if pose_lines else ""), encoding="utf-8")
    output_ply = args.out_dir / "official_npz_output_process.ply"
    official_script = args.official_repo / "da3_streaming/npz_output_process.py"
    command = [
        args.python,
        str(official_script),
        "--npz_folder",
        str(npz_dir),
        "--pose_file",
        str(pose_file),
        "--output_file",
        str(output_ply),
        "--conf_threshold_coef",
        str(args.conf_threshold_coef),
        "--sample_ratio",
        str(args.sample_ratio),
    ]
    return {
        "schema_version": "aether_da3_depth_index_official_npz_oracle_bridge_v1",
        "status": "materialized_official_python_oracle_inputs",
        "official_authority": "Depth-Anything-3/da3_streaming/npz_output_process.py",
        "note": "This bridge only creates official frame_*.npz + camera_poses.txt inputs; it does not reimplement point-cloud filtering.",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "depth_index": str(args.depth_index),
        },
        "outputs": {
            "npz_folder": str(npz_dir),
            "pose_file": str(pose_file),
            "output_ply": str(output_ply),
        },
        "official_command": command,
        "frame_count": len(frame_reports),
        "frames": frame_reports,
    }


def run_official_npz_output_process(args: argparse.Namespace, report: dict[str, Any]) -> dict[str, Any]:
    command = [str(item) for item in report["official_command"]]
    proc = subprocess.run(
        command,
        cwd=str(args.official_repo / "da3_streaming"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "command": command,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def failure_report(args: argparse.Namespace, exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": "aether_da3_depth_index_official_npz_oracle_bridge_v1",
        "status": "failed_to_materialize_official_python_oracle_inputs",
        "official_authority": "Depth-Anything-3/da3_streaming/npz_output_process.py",
        "note": "Failure is reported rather than repaired by resizing or reimplementing official point-cloud filtering.",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "depth_index": str(args.depth_index),
        },
        "outputs": {
            "npz_folder": str(args.out_dir / "results_output"),
            "pose_file": str(args.out_dir / "camera_poses.txt"),
            "output_ply": str(args.out_dir / "official_npz_output_process.ply"),
        },
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback_tail": traceback.format_exc()[-4000:],
        },
    }


def c2w_from_w2c(extrinsics: np.ndarray) -> np.ndarray:
    w2c = np.eye(4, dtype=np.float64)
    w2c[:3, :] = extrinsics.astype(np.float64)
    return np.linalg.inv(w2c)


def to_streaming_npz_conf(conf: np.ndarray, contract: str) -> tuple[np.ndarray, str]:
    if contract == "streaming_npz":
        return conf.astype(np.float32, copy=False), "streaming_npz_as_is"
    if contract == "raw_api" or (contract == "auto" and float(np.nanmin(conf)) >= 0.9):
        return (conf - np.float32(1.0)).astype(np.float32, copy=False), "raw_api_minus_one"
    return conf.astype(np.float32, copy=False), "auto_detected_streaming_npz_as_is"


def apply_official_c2w_sim3(c2w: np.ndarray, sim3: dict[str, np.ndarray | float]) -> np.ndarray:
    scale = float(sim3["scale"])
    rotation = np.asarray(sim3["rotation"], dtype=np.float64).reshape(3, 3)
    translation = np.asarray(sim3["translation"], dtype=np.float64).reshape(3)
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = scale * rotation
    transform[:3, 3] = translation
    out = transform @ c2w
    out[:3, :3] /= scale
    return out


def sim3_from_frame(frame: dict[str, Any]) -> dict[str, np.ndarray | float] | None:
    raw = frame.get("windowToRootSim3")
    if not isinstance(raw, dict) or not raw:
        return None
    scale = raw.get("scale", raw.get("sim3_scale", raw.get("s")))
    rotation = first_list(raw, ["rotation", "sim3_rotation", "R"])
    translation = first_list(raw, ["translation", "sim3_translation", "T", "t"])
    if scale is None or len(rotation) != 9 or len(translation) != 3:
        raise ValueError("windowToRootSim3 must expose scale/rotation[9]/translation[3]")
    return {
        "scale": float(scale),
        "rotation": np.asarray(rotation, dtype=np.float64).reshape(3, 3),
        "translation": np.asarray(translation, dtype=np.float64).reshape(3),
    }


def first_list(raw: dict[str, Any], keys: list[str]) -> list[float]:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, list):
            return [float(item) for item in value]
    return []


def maps(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def resolve(base: Path, path: str) -> Path:
    out = Path(path)
    return out if out.is_absolute() else base / out


def resolve_existing(base: Path, path: str, alternate_suffixes: list[str]) -> Path:
    resolved = resolve(base, path)
    if resolved.exists():
        return resolved
    for suffix in alternate_suffixes:
        candidate = resolved.with_suffix(suffix)
        if candidate.exists():
            return candidate
    return resolved


def required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing {key} in depth_index frame")
    return value


def required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"missing {key} in depth_index frame")
    return int(value)


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "status": report["status"],
        "frame_count": report.get("frame_count"),
        "outputs": report["outputs"],
        "official_run_returncode": report.get("official_run", {}).get("returncode"),
        "error": report.get("error"),
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official NPZ oracle bridge",
        "",
        f"- status: `{report['status']}`",
        f"- official authority: `{report['official_authority']}`",
        f"- frame count: `{report.get('frame_count', 'n/a')}`",
        f"- npz folder: `{report['outputs']['npz_folder']}`",
        f"- pose file: `{report['outputs']['pose_file']}`",
        f"- output ply: `{report['outputs']['output_ply']}`",
        "",
        "这个脚本只生成官方 Python 的输入，不重写点云过滤算法。",
    ]
    if "official_command" in report:
        lines.extend(
            [
                "",
                "## Official command",
                "",
                "```bash",
                " ".join(str(item) for item in report["official_command"]),
                "```",
            ]
        )
    if "error" in report:
        lines.extend(
            [
                "",
                "## Error",
                "",
                f"- type: `{report['error']['type']}`",
                f"- message: {report['error']['message']}",
            ]
        )
    if "official_run" in report:
        lines.extend(
            [
                "",
                "## Official run",
                "",
                f"- returncode: `{report['official_run']['returncode']}`",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
