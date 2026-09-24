#!/usr/bin/env python3
"""Minimal MLX-only smoke test for DA3-BASE image-only on Mac.

Bypasses atultw's convert_to_mlx.py (which targets Swift's camelCase) and uses
a Python-native PyTorch->MLX conversion that keeps PyTorch snake_case keys
unchanged (matching what the Python MLX model in mlx_depth_anything_3/ expects).

Only structural conversion done:
- Strip 'model.' prefix
- Conv2d weights: transpose OIHW -> OHWI
- ConvTranspose2d weights: transpose IOHW -> OHWI
- Skip GS-head and aux-head weights (not on image-only depth path)
"""

import sys
import time
import argparse
import re
from pathlib import Path

REPO = Path("/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3-mlx")
sys.path.insert(0, str(REPO))

import numpy as np
import mlx.core as mx

from mlx_depth_anything_3.model import DepthAnything3Net


# ---- python-native PyTorch -> MLX weight conversion ----

CONV2D_NAME_PATTERNS = [
    "patch_embed.proj.weight",
    "conv1.weight", "conv2.weight",
    "out_conv.weight",
    "layer1_rn.weight", "layer2_rn.weight",
    "layer3_rn.weight", "layer4_rn.weight",
    "output_conv1", "output_conv2_a", "output_conv2_b",
    "head.resize_0.weight", "head.resize_1.weight", "head.resize_3.weight",
    "projects.",
]
CONVT2D_NAME_PATTERNS = [
    "head.resize_0.weight",
    "head.resize_1.weight",
]
SKIP_NAME_PATTERNS = [
    "gs_head", "gs_adapter",
    # NOTE: do NOT skip "_aux" — MLX model has _aux modules that need loading
]


def map_pt_to_mlx_key(pt_key: str) -> str | None:
    """Map a PyTorch state_dict key to the MLX-Python model key.

    Adapted from atultw's convert_to_mlx.map_key but:
    - Keeps snake_case (no camelCase rename)
    - Keeps backbone.pretrained. prefix (does NOT strip to backbone.)
    - Does NOT skip _aux
    """
    k = pt_key
    if k.startswith("model."):
        k = k[6:]

    # GS-related skip
    if "gs_head" in k or "gs_adapter" in k:
        return None

    # Structural renames (MLX-Python model uses these)
    # head.scratch.X -> head.X
    k = k.replace("head.scratch.", "head.")
    # head.resize_layers.0/1/3 -> head.resize_0/1/3
    k = re.sub(r"head\.resize_layers\.(\d+)\.", r"head.resize_\1.", k)
    # head.output_conv2.0 -> head.output_conv2_a
    # head.output_conv2.2 -> head.output_conv2_b
    k = re.sub(r"head\.output_conv2\.0\.", "head.output_conv2_a.", k)
    k = re.sub(r"head\.output_conv2\.2\.", "head.output_conv2_b.", k)
    # cam_dec.backbone.0/2 -> cam_dec.backbone_fc1/2
    k = re.sub(r"cam_dec\.backbone\.0\.", "cam_dec.backbone_fc1.", k)
    k = re.sub(r"cam_dec\.backbone\.2\.", "cam_dec.backbone_fc2.", k)
    # cam_dec.fc_fov.0 -> cam_dec.fc_fov_linear
    k = re.sub(r"cam_dec\.fc_fov\.0\.", "cam_dec.fc_fov_linear.", k)
    # head.output_conv1_aux.X.{0..4} -> head.output_conv1_aux.X.layers.{0..4}
    k = re.sub(r"head\.output_conv1_aux\.(\d+)\.(\d+)\.", r"head.output_conv1_aux.\1.layers.\2.", k)
    # head.output_conv2_aux.X.0 -> .conv1; .2 -> .ln; .5 -> .conv2
    k = re.sub(r"head\.output_conv2_aux\.(\d+)\.0\.", r"head.output_conv2_aux.\1.conv1.", k)
    k = re.sub(r"head\.output_conv2_aux\.(\d+)\.2\.", r"head.output_conv2_aux.\1.ln.", k)
    k = re.sub(r"head\.output_conv2_aux\.(\d+)\.5\.", r"head.output_conv2_aux.\1.conv2.", k)

    return k


def is_conv2d_weight(key: str, shape: tuple) -> bool:
    if len(shape) != 4 or not key.endswith(".weight"):
        return False
    return any(p in key for p in CONV2D_NAME_PATTERNS)


def is_convt2d_weight(key: str) -> bool:
    return any(p in key for p in CONVT2D_NAME_PATTERNS)


def load_and_convert_pt_weights(safetensors_path: str) -> dict:
    """Load PyTorch safetensors and convert to MLX with PyTorch-style snake_case keys + structural renames."""
    from safetensors import safe_open
    mlx_weights = {}
    skipped = []
    with safe_open(safetensors_path, framework="numpy") as f:
        for key in f.keys():
            mlx_key = map_pt_to_mlx_key(key)
            if mlx_key is None:
                skipped.append(key)
                continue
            value = f.get_tensor(key)
            arr = value
            if is_convt2d_weight(mlx_key):
                arr = np.ascontiguousarray(arr.transpose(1, 2, 3, 0))
            elif is_conv2d_weight(mlx_key, arr.shape):
                arr = np.ascontiguousarray(arr.transpose(0, 2, 3, 1))
            mlx_weights[mlx_key] = mx.array(arr)
    return mlx_weights, skipped


# ---- model param flattening (to match load_weights API) ----

def flatten_params(params, prefix=""):
    flat = {}
    for k, v in params.items():
        name = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(flatten_params(v, name))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    flat.update(flatten_params(item, f"{name}.{i}"))
                else:
                    flat[f"{name}.{i}"] = item
        else:
            flat[name] = v
    return flat


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-views", type=int, default=60)
    parser.add_argument("--height", type=int, default=280)
    parser.add_argument("--width", type=int, default=504)
    parser.add_argument("--weights", type=str,
                        default="/Users/kaidongwang/.cache/huggingface/hub/models--depth-anything--DA3-BASE/snapshots/f4a6c9b3c95e41c82048423d3493a81ec3fa810e/model.safetensors")
    parser.add_argument("--model", type=str, default="da3-base")
    parser.add_argument("--diagnose-only", action="store_true",
                        help="Just print weight matching stats and exit")
    args = parser.parse_args()

    print(f"=== MLX smoke: model={args.model} N={args.num_views} H={args.height} W={args.width} image-only ===", flush=True)
    t0 = time.time()

    print(f"[1/4] building model...", flush=True)
    model = DepthAnything3Net(args.model)
    print(f"  built in {time.time()-t0:.2f}s", flush=True)

    t1 = time.time()
    print(f"[2/4] loading + converting weights (python-native)...", flush=True)
    mlx_weights, skipped = load_and_convert_pt_weights(args.weights)
    print(f"  loaded {len(mlx_weights)} weights, skipped {len(skipped)} (GS/aux)", flush=True)
    model_params = flatten_params(model.parameters())
    matched = {k: v for k, v in mlx_weights.items() if k in model_params}
    missing_in_weights = sorted(set(model_params.keys()) - set(mlx_weights.keys()))
    extra_in_weights = sorted(set(mlx_weights.keys()) - set(model_params.keys()))
    print(f"  matched: {len(matched)}/{len(model_params)}", flush=True)
    print(f"  model needs but weights lack: {len(missing_in_weights)} (first 10):", flush=True)
    for k in missing_in_weights[:10]:
        print(f"    {k}", flush=True)
    print(f"  weights extra (not in model): {len(extra_in_weights)} (first 10):", flush=True)
    for k in extra_in_weights[:10]:
        print(f"    {k}", flush=True)

    if args.diagnose_only:
        print(f"\n=== DIAGNOSE-ONLY: skipping load + forward ===")
        return

    model.load_weights(list(matched.items()), strict=False)
    mx.eval(model.parameters())
    print(f"  loaded in {time.time()-t1:.2f}s", flush=True)

    t2 = time.time()
    print(f"[3/4] building random input...", flush=True)
    rng = np.random.RandomState(42)
    images = rng.randn(1, args.num_views, args.height, args.width, 3).astype(np.float32)
    x = mx.array(images)
    print(f"  input shape {x.shape} dtype {x.dtype} built in {time.time()-t2:.2f}s", flush=True)

    t3 = time.time()
    print(f"[4/4] forward pass...", flush=True)
    output = model(x, extrinsics=None, intrinsics=None)
    mx.eval(output["depth"])
    print(f"  forward in {time.time()-t3:.2f}s", flush=True)

    depth = np.array(output["depth"][0])
    print(f"  depth shape: {depth.shape}")
    print(f"  depth range: [{depth.min():.4f}, {depth.max():.4f}]")
    print(f"  depth finite: {np.isfinite(depth).all()}")

    print(f"\n=== TOTAL: {time.time()-t0:.2f}s ===")
    print(f"PASS: MLX model={args.model} N={args.num_views} image-only forward completed")


if __name__ == "__main__":
    main()
