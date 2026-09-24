#!/usr/bin/env python3
"""Run the official DA3-Streaming pipeline with DA3-BASE on a manifest sequence.

This is an oracle runner for local research diagnostics. It keeps the official
vendor DA3-Streaming source unchanged, but adapts runtime-only pieces that are
CUDA/Triton-specific so the pipeline can run on this Mac:

- keep official Triton dense Sim3 alignment when CUDA+Triton are available;
- inject a Triton alignment stub only on non-Triton local runs, then use the
  official numpy dense Sim3 backend;
- patch CUDA capability probing when CUDA is absent;
- load DA3-BASE weights/config explicitly instead of the vendor default nested
  giant checkpoint;
- preserve manifest order by symlinking frames as 000000.jpg, 000001.jpg, ...

The default algorithmic settings remain the official long-sequence settings:
chunk_size=120, overlap=60, loop closure enabled, dense Sim3 alignment. Product
diagnostics can override only chunk_size/overlap, e.g. K35 uses 35/18.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import types
import importlib.util
from pathlib import Path
from typing import Any

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--vendor-dir", type=Path, required=True)
    parser.add_argument("--da3-src-dir", type=Path, required=True)
    parser.add_argument("--da3-base-snapshot", type=Path, required=True)
    parser.add_argument("--salad-ckpt", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=120)
    parser.add_argument("--overlap", type=int, default=60)
    parser.add_argument("--conf-threshold-coef", type=float, default=0.75)
    parser.add_argument("--sample-ratio", type=float, default=0.015)
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--npz-sample-ratio", type=float, default=0.015)
    parser.add_argument(
        "--mps-chunked-sdpa",
        choices=("auto", "on", "off"),
        default="auto",
        help="Use exact query-chunked SDPA on MPS for large attention matrices.",
    )
    parser.add_argument("--mps-sdpa-query-chunk", type=int, default=256)
    parser.add_argument("--mps-sdpa-min-gib", type=float, default=2.0)
    parser.add_argument(
        "--align-lib",
        choices=("auto", "triton", "numpy", "torch", "numba"),
        default="auto",
        help="Official DA3-Streaming alignment backend. auto keeps triton on CUDA+Triton, otherwise numpy.",
    )
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--force-refresh-input", action="store_true")
    return parser.parse_args()


def install_triton_stub() -> None:
    stub = types.ModuleType("loop_utils.alignment_triton")

    def _stub(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Triton alignment was called, but this oracle config uses align_lib=numpy")

    stub.robust_weighted_estimate_sim3_triton = _stub
    sys.modules["loop_utils.alignment_triton"] = stub


def read_manifest(manifest_path: Path) -> dict[str, Any]:
    with manifest_path.open() as f:
        return json.load(f)


def prepare_ordered_input_dir(capture_dir: Path, manifest: dict[str, Any], input_dir: Path, force: bool) -> list[str]:
    if force and input_dir.exists():
        shutil.rmtree(input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)

    image_paths: list[str] = []
    frames = list(manifest.get("frames") or [])
    for index, frame in enumerate(frames):
        rel = frame["sourceHighresRelativePath"]
        src = capture_dir / rel
        if not src.exists():
            raise FileNotFoundError(src)
        suffix = src.suffix.lower() or ".jpg"
        dst = input_dir / f"{index:06d}{suffix}"
        if dst.exists() or dst.is_symlink():
            if dst.is_symlink() and os.readlink(dst) == str(src):
                pass
            else:
                dst.unlink()
                dst.symlink_to(src)
        else:
            dst.symlink_to(src)
        image_paths.append(str(src))
    return image_paths


def resolve_align_lib(requested: str, cuda_available: bool) -> str:
    has_triton = importlib.util.find_spec("triton") is not None
    if requested == "auto":
        return "triton" if cuda_available and has_triton else "numpy"
    if requested == "triton" and not has_triton:
        raise RuntimeError("--align-lib triton requested, but Python package 'triton' is not importable")
    return requested


def install_mps_chunked_sdpa(torch_module: Any, query_chunk: int, min_gib: float) -> None:
    import torch.nn.functional as F

    original_sdpa = F.scaled_dot_product_attention
    reported_shapes: set[tuple[int, ...]] = set()

    def chunked_sdpa(
        query: Any,
        key: Any,
        value: Any,
        attn_mask: Any = None,
        dropout_p: float = 0.0,
        is_causal: bool = False,
        scale: float | None = None,
        enable_gqa: bool = False,
    ) -> Any:
        if (
            query.device.type != "mps"
            or dropout_p != 0.0
            or is_causal
            or enable_gqa
            or query.shape[-2] <= query_chunk
        ):
            return original_sdpa(
                query,
                key,
                value,
                attn_mask=attn_mask,
                dropout_p=dropout_p,
                is_causal=is_causal,
                scale=scale,
                enable_gqa=enable_gqa,
            )

        batch_heads = 1
        for dim in query.shape[:-2]:
            batch_heads *= int(dim)
        score_gib = (
            batch_heads
            * int(query.shape[-2])
            * int(key.shape[-2])
            * query.element_size()
            / (1024**3)
        )
        if score_gib < min_gib:
            return original_sdpa(
                query,
                key,
                value,
                attn_mask=attn_mask,
                dropout_p=dropout_p,
                is_causal=is_causal,
                scale=scale,
                enable_gqa=enable_gqa,
            )

        shape_key = tuple(int(dim) for dim in query.shape)
        if shape_key not in reported_shapes:
            print(
                "oracle_mps_chunked_sdpa "
                f"query_shape={shape_key} key_tokens={int(key.shape[-2])} "
                f"estimated_score_buffer_gib={score_gib:.2f} query_chunk={query_chunk}",
                flush=True,
            )
            reported_shapes.add(shape_key)

        scale_factor = float(scale) if scale is not None else 1.0 / math.sqrt(query.shape[-1])
        outputs = []
        key_t = key.transpose(-2, -1)
        query_tokens = int(query.shape[-2])
        for start in range(0, query_tokens, query_chunk):
            end = min(start + query_chunk, query_tokens)
            scores = torch_module.matmul(query[..., start:end, :], key_t) * scale_factor
            if attn_mask is not None:
                mask = attn_mask
                if mask.shape[-2] == query_tokens:
                    mask = mask[..., start:end, :]
                if mask.dtype == torch_module.bool:
                    scores = scores.masked_fill(~mask, float("-inf"))
                else:
                    scores = scores + mask
            probs = torch_module.softmax(scores.float(), dim=-1).to(value.dtype)
            outputs.append(torch_module.matmul(probs, value))
            del scores, probs
        return torch_module.cat(outputs, dim=-2)

    F.scaled_dot_product_attention = chunked_sdpa


def load_effective_config(args: argparse.Namespace, align_lib: str) -> dict[str, Any]:
    config_path = args.vendor_dir / "configs" / "base_config.yaml"
    with config_path.open() as f:
        config = yaml.safe_load(f)

    model_path = args.da3_base_snapshot / "model.safetensors"
    da3_config_path = args.da3_base_snapshot / "config.json"
    if not model_path.exists():
        raise FileNotFoundError(model_path)
    if not da3_config_path.exists():
        raise FileNotFoundError(da3_config_path)
    if not args.salad_ckpt.exists():
        raise FileNotFoundError(args.salad_ckpt)

    config["Weights"]["DA3"] = str(model_path)
    config["Weights"]["DA3_CONFIG"] = str(da3_config_path)
    config["Weights"]["SALAD"] = str(args.salad_ckpt)

    model_cfg = config["Model"]
    model_cfg["chunk_size"] = args.chunk_size
    model_cfg["overlap"] = args.overlap
    model_cfg["loop_enable"] = True
    model_cfg["align_lib"] = align_lib
    model_cfg["align_method"] = "sim3"
    model_cfg["align_type"] = "dense"
    model_cfg["save_depth_conf_result"] = True
    model_cfg["save_debug_info"] = False
    model_cfg["Pointcloud_Save"]["conf_threshold_coef"] = args.conf_threshold_coef
    model_cfg["Pointcloud_Save"]["sample_ratio"] = args.sample_ratio
    return config


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    input_dir = args.input_dir or (args.output_dir / "input_manifest_ordered_414")

    manifest = read_manifest(args.manifest)
    image_paths = prepare_ordered_input_dir(
        args.capture_dir,
        manifest,
        input_dir,
        force=args.force_refresh_input,
    )

    sys.path.insert(0, str(args.vendor_dir))
    sys.path.insert(0, str(args.da3_src_dir))

    import torch

    if not torch.cuda.is_available():
        torch.cuda.get_device_capability = lambda *_args, **_kwargs: (0, 0)  # type: ignore[assignment]

    use_mps_chunked_sdpa = args.mps_chunked_sdpa == "on" or (
        args.mps_chunked_sdpa == "auto"
        and not torch.cuda.is_available()
        and torch.backends.mps.is_available()
    )
    if use_mps_chunked_sdpa:
        install_mps_chunked_sdpa(torch, args.mps_sdpa_query_chunk, args.mps_sdpa_min_gib)

    align_lib = resolve_align_lib(args.align_lib, torch.cuda.is_available())
    if align_lib != "triton" and importlib.util.find_spec("triton") is None:
        install_triton_stub()

    effective_config = load_effective_config(args, align_lib)
    with (args.output_dir / "effective_config.yaml").open("w") as f:
        yaml.safe_dump(effective_config, f, sort_keys=False)
    with (args.output_dir / "ordered_input_manifest.json").open("w") as f:
        json.dump(
            {
                "sourceManifest": str(args.manifest),
                "frameCount": len(image_paths),
                "inputDir": str(input_dir),
                "sourceHighresPaths": image_paths,
            },
            f,
            indent=2,
        )

    original_torch_load = torch.load

    def torch_load_cpu(*load_args: Any, **load_kwargs: Any) -> Any:
        load_kwargs.setdefault("map_location", "cpu")
        load_kwargs.setdefault("weights_only", False)
        return original_torch_load(*load_args, **load_kwargs)

    torch.load = torch_load_cpu  # type: ignore[assignment]

    from da3_streaming import DA3_Streaming
    from loop_utils.sim3utils import merge_ply_files
    from npz_output_process import create_point_cloud

    print("oracle_frame_count", len(image_paths), flush=True)
    print("oracle_input_dir", input_dir, flush=True)
    print("oracle_output_dir", args.output_dir, flush=True)
    print("oracle_da3_base_snapshot", args.da3_base_snapshot, flush=True)
    print("oracle_salad_ckpt", args.salad_ckpt, flush=True)
    print("oracle_align_lib", effective_config["Model"]["align_lib"], flush=True)

    runner = DA3_Streaming(str(input_dir), str(args.output_dir), effective_config)
    preferred_device = (
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )
    runner.device = preferred_device
    runner.model = runner.model.to(preferred_device)
    print("oracle_da3_device", preferred_device, flush=True)

    runner.run()
    runner.close()
    del runner

    all_ply_path = args.output_dir / "pcd" / "combined_pcd.ply"
    merge_ply_files(str(args.output_dir / "pcd"), str(all_ply_path))
    print("oracle_combined_ply", all_ply_path, flush=True)

    unique_npz_ply_path = args.output_dir / "pcd" / "unique_frame_npz_fusion.ply"
    create_point_cloud(
        npz_folder=str(args.output_dir / "results_output"),
        pose_file=str(args.output_dir / "camera_poses.txt"),
        output_ply=str(unique_npz_ply_path),
        conf_threshold_coef=args.npz_conf_threshold_coef,
        sample_ratio=args.npz_sample_ratio,
    )
    print("oracle_unique_frame_npz_fusion_ply", unique_npz_ply_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
