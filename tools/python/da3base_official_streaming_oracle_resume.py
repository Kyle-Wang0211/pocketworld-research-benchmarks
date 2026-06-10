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
    parser.add_argument(
        "--clamp-last-chunk",
        action="store_true",
        help=(
            "Clamp the last chunk's start back so it spans a full chunk_size "
            "window (start = len - chunk_size), matching iPhone CoreML static-"
            "shape chunking. Official code lets the last chunk be shorter; a "
            "static-shape mlpackage cannot."
        ),
    )
    parser.add_argument(
        "--loop-process-res",
        type=int,
        default=None,
        help=(
            "process_res for on-the-fly loop-chunk inference. Must match the "
            "resolution of cached chunks (e.g. 392 → 224x392) or Sim3 loop "
            "alignment hits a shape mismatch against official default 504."
        ),
    )
    return parser.parse_args()


def install_triton_stub() -> None:
    stub = types.ModuleType("loop_utils.alignment_triton")

    def _stub(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Triton alignment was called, but this oracle config uses align_lib=numpy")

    stub.robust_weighted_estimate_sim3_triton = _stub
    sys.modules["loop_utils.alignment_triton"] = stub


def install_da3_dinov2_layers_export_shim() -> None:
    """Repair incomplete local DA3 source checkouts whose layers package is empty.

    Some local copies have all official submodules present but an empty
    depth_anything_3.model.dinov2.layers.__init__, which breaks official imports
    like ``from .layers import LayerScale``. This only restores package exports;
    it does not change model, streaming, alignment, or fusion behavior.
    """

    import importlib

    layers_pkg = importlib.import_module("depth_anything_3.model.dinov2.layers")
    exports = {
        "Attention": "depth_anything_3.model.dinov2.layers.attention",
        "Block": "depth_anything_3.model.dinov2.layers.block",
        "DropPath": "depth_anything_3.model.dinov2.layers.drop_path",
        "LayerScale": "depth_anything_3.model.dinov2.layers.layer_scale",
        "Mlp": "depth_anything_3.model.dinov2.layers.mlp",
        "PatchEmbed": "depth_anything_3.model.dinov2.layers.patch_embed",
        "PositionGetter": "depth_anything_3.model.dinov2.layers.rope",
        "RotaryPositionEmbedding2D": "depth_anything_3.model.dinov2.layers.rope",
        "SwiGLUFFN": "depth_anything_3.model.dinov2.layers.swiglu_ffn",
        "SwiGLUFFNFused": "depth_anything_3.model.dinov2.layers.swiglu_ffn",
    }
    for name, module_name in exports.items():
        if not hasattr(layers_pkg, name):
            module = importlib.import_module(module_name)
            setattr(layers_pkg, name, getattr(module, name))


def install_loop_detector_numpy_search_shim() -> None:
    """Use an exact NumPy IP search when local FAISS crashes on macOS.

    This preserves DA3-Streaming SALAD semantics: same descriptors, same
    inner-product nearest-neighbor objective, same top_k, threshold, NMS, and
    output format. Only the exact-search backend changes from FAISS C++ to
    NumPy to avoid a local SIGSEGV after descriptor extraction.
    """

    import numpy as np
    from loop_utils.loop_detector import LoopDetector

    def find_loop_closures_numpy(self: Any) -> list[tuple[int, int, float]]:
        if self.descriptors is None:
            self.extract_descriptors()

        descriptors = self.descriptors.detach().cpu().numpy().astype(np.float32, copy=False)
        similarities_all = descriptors @ descriptors.T
        n = similarities_all.shape[0]
        k_count = min(self.top_k + 1, n)

        candidate_indices = np.argpartition(-similarities_all, kth=k_count - 1, axis=1)[
            :, :k_count
        ]
        candidate_sims = np.take_along_axis(similarities_all, candidate_indices, axis=1)
        order = np.argsort(-candidate_sims, axis=1)
        indices = np.take_along_axis(candidate_indices, order, axis=1)
        similarities = np.take_along_axis(candidate_sims, order, axis=1)

        loop_closures = []
        for i in range(n):
            for j in range(1, k_count):
                neighbor_idx = int(indices[i, j])
                similarity = float(similarities[i, j])
                if similarity > self.similarity_threshold and abs(i - neighbor_idx) > 10:
                    if i < neighbor_idx:
                        loop_closures.append((i, neighbor_idx, similarity))
                    else:
                        loop_closures.append((neighbor_idx, i, similarity))

        loop_closures = list(set(loop_closures))
        loop_closures.sort(key=lambda x: x[2], reverse=True)

        if self.use_nms and self.nms_threshold > 0:
            loop_closures = self._apply_nms_filter(loop_closures, self.nms_threshold)

        self.loop_closures = self._ensure_decending_order(loop_closures)
        return self.loop_closures

    LoopDetector.find_loop_closures = find_loop_closures_numpy  # type: ignore[method-assign]
    print("[resume] LoopDetector.find_loop_closures patched to NumPy exact IP search", flush=True)


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
    install_da3_dinov2_layers_export_shim()

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
    install_loop_detector_numpy_search_shim()

    import numpy as _np_for_resume
    _original_process_single_chunk = DA3_Streaming.process_single_chunk

    def _resume_process_single_chunk(self, range_1, chunk_idx=None, range_2=None, is_loop=False):
        if not is_loop and chunk_idx is not None and range_2 is None:
            cached = os.path.join(self.result_unaligned_dir, f"chunk_{chunk_idx}.npy")
            if os.path.exists(cached):
                print(f"[resume] load cached chunk_{chunk_idx} from {cached}", flush=True)
                predictions = _np_for_resume.load(cached, allow_pickle=True).item()
                chunk_range = self.chunk_indices[chunk_idx]
                self.all_camera_poses.append((chunk_range, predictions.extrinsics))
                self.all_camera_intrinsics.append((chunk_range, predictions.intrinsics))
                return predictions
        return _original_process_single_chunk(self, range_1, chunk_idx=chunk_idx, range_2=range_2, is_loop=is_loop)

    DA3_Streaming.process_single_chunk = _resume_process_single_chunk
    print("[resume] DA3_Streaming.process_single_chunk patched to load cached unaligned chunks", flush=True)

    if args.loop_process_res is not None:
        from depth_anything_3.api import DepthAnything3 as _DA3Api

        _original_inference = _DA3Api.inference

        def _res_pinned_inference(self, *a, **kw):
            kw.setdefault("process_res", args.loop_process_res)
            return _original_inference(self, *a, **kw)

        _DA3Api.inference = _res_pinned_inference
        print(
            f"[resume] DepthAnything3.inference pinned to process_res={args.loop_process_res}",
            flush=True,
        )

    if args.clamp_last_chunk:
        _original_get_chunk_indices = DA3_Streaming.get_chunk_indices

        def _clamped_get_chunk_indices(self):
            chunk_indices, num_chunks = _original_get_chunk_indices(self)
            if len(chunk_indices) >= 2:
                last_start, last_end = chunk_indices[-1]
                if (last_end - last_start) < self.chunk_size and last_end >= self.chunk_size:
                    chunk_indices[-1] = (last_end - self.chunk_size, last_end)
                    print(
                        f"[resume] clamped last chunk to {chunk_indices[-1]} "
                        f"(static K={self.chunk_size} window, matches iPhone chunking)",
                        flush=True,
                    )
            return chunk_indices, num_chunks

        DA3_Streaming.get_chunk_indices = _clamped_get_chunk_indices
        print("[resume] DA3_Streaming.get_chunk_indices patched with last-chunk clamp", flush=True)

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
