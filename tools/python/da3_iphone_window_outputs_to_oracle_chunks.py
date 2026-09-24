#!/usr/bin/env python3
"""Convert iPhone pocketworld_da3_bench window outputs → oracle resume chunk_N.npy.

iPhone bench app saves per-window:
  window_NNN/
    depth.bin           # fp32 little-endian raw, shape from meta.json
    depth_conf.bin
    pred_extrinsics.bin
    pred_intrinsics.bin
    meta.json           # tensor_shapes, tensor_dtypes, window_start_frame, ...

This script builds a SimpleNamespace per chunk matching
da3_streaming.DA3_Streaming.process_single_chunk return value:
  predictions.depth            # [K, H, W] float32 (squeezed)
  predictions.conf             # [K, H, W] float32 (- 1.0 like upstream)
  predictions.intrinsics       # [K, 3, 3] float32
  predictions.extrinsics       # [K, 3, 4] float32 (w2c)
  predictions.processed_images # [K, H, W, 3] uint8 (generated from source jpgs)

and writes np.save(chunk_{idx}.npy, predictions, allow_pickle=True) so that
da3base_official_streaming_oracle_resume.py's _resume_process_single_chunk
loads them directly.
"""

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iphone-run-dir", type=Path, required=True,
                        help="Path to da3_bench_run_*/ pulled from iPhone Documents")
    parser.add_argument("--source-images-dir", type=Path, required=True,
                        help="Directory with 414 source jpgs (000000.jpg .. 000413.jpg)")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Where to write chunk_0.npy .. chunk_N.npy")
    parser.add_argument("--input-height", type=int, default=280)
    parser.add_argument("--input-width", type=int, default=504)
    parser.add_argument("--conf-shift", type=float, default=1.0,
                        help="Upstream DA3-Streaming does conf -= 1.0 after inference")
    return parser.parse_args()


def load_window_meta(window_dir: Path) -> dict:
    with (window_dir / "meta.json").open() as f:
        return json.load(f)


def load_bin_as_fp32(path: Path, shape: list[int]) -> np.ndarray:
    """Read raw little-endian fp32 binary and reshape."""
    arr = np.fromfile(path, dtype=np.float32)
    expected = int(np.prod(shape))
    if arr.size != expected:
        raise ValueError(f"{path}: expected {expected} elems for shape {shape}, "
                         f"got {arr.size}")
    return arr.reshape(shape)


def make_processed_images(source_dir: Path, start_frame: int, window_size: int,
                          height: int, width: int) -> np.ndarray:
    """Build [K, H, W, 3] uint8 from source jpgs (resize bilinear, RGB)."""
    out = np.zeros((window_size, height, width, 3), dtype=np.uint8)
    for k in range(window_size):
        idx = start_frame + k
        jpg = source_dir / f"{idx:06d}.jpg"
        if not jpg.exists():
            raise FileNotFoundError(f"source jpg not found: {jpg}")
        img = Image.open(jpg).convert("RGB").resize((width, height), Image.BILINEAR)
        out[k] = np.array(img, dtype=np.uint8)
    return out


def convert_one_window(window_dir: Path, source_dir: Path, height: int, width: int,
                       conf_shift: float) -> SimpleNamespace:
    meta = load_window_meta(window_dir)
    shapes = meta["tensor_shapes"]
    start_frame = int(meta["window_start_frame"])
    window_size = int(meta["window_size"])

    # Each tensor's raw bin file
    depth_shape = shapes["depth"]
    conf_shape = shapes["depth_conf"]
    extr_shape = shapes["pred_extrinsics"]
    intr_shape = shapes["pred_intrinsics"]

    depth_raw = load_bin_as_fp32(window_dir / "depth.bin", depth_shape)
    conf_raw = load_bin_as_fp32(window_dir / "depth_conf.bin", conf_shape)
    extr_raw = load_bin_as_fp32(window_dir / "pred_extrinsics.bin", extr_shape)
    intr_raw = load_bin_as_fp32(window_dir / "pred_intrinsics.bin", intr_shape)

    # Squeeze leading 1 if present + reshape to [K, H, W] / [K, 3, 4] / [K, 3, 3]
    depth = depth_raw.reshape(-1, depth_shape[-2], depth_shape[-1])
    # Match upstream da3_streaming.py:275-276 semantics
    #   predictions.depth = np.squeeze(predictions.depth)
    #   predictions.conf -= 1.0
    conf = conf_raw.reshape(-1, conf_shape[-2], conf_shape[-1]) - conf_shift

    extr_flat = extr_raw.reshape(-1)
    intr_flat = intr_raw.reshape(-1)
    if extr_flat.size != window_size * 12 or intr_flat.size != window_size * 9:
        raise ValueError(
            f"pose tensor size mismatch: extr={extr_flat.size} "
            f"intr={intr_flat.size}, expected {window_size}*12={window_size*12} "
            f"and {window_size}*9={window_size*9}"
        )
    extrinsics = extr_flat.reshape(window_size, 3, 4)
    intrinsics = intr_flat.reshape(window_size, 3, 3)

    # Generate processed_images [K, H, W, 3] uint8 from source jpgs
    processed_images = make_processed_images(
        source_dir, start_frame, window_size, height, width
    )

    return SimpleNamespace(
        depth=depth.astype(np.float32),
        conf=conf.astype(np.float32),
        extrinsics=extrinsics.astype(np.float32),
        intrinsics=intrinsics.astype(np.float32),
        processed_images=processed_images,
    )


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    window_dirs = sorted(d for d in args.iphone_run_dir.iterdir()
                         if d.is_dir() and d.name.startswith("window_"))
    if not window_dirs:
        print(f"no window_* subdirs found in {args.iphone_run_dir}", file=sys.stderr)
        return 1
    print(f"found {len(window_dirs)} windows", flush=True)

    for chunk_idx, window_dir in enumerate(window_dirs):
        out_path = args.output_dir / f"chunk_{chunk_idx}.npy"
        print(f"[{chunk_idx}/{len(window_dirs)}] {window_dir.name} → {out_path.name}",
              flush=True)
        predictions = convert_one_window(
            window_dir, args.source_images_dir,
            args.input_height, args.input_width,
            args.conf_shift,
        )
        np.save(out_path, predictions, allow_pickle=True)
        print(f"  depth {predictions.depth.shape} | conf {predictions.conf.shape}"
              f" | extr {predictions.extrinsics.shape}"
              f" | intr {predictions.intrinsics.shape}"
              f" | processed {predictions.processed_images.shape}",
              flush=True)

    print(f"done — {len(window_dirs)} chunks written to {args.output_dir}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
