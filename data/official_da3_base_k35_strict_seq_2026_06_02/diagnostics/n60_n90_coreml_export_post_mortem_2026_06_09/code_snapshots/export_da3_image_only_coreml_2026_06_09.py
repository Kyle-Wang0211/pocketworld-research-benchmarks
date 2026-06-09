#!/usr/bin/env python3
"""Export or dry-run the official DA3 image-only CoreML wrapper."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def install_chunked_sdpa_for_trace(query_chunk: int = 720, min_gib: float = 2.0) -> None:
    """Chunk SDPA queries so CPU fp32 trace forward stays under macOS jetsam.

    Without this, window_size>=60 makes F.scaled_dot_product_attention materialize a
    (K*token_count)^2 attention matrix in the global cross-frame attention blocks
    (e.g. K=60 -> 12 heads * 43260^2 * 4 bytes = ~90 GB fp32) at trace time, which
    exceeds Mac unified memory and gets SIGKILL'd with no Python exception.

    The chunked variant produces mathematically identical output, just records as
    N_chunks SDPA calls + cat in the trace graph (coremltools handles each
    independently, iPhone CoreML runtime picks fused kernel at execution time).

    Adapted from da3base_official_streaming_oracle.install_mps_chunked_sdpa; device-
    agnostic (works on CPU, MPS, CUDA alike).
    """
    import gc
    import math
    import torch
    import torch.nn.functional as F

    original_sdpa = F.scaled_dot_product_attention
    reported_shapes: set[tuple[int, ...]] = set()

    def chunked_sdpa(query, key, value, attn_mask=None, dropout_p=0.0,
                     is_causal=False, scale=None, enable_gqa=False):
        if dropout_p != 0.0 or is_causal or enable_gqa or query.shape[-2] <= query_chunk:
            return original_sdpa(query, key, value, attn_mask=attn_mask,
                                 dropout_p=dropout_p, is_causal=is_causal,
                                 scale=scale, enable_gqa=enable_gqa)
        batch_heads = 1
        for d in query.shape[:-2]:
            batch_heads *= int(d)
        score_gib = batch_heads * int(query.shape[-2]) * int(key.shape[-2]) \
                    * query.element_size() / (1024**3)
        if score_gib < min_gib:
            return original_sdpa(query, key, value, attn_mask=attn_mask,
                                 dropout_p=dropout_p, is_causal=is_causal,
                                 scale=scale, enable_gqa=enable_gqa)
        shape_key = tuple(int(d) for d in query.shape)
        if shape_key not in reported_shapes:
            print(
                f"[chunked_sdpa] query_shape={shape_key} key_tokens={int(key.shape[-2])} "
                f"score_buffer_gib={score_gib:.2f} query_chunk={query_chunk}",
                flush=True,
            )
            reported_shapes.add(shape_key)
        scale_factor = float(scale) if scale is not None else 1.0 / math.sqrt(query.shape[-1])
        outputs = []
        key_t = key.transpose(-2, -1)
        q_tokens = int(query.shape[-2])
        for start in range(0, q_tokens, query_chunk):
            end = min(start + query_chunk, q_tokens)
            scores = torch.matmul(query[..., start:end, :], key_t) * scale_factor
            if attn_mask is not None:
                mask = attn_mask
                if mask.shape[-2] == q_tokens:
                    mask = mask[..., start:end, :]
                if mask.dtype == torch.bool:
                    scores = scores.masked_fill(~mask, float("-inf"))
                else:
                    scores = scores + mask
            probs = torch.softmax(scores.float(), dim=-1).to(value.dtype)
            outputs.append(torch.matmul(probs, value))
            del scores, probs
            gc.collect()
        return torch.cat(outputs, dim=-2)

    F.scaled_dot_product_attention = chunked_sdpa


def install_da3_dinov2_layers_export_shim() -> None:
    """Restore missing local package exports for official DA3 imports.

    Some local DA3 source copies include all layer modules but have an empty
    depth_anything_3.model.dinov2.layers.__init__. This mirrors the oracle
    runner's runtime-only repair and does not alter DA3 model semantics.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--window-size", type=int, default=35)
    parser.add_argument("--height", type=int, default=280)
    parser.add_argument("--width", type=int, default=504)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--convert", action="store_true")
    parser.add_argument("--compute-precision", choices=["float16", "float32"], default="float16")
    parser.add_argument("--minimum-deployment-target", default="iOS18")
    parser.add_argument(
        "--no-trace-check",
        action="store_true",
        help=(
            "Disable torch.jit.trace check_trace. This is export-only and avoids "
            "an extra full DA3 forward pass for large fixed-window CoreML graphs."
        ),
    )
    parser.add_argument(
        "--trace-optimize-false",
        action="store_true",
        help="Pass optimize=False to torch.jit.trace for large fixed-window export probes.",
    )
    parser.add_argument(
        "--static-shape-export-patches",
        action="store_true",
        help=(
            "Apply export-only static-shape patches for the fixed B=1,K,H,W CoreML graph. "
            "This keeps image-only DA3 semantics but removes PyTorch dynamic shape constructs "
            "that coremltools cannot lower."
        ),
    )
    parser.add_argument("--allow-duplicate-openmp", action="store_true")
    parser.add_argument(
        "--install-chunked-sdpa-for-trace",
        action="store_true",
        help=(
            "Monkey-patch F.scaled_dot_product_attention to a query-chunked variant "
            "before torch.jit.trace runs the CPU fp32 forward. Required for window_size "
            ">= 60 so the global cross-frame attention matrix (K*token_count)^2 doesn't "
            "exceed macOS unified memory and get SIGKILL'd by jetsam mid-trace. "
            "Output is mathematically identical to the math backend."
        ),
    )
    parser.add_argument(
        "--chunked-sdpa-query-chunk",
        type=int,
        default=720,
        help="Query chunk size for --install-chunked-sdpa-for-trace. Default 720 matches one frame's token count for 280x504 input.",
    )
    parser.add_argument(
        "--chunked-sdpa-min-gib",
        type=float,
        default=2.0,
        help="Only chunk SDPA when the estimated attention score buffer exceeds this many GiB. Smaller SDPA calls pass through to the original implementation.",
    )
    parser.add_argument(
        "--trace-device",
        choices=["cpu", "mps"],
        default="cpu",
        help=(
            "Device for torch.jit.trace's eager forward. 'cpu' is the historical default. "
            "'mps' moves net+example to Apple Silicon GPU before trace; MPS SDPA uses a fused "
            "FlashAttention-style kernel (O(seq) memory) and avoids CPU dispatcher OOM for "
            "window_size>=60. The resulting traced graph is device-agnostic and converts to "
            "the same CoreML mlpackage."
        ),
    )
    parser.add_argument("--out-report", type=Path)
    args = parser.parse_args()

    if not args.dry_run and not args.convert:
        parser.error("Specify --dry-run and/or --convert")
    if args.allow_duplicate_openmp:
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    report = run(args)
    if args.out_report is not None:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.out_report, report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    repo_src = args.official_da3_repo / "src"
    sys.path.insert(0, str(repo_src))
    install_da3_dinov2_layers_export_shim()

    import torch
    from depth_anything_3.api import DepthAnything3

    api_model = DepthAnything3.from_pretrained(str(args.model_dir))
    net = api_model.model.eval()
    example = torch.zeros(
        1,
        args.window_size,
        3,
        args.height,
        args.width,
        dtype=torch.float32,
    )
    static_patch_report: dict[str, Any] | None = None
    if args.static_shape_export_patches:
        static_patch_report = apply_static_shape_export_patches(
            net,
            window_size=args.window_size,
            height=args.height,
            width=args.width,
        )
    if args.install_chunked_sdpa_for_trace:
        install_chunked_sdpa_for_trace(
            query_chunk=args.chunked_sdpa_query_chunk,
            min_gib=args.chunked_sdpa_min_gib,
        )
        print(
            f"[export] chunked SDPA installed before trace (query_chunk={args.chunked_sdpa_query_chunk}, "
            f"min_gib={args.chunked_sdpa_min_gib})",
            flush=True,
        )
        if static_patch_report is not None:
            static_patch_report["chunked_sdpa"] = {
                "query_chunk": args.chunked_sdpa_query_chunk,
                "min_gib_threshold": args.chunked_sdpa_min_gib,
            }
    wrapper = DA3ImageOnlyCoreMLWrapper(net).eval()

    if args.trace_device != "cpu":
        import torch
        wrapper.module.to(args.trace_device)
        example = example.to(args.trace_device)
        print(f"[export] trace device moved to {args.trace_device}", flush=True)
        if static_patch_report is not None:
            static_patch_report["trace_device"] = args.trace_device

    report: dict[str, Any] = {
        "schema_version": "aether_da3_image_only_coreml_export_v1",
        "purpose": "Export official DA3-Streaming image-only CoreML wrapper",
        "inputs": {
            "official_da3_repo": str(args.official_da3_repo),
            "model_dir": str(args.model_dir),
            "out_model": str(args.out_model),
            "window_size": args.window_size,
            "height": args.height,
            "width": args.width,
            "dry_run": args.dry_run,
            "convert": args.convert,
            "compute_precision": args.compute_precision,
            "minimum_deployment_target": args.minimum_deployment_target,
            "no_trace_check": args.no_trace_check,
            "trace_optimize_false": args.trace_optimize_false,
            "static_shape_export_patches": args.static_shape_export_patches,
            "allow_duplicate_openmp": args.allow_duplicate_openmp,
        },
        "contract": {
            "coreml_inputs": ["image"],
            "forbidden_coreml_inputs": ["extrinsics", "intrinsics"],
            "torch_semantics": "net(image, None, None, [], False, False, 'saddle_balanced')",
            "outputs": ["depth", "depth_conf", "pred_extrinsics", "pred_intrinsics"],
            "not_identity_camera": True,
        },
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
        },
    }
    if static_patch_report is not None:
        report["static_shape_export_patches"] = static_patch_report

    if args.dry_run:
        dry_started = time.perf_counter()
        with torch.no_grad():
            outputs = wrapper(example)
        report["dry_run"] = {
            "status": "pass",
            "elapsed_s": time.perf_counter() - dry_started,
            "output_shapes": [list(tensor.shape) for tensor in outputs],
            "output_dtypes": [str(tensor.dtype).replace("torch.", "") for tensor in outputs],
            "finite": [bool(torch.isfinite(tensor).all().item()) for tensor in outputs],
        }

    if args.convert:
        report["conversion"] = convert_to_coreml(args, wrapper, example)

    report["elapsed_s"] = time.perf_counter() - started
    return report


class DA3ImageOnlyCoreMLWrapper:
    """Thin PyTorch wrapper with official streaming image-only semantics."""

    def __init__(self, net: Any):
        import torch.nn as nn

        class _Wrapper(nn.Module):
            def __init__(self, inner: Any):
                super().__init__()
                self.inner = inner

            def forward(self, image):  # type: ignore[no-untyped-def]
                output = self.inner(
                    image,
                    None,
                    None,
                    export_feat_layers=[],
                    infer_gs=False,
                    use_ray_pose=False,
                    ref_view_strategy="saddle_balanced",
                )
                depth = output.depth
                if depth.dim() == 5 and depth.shape[-1] == 1:
                    depth = depth.squeeze(-1)
                extrinsics = output.extrinsics
                if extrinsics.dim() == 4 and extrinsics.shape[-2] == 4:
                    extrinsics = extrinsics[:, :, :3, :]
                return depth, output.depth_conf, extrinsics, output.intrinsics

        self.module = _Wrapper(net)

    def eval(self):  # type: ignore[no-untyped-def]
        self.module.eval()
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.module(*args, **kwargs)


def apply_static_shape_export_patches(
    net: Any,
    *,
    window_size: int,
    height: int,
    width: int,
) -> dict[str, Any]:
    """Patch official modules to make a fixed-shape CoreML trace exportable.

    These patches are export-only. They keep the official image-only branch
    (extrinsics=None/intrinsics=None) and replace shape-derived tensors with
    constants for the fixed B=1,K,H,W CoreML resource.
    """

    import types

    import torch
    import torch.nn.functional as F
    from addict import Dict
    from depth_anything_3.model.dinov2.vision_transformer import THRESH_FOR_REF_SELECTION
    from depth_anything_3.model.reference_view_selector import (
        reorder_by_reference,
        restore_original_order,
        select_reference_view,
    )
    from depth_anything_3.model.utils.transform import quat_to_mat
    from depth_anything_3.model.utils.head_utils import (
        create_uv_grid,
        position_grid_to_embed,
    )

    pretrained = net.backbone.pretrained
    head = net.head

    batch_size = 1
    channels = 3
    patch_size = int(pretrained.patch_size)
    patch_h = height // patch_size
    patch_w = width // patch_size
    token_count = 1 + patch_h * patch_w + int(getattr(pretrained, "num_register_tokens", 0))
    patch_token_count = patch_h * patch_w
    embed_dim = int(pretrained.embed_dim)
    num_heads = int(pretrained.num_heads)
    head_dim = embed_dim // num_heads
    rope_feature_dim = head_dim // 2
    flat_batch = batch_size * window_size

    with torch.no_grad():
        patch_tokens = pretrained.patch_embed(
            torch.zeros(flat_batch, channels, height, width, dtype=torch.float32)
        )
        tokens_with_cls = torch.cat(
            (pretrained.prepare_cls_token(batch_size, window_size), patch_tokens),
            dim=1,
        )
        static_pos_embed = pretrained.interpolate_pos_encoding(
            tokens_with_cls, width, height
        ).detach()

        if pretrained.rope is not None:
            pos = pretrained.position_getter(
                flat_batch,
                patch_h,
                patch_w,
                device=torch.device("cpu"),
            ).reshape(batch_size, window_size, -1, 2)
            pos_nodiff = torch.zeros_like(pos).to(pos.dtype)
            if pretrained.patch_start_idx > 0:
                pos = pos + 1
                pos_special = torch.zeros(
                    batch_size,
                    window_size,
                    pretrained.patch_start_idx,
                    2,
                    dtype=pos.dtype,
                )
                pos = torch.cat([pos_special, pos], dim=2)
                pos_nodiff = pos_nodiff + 1
                pos_nodiff = torch.cat([pos_special, pos_nodiff], dim=2)
            max_position = int(torch.maximum(pos.max(), pos_nodiff.max()).item()) + 1
            cos_comp, sin_comp = pretrained.rope._compute_frequency_components(
                rope_feature_dim,
                max_position,
                torch.device("cpu"),
                torch.float32,
            )
        else:
            pos = torch.empty(0, dtype=torch.long)
            pos_nodiff = torch.empty(0, dtype=torch.long)
            max_position = 0
            cos_comp = torch.empty(0, dtype=torch.float32)
            sin_comp = torch.empty(0, dtype=torch.float32)

        ref_token = pretrained.camera_token[:, :1].expand(batch_size, 1, -1)
        src_token = pretrained.camera_token[:, 1:].expand(batch_size, window_size - 1, -1)
        static_cam_token = torch.cat([ref_token, src_token], dim=1).detach()

    pretrained.register_buffer("_export_static_pos_embed", static_pos_embed, persistent=False)
    pretrained.register_buffer("_export_static_rope_pos", pos, persistent=False)
    pretrained.register_buffer("_export_static_rope_pos_nodiff", pos_nodiff, persistent=False)
    pretrained.register_buffer("_export_static_cam_token", static_cam_token, persistent=False)
    if pretrained.rope is not None:
        pretrained.rope.register_buffer("_export_static_cos_comp", cos_comp, persistent=False)
        pretrained.rope.register_buffer("_export_static_sin_comp", sin_comp, persistent=False)

    head_pos_embed_shapes = precompute_head_pos_embeds(
        head,
        height=height,
        width=width,
        patch_h=patch_h,
        patch_w=patch_w,
        flat_batch=flat_batch,
        create_uv_grid=create_uv_grid,
        position_grid_to_embed=position_grid_to_embed,
    )

    def interpolate_pos_encoding_static(self: Any, x: Any, w: int, h: int) -> Any:
        return self._export_static_pos_embed.to(dtype=x.dtype, device=x.device)

    def prepare_rope_static(
        self: Any,
        B: int,
        S: int,
        H: int,
        W: int,
        device: Any,
    ) -> tuple[Any, Any]:
        if self.rope is None:
            return None, None
        return (
            self._export_static_rope_pos.to(device=device),
            self._export_static_rope_pos_nodiff.to(device=device),
        )

    def prepare_tokens_with_masks_static(
        self: Any,
        x: Any,
        masks: Any = None,
        cls_token: Any = None,
        **kwargs: Any,
    ) -> Any:
        x = x.reshape(flat_batch, channels, height, width)
        x = self.patch_embed(x)
        if masks is not None:
            x = torch.where(masks.unsqueeze(-1), self.mask_token.to(x.dtype).unsqueeze(0), x)
        cls_token = self.prepare_cls_token(batch_size, window_size)
        x = torch.cat((cls_token, x), dim=1)
        x = x + self.interpolate_pos_encoding(x, width, height)
        if self.register_tokens is not None:
            x = torch.cat(
                (
                    x[:, :1],
                    self.register_tokens.expand(flat_batch, -1, -1),
                    x[:, 1:],
                ),
                dim=1,
            )
        return x.reshape(batch_size, window_size, token_count, embed_dim)

    def process_attention_static(
        self: Any,
        x: Any,
        block: Any,
        attn_type: str = "global",
        pos: Any = None,
        attn_mask: Any = None,
    ) -> Any:
        if attn_type == "local":
            x = x.reshape(flat_batch, token_count, embed_dim)
            if pos is not None:
                pos = pos.reshape(flat_batch, token_count, 2)
        elif attn_type == "global":
            x = x.reshape(batch_size, window_size * token_count, embed_dim)
            if pos is not None:
                pos = pos.reshape(batch_size, window_size * token_count, 2)
        else:
            raise ValueError(f"Invalid attention type: {attn_type}")
        x = block(x, pos=pos, attn_mask=None)
        return x.reshape(batch_size, window_size, token_count, embed_dim)

    def rope_forward_static(self: Any, tokens: Any, positions: Any) -> Any:
        cos_comp = self._export_static_cos_comp.to(dtype=tokens.dtype, device=tokens.device)
        sin_comp = self._export_static_sin_comp.to(dtype=tokens.dtype, device=tokens.device)
        vertical_features, horizontal_features = tokens.chunk(2, dim=-1)

        def apply_1d(token_features: Any, position_indices: Any) -> Any:
            cos = F.embedding(position_indices, cos_comp)[:, None, :, :]
            sin = F.embedding(position_indices, sin_comp)[:, None, :, :]
            feature_half = rope_feature_dim // 2
            x1 = token_features[..., :feature_half]
            x2 = token_features[..., feature_half:]
            rotated = torch.cat((-x2, x1), dim=-1)
            return (token_features * cos) + (rotated * sin)

        vertical_features = apply_1d(vertical_features, positions[..., 0])
        horizontal_features = apply_1d(horizontal_features, positions[..., 1])
        return torch.cat((vertical_features, horizontal_features), dim=-1)

    def attention_forward_static(self: Any, x: Any, pos: Any = None, attn_mask: Any = None) -> Any:
        if x.shape[1] == token_count:
            current_batch = flat_batch
            current_tokens = token_count
        else:
            current_batch = batch_size
            current_tokens = window_size * token_count
        dim = int(self.qkv.in_features)
        current_head_dim = dim // int(self.num_heads)
        qkv = (
            self.qkv(x)
            .reshape(current_batch, current_tokens, 3, self.num_heads, current_head_dim)
            .permute(2, 0, 3, 1, 4)
        )
        q, k, v = qkv[0], qkv[1], qkv[2]
        q, k = self.q_norm(q), self.k_norm(k)
        if self.rope is not None and pos is not None:
            q = self.rope(q, pos)
            k = self.rope(k, pos)
        if self.fused_attn:
            out = F.scaled_dot_product_attention(
                q,
                k,
                v,
                dropout_p=0.0,
                attn_mask=None,
            )
        else:
            q = q * self.scale
            attn = (q @ k.transpose(-2, -1)).softmax(dim=-1)
            out = attn @ v
        out = out.transpose(1, 2).reshape(current_batch, current_tokens, dim)
        out = self.proj(out)
        return self.proj_drop(out)

    def intermediate_layers_static(
        self: Any,
        x: Any,
        n: Any = 1,
        export_feat_layers: list[int] | None = None,
        **kwargs: Any,
    ) -> tuple[list[Any], list[Any]]:
        if export_feat_layers is None:
            export_feat_layers = []
        x = self.prepare_tokens_with_masks(x)
        output: list[Any] = []
        aux_output: list[Any] = []
        total_block_len = len(self.blocks)
        blocks_to_take = range(total_block_len - n, total_block_len) if isinstance(n, int) else n
        pos, pos_nodiff = self._prepare_rope(batch_size, window_size, height, width, x.device)
        b_idx = None
        local_x = x

        for i, blk in enumerate(self.blocks):
            if i < self.rope_start or self.rope is None:
                g_pos, l_pos = None, None
            else:
                g_pos = pos_nodiff
                l_pos = pos

            if (
                self.alt_start != -1
                and (i == self.alt_start - 1)
                and window_size >= THRESH_FOR_REF_SELECTION
                and kwargs.get("cam_token", None) is None
            ):
                b_idx = select_reference_view(
                    x,
                    strategy=kwargs.get("ref_view_strategy", "saddle_balanced"),
                )
                x = reorder_by_reference(x, b_idx)
                local_x = reorder_by_reference(local_x, b_idx)

            if self.alt_start != -1 and i == self.alt_start:
                cam_token = kwargs.get("cam_token", None)
                if cam_token is None:
                    cam_token = self._export_static_cam_token.to(dtype=x.dtype, device=x.device)
                x = torch.cat([cam_token.unsqueeze(2), x[:, :, 1:]], dim=2)

            if self.alt_start != -1 and i >= self.alt_start and i % 2 == 1:
                x = self.process_attention(x, blk, "global", pos=g_pos, attn_mask=None)
            else:
                x = self.process_attention(x, blk, "local", pos=l_pos)
                local_x = x

            if i in blocks_to_take:
                out_x = torch.cat([local_x, x], dim=-1) if self.cat_token else x
                if b_idx is not None and window_size >= THRESH_FOR_REF_SELECTION and self.alt_start != -1:
                    out_x = restore_original_order(out_x, b_idx)
                output.append((out_x[:, :, 0], out_x))
            if i in export_feat_layers:
                aux_output.append(x)
        return output, aux_output

    def head_add_pos_embed_static(self: Any, x: Any, W: int, H: int, ratio: float = 0.1) -> Any:
        channel_count = int(x.shape[1])
        feature_h = int(x.shape[2])
        feature_w = int(x.shape[3])
        buffer_name = f"_export_pos_embed_{channel_count}_{feature_h}_{feature_w}"
        if not hasattr(self, buffer_name):
            raise RuntimeError(f"Missing static head positional embedding: {buffer_name}")
        pe = getattr(self, buffer_name).to(dtype=x.dtype, device=x.device)
        return x + pe.expand(flat_batch, -1, -1, -1)

    def head_forward_static(
        self: Any,
        feats: list[Any],
        H: int,
        W: int,
        patch_start_idx: int,
        chunk_size: int = 8,
    ) -> Any:
        dim_in = int(self.projects[0].in_channels)
        flat_feats = [feat[0].reshape(flat_batch, patch_token_count, dim_in) for feat in feats]
        out_dict = self._forward_impl(flat_feats, height, width, patch_start_idx)
        main_h = int(patch_h * self.patch_size / self.down_ratio)
        main_w = int(patch_w * self.patch_size / self.down_ratio)
        aux_h = patch_h * 8
        aux_w = patch_w * 8
        aux_dim = int(last_conv2d_out_channels(self.scratch.output_conv2_aux[-1]) - 1)
        return Dict(
            {
                self.head_main: out_dict[self.head_main].reshape(
                    batch_size,
                    window_size,
                    main_h,
                    main_w,
                ),
                f"{self.head_main}_conf": out_dict[f"{self.head_main}_conf"].reshape(
                    batch_size,
                    window_size,
                    main_h,
                    main_w,
                ),
                self.head_aux: out_dict[self.head_aux].reshape(
                    batch_size,
                    window_size,
                    aux_h,
                    aux_w,
                    aux_dim,
                ),
                f"{self.head_aux}_conf": out_dict[f"{self.head_aux}_conf"].reshape(
                    batch_size,
                    window_size,
                    aux_h,
                    aux_w,
                ),
            }
        )

    def head_forward_impl_static(self: Any, feats: list[Any], H: int, W: int, patch_start_idx: int) -> dict[str, Any]:
        ph = patch_h
        pw = patch_w
        dim_in = int(self.projects[0].in_channels)
        resized_feats = []
        for stage_idx, take_idx in enumerate(self.intermediate_layer_idx):
            x = feats[take_idx][:, patch_start_idx:]
            x = self.norm(x)
            x = x.permute(0, 2, 1).reshape(flat_batch, dim_in, ph, pw)
            x = self.projects[stage_idx](x)
            if self.pos_embed:
                x = self._add_pos_embed(x, width, height)
            x = self.resize_layers[stage_idx](x)
            resized_feats.append(x)

        fused_main, fused_aux_pyr = self._fuse(resized_feats)
        main_h = int(ph * self.patch_size / self.down_ratio)
        main_w = int(pw * self.patch_size / self.down_ratio)
        fused_main = F.interpolate(
            fused_main,
            size=(main_h, main_w),
            mode="bilinear",
            align_corners=True,
        )
        if self.pos_embed:
            fused_main = self._add_pos_embed(fused_main, width, height)

        main_logits = self.scratch.output_conv2(fused_main)
        fmap = main_logits.permute(0, 2, 3, 1)
        main_pred = self._apply_activation_single(fmap[..., :-1], self.activation)
        main_conf = self._apply_activation_single(fmap[..., -1], self.conf_activation)

        last_aux = fused_aux_pyr[-1]
        if self.pos_embed:
            last_aux = self._add_pos_embed(last_aux, width, height)
        last_aux_logits = self.scratch.output_conv2_aux[-1](last_aux)
        fmap_last = last_aux_logits.permute(0, 2, 3, 1)
        aux_pred = self._apply_activation_single(fmap_last[..., :-1], "linear")
        aux_conf = self._apply_activation_single(fmap_last[..., -1], self.conf_activation)
        return {
            self.head_main: main_pred.squeeze(-1),
            f"{self.head_main}_conf": main_conf,
            self.head_aux: aux_pred,
            f"{self.head_aux}_conf": aux_conf,
        }

    def camera_decoder_forward_static(
        self: Any,
        feat: Any,
        camera_encoding: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        dim_in = int(self.fc_t.in_features)
        feat = feat.reshape(flat_batch, dim_in)
        feat = self.backbone(feat)
        out_t = self.fc_t(feat.float()).reshape(batch_size, window_size, 3)
        if camera_encoding is None:
            out_qvec = self.fc_qvec(feat.float()).reshape(batch_size, window_size, 4)
            out_fov = self.fc_fov(feat.float()).reshape(batch_size, window_size, 2)
        else:
            out_qvec = camera_encoding[..., 3:7]
            out_fov = camera_encoding[..., -2:]
        return torch.cat([out_t, out_qvec, out_fov], dim=-1)

    def process_camera_estimation_static(
        self: Any,
        feats: list[Any],
        H: int,
        W: int,
        output: Any,
    ) -> Any:
        if self.cam_dec is None:
            return output
        pose_enc = self.cam_dec(feats[-1][1])
        if "ray" in output:
            del output.ray
        if "ray_conf" in output:
            del output.ray_conf

        translation = pose_enc[..., :3]
        quat = pose_enc[..., 3:7]
        fov_h = pose_enc[..., 7]
        fov_w = pose_enc[..., 8]
        rotation = quat_to_mat(quat)
        c2w = torch.cat([rotation, translation[..., None]], dim=-1)

        fy = (height / 2.0) / torch.clamp(torch.tan(fov_h / 2.0), 1e-6)
        fx = (width / 2.0) / torch.clamp(torch.tan(fov_w / 2.0), 1e-6)
        zeros = torch.zeros_like(fx)
        ones = torch.ones_like(fx)
        cx = torch.full_like(fx, width / 2.0)
        cy = torch.full_like(fy, height / 2.0)
        row0 = torch.stack([fx, zeros, cx], dim=-1)
        row1 = torch.stack([zeros, fy, cy], dim=-1)
        row2 = torch.stack([zeros, zeros, ones], dim=-1)

        rotation_t = rotation.transpose(-1, -2)
        translation_inv = -(rotation_t @ translation[..., None])
        output.extrinsics = torch.cat([rotation_t, translation_inv], dim=-1)
        output.intrinsics = torch.stack([row0, row1, row2], dim=-2)
        return output

    pretrained.interpolate_pos_encoding = types.MethodType(interpolate_pos_encoding_static, pretrained)
    pretrained._prepare_rope = types.MethodType(prepare_rope_static, pretrained)
    pretrained.prepare_tokens_with_masks = types.MethodType(prepare_tokens_with_masks_static, pretrained)
    pretrained.process_attention = types.MethodType(process_attention_static, pretrained)
    pretrained._get_intermediate_layers_not_chunked = types.MethodType(intermediate_layers_static, pretrained)
    if pretrained.rope is not None:
        pretrained.rope.forward = types.MethodType(rope_forward_static, pretrained.rope)
    for block in pretrained.blocks:
        block.attn.forward = types.MethodType(attention_forward_static, block.attn)

    head._add_pos_embed = types.MethodType(head_add_pos_embed_static, head)
    head.forward = types.MethodType(head_forward_static, head)
    head._forward_impl = types.MethodType(head_forward_impl_static, head)
    if net.cam_dec is not None:
        net.cam_dec.forward = types.MethodType(camera_decoder_forward_static, net.cam_dec)
    net._process_camera_estimation = types.MethodType(process_camera_estimation_static, net)

    return {
        "status": "applied",
        "scope": "fixed B=1 image-only CoreML export graph",
        "window_size": window_size,
        "height": height,
        "width": width,
        "patch_size": patch_size,
        "patch_grid": [patch_h, patch_w],
        "token_count_with_cls": token_count,
        "patch_token_count": patch_token_count,
        "rope_max_position": max_position,
        "head_pos_embed_shapes": head_pos_embed_shapes,
        "patched_modules": [
            "backbone.prepare_tokens_with_masks",
            "backbone.interpolate_pos_encoding",
            "backbone._prepare_rope",
            "backbone.process_attention",
            "backbone._get_intermediate_layers_not_chunked",
            "backbone.rope.forward",
            "backbone.block.attn.forward",
            "head.forward",
            "head._forward_impl",
            "head._add_pos_embed",
            "cam_dec.forward",
            "net._process_camera_estimation",
        ],
        "semantic_guardrail": (
            "The wrapper still calls official DA3 with extrinsics=None and intrinsics=None; "
            "patches only specialize fixed tensor shapes and precomputed positional encodings."
        ),
    }


def precompute_head_pos_embeds(
    head: Any,
    *,
    height: int,
    width: int,
    patch_h: int,
    patch_w: int,
    flat_batch: int,
    create_uv_grid: Any,
    position_grid_to_embed: Any,
) -> list[list[int]]:
    import torch

    shapes: list[tuple[int, int, int]] = []
    for project in head.projects:
        shapes.append((int(project.out_channels), patch_h, patch_w))

    main_channel_count = int(first_conv2d_in_channels(head.scratch.output_conv2))
    main_h = int(patch_h * head.patch_size / head.down_ratio)
    main_w = int(patch_w * head.patch_size / head.down_ratio)
    shapes.append((main_channel_count, main_h, main_w))

    aux_channel_count = int(first_conv2d_in_channels(head.scratch.output_conv2_aux[-1]))
    shapes.append((aux_channel_count, patch_h * 8, patch_w * 8))

    registered: list[list[int]] = []
    for channel_count, feature_h, feature_w in sorted(set(shapes)):
        pe = create_uv_grid(
            feature_w,
            feature_h,
            aspect_ratio=width / height,
            dtype=torch.float32,
            device=torch.device("cpu"),
        )
        pe = position_grid_to_embed(pe, channel_count) * 0.1
        pe = pe.permute(2, 0, 1)[None].detach()
        buffer_name = f"_export_pos_embed_{channel_count}_{feature_h}_{feature_w}"
        head.register_buffer(buffer_name, pe, persistent=False)
        registered.append([flat_batch, channel_count, feature_h, feature_w])
    return registered


def first_conv2d_in_channels(module: Any) -> int:
    import torch.nn as nn

    if isinstance(module, nn.Conv2d):
        return int(module.in_channels)
    for child in module.modules():
        if isinstance(child, nn.Conv2d):
            return int(child.in_channels)
    raise ValueError(f"No Conv2d found in {type(module).__name__}")


def first_conv2d_out_channels(module: Any) -> int:
    import torch.nn as nn

    if isinstance(module, nn.Conv2d):
        return int(module.out_channels)
    for child in module.modules():
        if isinstance(child, nn.Conv2d):
            return int(child.out_channels)
    raise ValueError(f"No Conv2d found in {type(module).__name__}")


def last_conv2d_out_channels(module: Any) -> int:
    import torch.nn as nn

    last_seen: int | None = None
    if isinstance(module, nn.Conv2d):
        last_seen = int(module.out_channels)
    for child in module.modules():
        if isinstance(child, nn.Conv2d):
            last_seen = int(child.out_channels)
    if last_seen is None:
        raise ValueError(f"No Conv2d found in {type(module).__name__}")
    return last_seen


def convert_to_coreml(args: argparse.Namespace, wrapper: DA3ImageOnlyCoreMLWrapper, example: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        import coremltools as ct
        import torch
    except Exception as exc:  # pragma: no cover
        return {
            "status": "fail",
            "reason": f"{type(exc).__name__}: {exc}",
        }

    try:
        print(
            f"[export] torch.jit.trace begin check_trace={not args.no_trace_check}",
            flush=True,
        )
        trace_kwargs: dict[str, Any] = {}
        if args.trace_optimize_false:
            trace_kwargs["optimize"] = False
        traced = torch.jit.trace(
            wrapper.module,
            example,
            strict=False,
            check_trace=not args.no_trace_check,
            **trace_kwargs,
        )
        print("[export] torch.jit.trace done", flush=True)
        deployment_target = getattr(ct.target, args.minimum_deployment_target)
        precision = ct.precision.FLOAT16 if args.compute_precision == "float16" else ct.precision.FLOAT32
        print("[export] coremltools convert begin", flush=True)
        mlmodel = ct.convert(
            traced,
            inputs=[
                ct.TensorType(
                    name="image",
                    shape=example.shape,
                    dtype=float,
                )
            ],
            outputs=[
                ct.TensorType(name="depth"),
                ct.TensorType(name="depth_conf"),
                ct.TensorType(name="pred_extrinsics"),
                ct.TensorType(name="pred_intrinsics"),
            ],
            convert_to="mlprogram",
            minimum_deployment_target=deployment_target,
            compute_precision=precision,
        )
        print("[export] coremltools convert done", flush=True)
        args.out_model.parent.mkdir(parents=True, exist_ok=True)
        mlmodel.save(str(args.out_model))
        print(f"[export] saved {args.out_model}", flush=True)
    except Exception as exc:
        return {
            "status": "fail",
            "elapsed_s": time.perf_counter() - started,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        "status": "pass",
        "elapsed_s": time.perf_counter() - started,
        "out_model": str(args.out_model),
    }


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "dry_run": report.get("dry_run"),
        "conversion": report.get("conversion"),
        "elapsed_s": report.get("elapsed_s"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
