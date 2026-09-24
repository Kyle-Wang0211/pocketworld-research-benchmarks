#!/usr/bin/env python3
"""
Export DA3-LARGE-1.1 pose-conditioned CoreML experiments.

This is the first high-tier experiment that preserves the official DA3 camera
conditioning inputs:

  image      [1, K, 3, H, W]
  extrinsics [1, K, 4, 4]   raw OpenCV/COLMAP-style w2c, meters
  intrinsics [1, K, 3, 3]   pixels at the model input resolution

The wrapper normalizes extrinsics exactly like the official API before calling
DepthAnything3Net.forward(..., extrinsics, intrinsics). It also returns the
model-predicted extrinsics/intrinsics required for official Umeyama alignment
outside CoreML.
"""

from __future__ import annotations

import argparse
import gc
import math
import os
import sys
import time
import types
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

REPO_ROOT = Path(__file__).resolve().parents[2]
DA3_SRC = Path("/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3/src")
MODEL_PATH = REPO_ROOT / "pocketworld_flutter/ios/Runner/Models/DA3-LARGE-1.1"
OUT_DIR = REPO_ROOT / "pocketworld_flutter/ios/Runner/Models/DA3-LARGE-1.1-CoreML"

sys.path.insert(0, str(DA3_SRC))

# Existing DA3 export experiments needed this compatibility patch for graph
# exporters that dislike torch.cartesian_prod lowering.
_orig_cartesian_prod = torch.cartesian_prod


def _cartesian_prod_compat(*tensors):
    if len(tensors) != 2:
        return _orig_cartesian_prod(*tensors)
    y, x = tensors
    h, w = y.shape[0], x.shape[0]
    return torch.stack(
        [
            y.view(h, 1).expand(h, w).reshape(-1),
            x.view(1, w).expand(h, w).reshape(-1),
        ],
        dim=1,
    )


torch.cartesian_prod = _cartesian_prod_compat


_orig_interpolate = torch.nn.functional.interpolate


def _interpolate_coreml_compat(*args, **kwargs):
    mode = kwargs.get("mode", None)
    if mode == "bicubic":
        kwargs["mode"] = "bilinear"
    elif len(args) >= 4 and isinstance(args[3], str) and args[3] == "bicubic":
        args = list(args)
        args[3] = "bilinear"
        args = tuple(args)
    return _orig_interpolate(*args, **kwargs)


torch.nn.functional.interpolate = _interpolate_coreml_compat

from depth_anything_3.api import DepthAnything3  # noqa: E402
import depth_anything_3.model.dpt as dpt_mod  # noqa: E402
import depth_anything_3.model.dualdpt as dualdpt_mod  # noqa: E402
import depth_anything_3.model.da3 as da3_mod  # noqa: E402
import depth_anything_3.model.cam_enc as cam_enc_mod  # noqa: E402
import depth_anything_3.model.utils.transform as transform_mod  # noqa: E402
import depth_anything_3.model.utils.head_utils as head_utils_mod  # noqa: E402


def affine_inverse(a: torch.Tensor) -> torch.Tensor:
    r = a[..., :3, :3]
    t = a[..., :3, 3:]
    p = a[..., 3:, :]
    rt = r.transpose(-1, -2)
    return torch.cat([torch.cat([rt, -rt @ t], dim=-1), p], dim=-2)


# Patch DA3's camera encoder for export. Official geometry.affine_inverse uses
# Tensor.mT, which coremltools 9 does not lower from TorchScript. The math is
# identical; only the traced op changes to aten::transpose.
cam_enc_mod.affine_inverse = affine_inverse
da3_mod.affine_inverse = affine_inverse


def create_uv_grid_export(
    width: int,
    height: int,
    aspect_ratio: float = None,
    dtype: torch.dtype = None,
    device: torch.device = None,
) -> torch.Tensor:
    if aspect_ratio is None:
        aspect_ratio = float(width) / float(height)
    diag_factor = (aspect_ratio**2 + 1.0) ** 0.5
    span_x = aspect_ratio / diag_factor
    span_y = 1.0 / diag_factor
    left_x = -span_x * (width - 1) / width
    right_x = span_x * (width - 1) / width
    top_y = -span_y * (height - 1) / height
    bottom_y = span_y * (height - 1) / height
    x_coords = torch.linspace(left_x, right_x, steps=width, dtype=dtype, device=device)
    y_coords = torch.linspace(top_y, bottom_y, steps=height, dtype=dtype, device=device)
    uu = x_coords.view(1, width).expand(height, width)
    vv = y_coords.view(height, 1).expand(height, width)
    return torch.stack((uu, vv), dim=-1)


head_utils_mod.create_uv_grid = create_uv_grid_export
dualdpt_mod.create_uv_grid = create_uv_grid_export
dpt_mod.create_uv_grid = create_uv_grid_export


def pose_encoding_to_extri_intri_export(pose_encoding, image_size_hw=None):
    t = pose_encoding[..., :3]
    quat = pose_encoding[..., 3:7]
    fov_h = pose_encoding[..., 7]
    fov_w = pose_encoding[..., 8]
    r = transform_mod.quat_to_mat(quat)
    extrinsics = torch.cat([r, t[..., None]], dim=-1)

    h, w = image_size_hw
    fy = (h / 2.0) / torch.clamp(torch.tan(fov_h / 2.0), 1e-6)
    fx = (w / 2.0) / torch.clamp(torch.tan(fov_w / 2.0), 1e-6)
    zero = torch.zeros_like(fx)
    row0 = torch.stack([fx, zero, torch.full_like(fx, w / 2.0)], dim=-1)
    row1 = torch.stack([zero, fy, torch.full_like(fy, h / 2.0)], dim=-1)
    row2 = torch.stack([zero, zero, torch.ones_like(fx)], dim=-1)
    intrinsics = torch.stack([row0, row1, row2], dim=-2)
    return extrinsics, intrinsics


transform_mod.pose_encoding_to_extri_intri = pose_encoding_to_extri_intri_export
da3_mod.pose_encoding_to_extri_intri = pose_encoding_to_extri_intri_export


def fixed_k_median(values: torch.Tensor) -> torch.Tensor:
    """Static median for the K values used by PocketWorld CoreML exports."""
    sorted_values = static_sort_last_dim(values)
    k = len(sorted_values)
    if k % 2 == 1:
        return sorted_values[k // 2]
    return (sorted_values[k // 2 - 1] + sorted_values[k // 2]) * 0.5


def static_sort_last_dim(values: torch.Tensor) -> list[torch.Tensor]:
    """Trace-friendly insertion sort for small fixed-K tensors."""
    items = list(values.unbind(dim=-1))
    if not 1 <= len(items) <= 60:
        raise ValueError(f"CoreML pose exporter currently supports fixed K in [1,60], got {len(items)}")
    out: list[torch.Tensor] = []
    for item in items:
        out.append(item)
        idx = len(out) - 1
        while idx > 0:
            lo = torch.minimum(out[idx - 1], out[idx])
            hi = torch.maximum(out[idx - 1], out[idx])
            out[idx - 1], out[idx] = lo, hi
            idx -= 1
    return out


class DA3PoseConditionedWrapper(nn.Module):
    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def normalize_extrinsics(self, extrinsics: torch.Tensor) -> torch.Tensor:
        transform = affine_inverse(extrinsics[:, :1])
        ex_norm = extrinsics @ transform
        c2ws = affine_inverse(ex_norm)
        translations = c2ws[..., :3, 3]
        dists = translations.norm(dim=-1)
        median_dist = fixed_k_median(dists).clamp(min=1e-1)
        scale = median_dist[:, None, None]
        translation = ex_norm[..., :3, 3] / scale
        ex_norm = torch.cat(
            [
                torch.cat([ex_norm[..., :3, :3], translation[..., None]], dim=-1),
                ex_norm[..., 3:, :],
            ],
            dim=-2,
        )
        return ex_norm

    def forward(
        self,
        image: torch.Tensor,
        extrinsics: torch.Tensor,
        intrinsics: torch.Tensor,
    ):
        ex_norm = self.normalize_extrinsics(extrinsics)
        out = self.model(image, ex_norm, intrinsics)
        return out["depth"], out["depth_conf"], out["extrinsics"], out["intrinsics"]


def freeze_dinov2_pos_embed(root: nn.Module, height: int, width: int) -> int:
    """Precompute DINO positional interpolation for fixed export size."""
    patched = 0
    for module in root.modules():
        if not all(hasattr(module, attr) for attr in ("interpolate_pos_encoding", "pos_embed", "patch_size")):
            continue
        pos_embed = module.pos_embed
        patch_size = int(module.patch_size)
        tokens = (height // patch_size) * (width // patch_size) + 1
        dummy = torch.zeros(1, tokens, pos_embed.shape[-1], dtype=pos_embed.dtype, device=pos_embed.device)
        with torch.no_grad():
            fixed = module.interpolate_pos_encoding(dummy, height, width).detach().clone()
        module.register_buffer("_fixed_export_pos_embed", fixed, persistent=False)

        def _fixed_interpolate_pos_encoding(self, x, w, h):
            return self._fixed_export_pos_embed.to(dtype=x.dtype, device=x.device)

        module.interpolate_pos_encoding = types.MethodType(_fixed_interpolate_pos_encoding, module)
        patched += 1
    return patched


def make_dummy(k: int, height: int, width: int):
    image = torch.randn(1, k, 3, height, width, dtype=torch.float32)
    extrinsics = torch.eye(4, dtype=torch.float32).view(1, 1, 4, 4).repeat(1, k, 1, 1)
    # Non-collinear camera centers so pose conditioning has a healthy baseline.
    for idx in range(k):
        theta = 2.0 * math.pi * float(idx) / max(float(k), 1.0)
        extrinsics[:, idx, 0, 3] = 0.20 * math.cos(theta)
        extrinsics[:, idx, 1, 3] = 0.16 * math.sin(theta)
        extrinsics[:, idx, 2, 3] = 0.08 * math.sin(theta * 1.7)
    intrinsics = torch.eye(3, dtype=torch.float32).view(1, 1, 3, 3).repeat(1, k, 1, 1)
    intrinsics[:, :, 0, 0] = float(width)
    intrinsics[:, :, 1, 1] = float(height)
    intrinsics[:, :, 0, 2] = float(width) * 0.5
    intrinsics[:, :, 1, 2] = float(height) * 0.5
    return image, extrinsics, intrinsics


def output_name(k: int, height: int, width: int, fp32: bool) -> str:
    suffix = "_fp32" if fp32 else ""
    size = f"{height}x{width}" if height != width else str(height)
    return f"DA3LARGE_v11_{size}_N{k}_pose{suffix}"


def print_outputs(outputs) -> None:
    for name, tensor in zip(["depth", "depth_conf", "pred_extrinsics", "pred_intrinsics"], outputs):
        print(f"  {name}: shape={tuple(tensor.shape)} dtype={tensor.dtype}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", default=str(MODEL_PATH))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--out-name")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--side", type=int, default=252)
    parser.add_argument("--height", type=int, help="Optional non-square input height; defaults to --side")
    parser.add_argument("--width", type=int, help="Optional non-square input width; defaults to --side")
    parser.add_argument("--forward-only", action="store_true")
    parser.add_argument("--trace-only", action="store_true")
    parser.add_argument("--fp32", action="store_true", help="Use fp32 CoreML precision instead of fp16")
    parser.add_argument(
        "--direct-package-save",
        action="store_true",
        help="Ask coremltools to write package_dir during conversion and skip the extra Core ML load/save pass.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    height = args.height or args.side
    width = args.width or args.side
    if height % 14 != 0 or width % 14 != 0:
        raise ValueError(f"--height/--width should be multiples of 14 for DA3/DINO patch grid; got {height}x{width}")
    if not 1 <= args.k <= 60:
        raise ValueError("--k must be in [1,60] for this fixed-median CoreML exporter")

    print(f"[pose-export] loading DA3 from {args.model_path}")
    t0 = time.time()
    da3 = DepthAnything3.from_pretrained(args.model_path)
    da3.eval()
    patched_pos = freeze_dinov2_pos_embed(da3.model, height, width)
    print(f"[pose-export] froze DINO pos embed modules: {patched_pos}")
    wrapper = DA3PoseConditionedWrapper(da3.model).eval()
    print(f"[pose-export] loaded in {time.time() - t0:.1f}s")

    dummy = make_dummy(args.k, height, width)
    with torch.inference_mode():
        print("[pose-export] forward smoke")
        outputs = wrapper(*dummy)
        print_outputs(outputs)
    if args.forward_only:
        return 0

    print("[pose-export] torch.jit.trace")
    t0 = time.time()
    with torch.inference_mode():
        traced = torch.jit.trace(wrapper, dummy, strict=False)
        traced.eval()
    print(f"[pose-export] traced in {time.time() - t0:.1f}s")
    if args.trace_only:
        return 0
    del outputs
    del dummy
    gc.collect()

    import coremltools as ct

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.out_name or output_name(args.k, height, width, args.fp32)
    out_path = out_dir / f"{name}.mlpackage"
    if out_path.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite existing package: {out_path}")
    if out_path.exists() and args.overwrite:
        import shutil

        shutil.rmtree(out_path)

    precision = ct.precision.FLOAT32 if args.fp32 else ct.precision.FLOAT16
    print(f"[pose-export] coremltools.convert -> {out_path}")
    t0 = time.time()
    mlmodel = ct.convert(
        traced,
        convert_to="mlprogram",
        minimum_deployment_target=ct.target.iOS16,
        compute_precision=precision,
        skip_model_load=args.direct_package_save,
        package_dir=str(out_path) if args.direct_package_save else None,
        inputs=[
            ct.TensorType(name="image", shape=(1, args.k, 3, height, width), dtype=np.float32),
            ct.TensorType(name="extrinsics", shape=(1, args.k, 4, 4), dtype=np.float32),
            ct.TensorType(name="intrinsics", shape=(1, args.k, 3, 3), dtype=np.float32),
        ],
        outputs=[
            ct.TensorType(name="depth"),
            ct.TensorType(name="depth_conf"),
            ct.TensorType(name="pred_extrinsics"),
            ct.TensorType(name="pred_intrinsics"),
        ],
    )
    if args.direct_package_save:
        if not out_path.exists():
            raise FileNotFoundError(f"coremltools did not write expected package: {out_path}")
        print(f"[pose-export] saved {out_path} during convert in {time.time() - t0:.1f}s")
        print(f"[pose-export] size={out_path.stat().st_size / 1024**2:.1f} MB package root")
        return 0

    mlmodel.short_description = f"DA3-LARGE-1.1 K={args.k} {height}x{width} pose-conditioned experimental export"
    mlmodel.author = "PocketWorld (DA3 from ByteDance Seed, Apache 2.0)"
    mlmodel.license = "Apache 2.0"
    mlmodel.version = "1.1"
    mlmodel.input_description["image"] = f"ImageNet-normalized RGB tensor [1,{args.k},3,{height},{width}]"
    mlmodel.input_description["extrinsics"] = f"Raw OpenCV/COLMAP w2c extrinsics [1,{args.k},4,4]"
    mlmodel.input_description["intrinsics"] = f"Input-resolution camera intrinsics [1,{args.k},3,3]"
    mlmodel.output_description["depth"] = f"DA3 relative depth [1,{args.k},{height},{width}]"
    mlmodel.output_description["depth_conf"] = f"DA3 depth confidence [1,{args.k},{height},{width}]"
    mlmodel.output_description["pred_extrinsics"] = f"DA3 predicted w2c extrinsics [1,{args.k},3,4]"
    mlmodel.output_description["pred_intrinsics"] = f"DA3 predicted intrinsics [1,{args.k},3,3]"
    mlmodel.save(str(out_path))
    print(f"[pose-export] saved {out_path} in {time.time() - t0:.1f}s")
    print(f"[pose-export] size={out_path.stat().st_size / 1024**2:.1f} MB package root")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
