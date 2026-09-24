#!/usr/bin/env python3
"""Convert Da3DepthPlugin per-frame window outputs → oracle resume chunk_N.npy.

Input layout (pulled from iPhone Documents/da3_bench_run_*/):
  window_NNN/
    relative_depth/<safeID>.bin   # H*W fp32 LE, one per frame
    confidence/<safeID>.bin       # H*W fp32 LE
    pred_pose/<safeID>_extrinsics.bin  # 12 fp32 (3x4 w2c)
    pred_pose/<safeID>_intrinsics.bin  # 9 fp32 (3x3)
  where safeID ends with ..._slot_SSS (slot index inside the window).

Output: chunk_{idx}.npy files compatible with
da3base_official_streaming_oracle_resume.py's process_single_chunk cache:
  SimpleNamespace(
    depth            [K,H,W] fp32,
    conf             [K,H,W] fp32  (shifted by -1.0 like upstream),
    extrinsics       [K,3,4] fp32,
    intrinsics       [K,3,3] fp32,
    processed_images [K,H,W,3] uint8,
  )

processed_images come from the official C++ preprocess PNG output
(da3_preprocess_cli --out-png) in cap-N global frame order.
"""

import argparse
import re
import subprocess
import sys
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

SLOT_RE = re.compile(r"_slot_(\d+)$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--iphone-run-dir", type=Path, required=True,
                   help="da3_bench_run_* dir pulled from iPhone")
    p.add_argument("--photo-bundle", type=Path, required=True,
                   help="photo_bundle.json with cap-N frame ordering")
    p.add_argument("--photos-highres-dir", type=Path, required=True,
                   help="source highres jpgs referenced by photo_bundle")
    p.add_argument("--preprocess-cli", type=Path, required=True,
                   help="da3_preprocess_cli binary")
    p.add_argument("--process-res", type=int, required=True,
                   help="official process_res used on phone (e.g. 392, 406)")
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--png-cache-dir", type=Path, required=True,
                   help="where to generate/reuse official processed PNGs")
    p.add_argument("--output-dir", type=Path, required=True,
                   help="dir to write chunk_N.npy (oracle _tmp_results_unaligned)")
    p.add_argument("--conf-shift", type=float, default=1.0)
    return p.parse_args()


def ordered_frames(photo_bundle: Path) -> list[dict]:
    with photo_bundle.open() as f:
        d = json.load(f)
    return sorted(d["frames"], key=lambda fr: int(fr["id"].split("-")[1]))


def ensure_pngs(frames: list[dict], src_dir: Path, cli: Path, process_res: int,
                png_dir: Path, width: int, height: int) -> list[Path]:
    png_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    made = 0
    for i, fr in enumerate(frames):
        out = png_dir / f"{i:06d}.png"
        paths.append(out)
        if out.exists():
            continue
        r = subprocess.run(
            [str(cli), "--input", str(src_dir / fr["highresFilename"]),
             "--out-png", str(out), "--out-tensor", "/tmp/_ignore_tensor.bin",
             "--process-res", str(process_res)],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"preprocess failed for frame {i}: {r.stderr[:300]}")
        made += 1
    if made:
        print(f"generated {made} processed PNGs into {png_dir}", flush=True)
    # sanity-check first png size
    with Image.open(paths[0]) as im:
        if im.size != (width, height):
            raise ValueError(f"png size {im.size} != expected ({width},{height})")
    return paths


def load_window(window_dir: Path, height: int, width: int,
                conf_shift: float) -> SimpleNamespace:
    depth_dir = window_dir / "relative_depth"
    conf_dir = window_dir / "confidence"
    pose_dir = window_dir / "pred_pose"

    def slot_of(stem: str) -> int:
        m = SLOT_RE.search(stem)
        if not m:
            raise ValueError(f"no slot suffix in {stem}")
        return int(m.group(1))

    depth_files = sorted(depth_dir.glob("*.bin"), key=lambda p: slot_of(p.stem))
    k = len(depth_files)
    if k == 0:
        raise FileNotFoundError(f"no depth bins in {depth_dir}")

    plane = height * width
    depth = np.empty((k, height, width), dtype=np.float32)
    conf = np.empty((k, height, width), dtype=np.float32)
    extr = np.empty((k, 3, 4), dtype=np.float32)
    intr = np.empty((k, 3, 3), dtype=np.float32)

    for slot, dfile in enumerate(depth_files):
        stem = dfile.stem
        if slot_of(stem) != slot:
            raise ValueError(f"slot gap at {slot}: {stem}")
        arr = np.fromfile(dfile, dtype=np.float32)
        if arr.size != plane:
            raise ValueError(f"{dfile}: {arr.size} != {plane}")
        depth[slot] = arr.reshape(height, width)

        cfile = conf_dir / dfile.name
        carr = np.fromfile(cfile, dtype=np.float32)
        if carr.size != plane:
            raise ValueError(f"{cfile}: {carr.size} != {plane}")
        conf[slot] = carr.reshape(height, width)

        e = np.fromfile(pose_dir / f"{stem}_extrinsics.bin", dtype=np.float32)
        if e.size != 12:
            raise ValueError(f"extr {stem}: {e.size} != 12")
        extr[slot] = e.reshape(3, 4)

        i9 = np.fromfile(pose_dir / f"{stem}_intrinsics.bin", dtype=np.float32)
        if i9.size != 9:
            raise ValueError(f"intr {stem}: {i9.size} != 9")
        intr[slot] = i9.reshape(3, 3)

    # Confidence contract (proven in da3_depth_index_official_npz_oracle_bridge):
    # raw_api values are 1+exp(x) >= 1 → subtract 1 like upstream da3_streaming.
    # CoreML wrapper outputs are already in the exp-like [0, ~1.4] range → as-is.
    if float(np.nanmin(conf)) >= 0.9:
        conf -= np.float32(conf_shift)
        contract = "raw_api_minus_one"
    else:
        contract = "streaming_as_is"
    print(f"  conf contract: {contract} (min={conf.min():.4f} max={conf.max():.4f})",
          flush=True)

    return SimpleNamespace(depth=depth, conf=conf, extrinsics=extr,
                           intrinsics=intr, processed_images=None)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with (args.iphone_run_dir / "bench_summary.json").open() as f:
        summary = json.load(f)
    windows = summary["windows"]
    print(f"windows: {len(windows)}, model={summary.get('model')}", flush=True)

    frames = ordered_frames(args.photo_bundle)
    pngs = ensure_pngs(frames, args.photos_highres_dir, args.preprocess_cli,
                       args.process_res, args.png_cache_dir,
                       args.width, args.height)

    chunk_starts = []
    for w in sorted(windows, key=lambda x: x["window_index"]):
        idx = w["window_index"]
        start = w["window_start"]
        wdir = args.iphone_run_dir / f"window_{idx:03d}"
        pred = load_window(wdir, args.height, args.width, args.conf_shift)
        k = pred.depth.shape[0]

        imgs = np.empty((k, args.height, args.width, 3), dtype=np.uint8)
        for slot in range(k):
            with Image.open(pngs[start + slot]) as im:
                imgs[slot] = np.asarray(im.convert("RGB"), dtype=np.uint8)
        pred.processed_images = imgs

        out = args.output_dir / f"chunk_{idx}.npy"
        np.save(out, pred, allow_pickle=True)
        chunk_starts.append((idx, start, k))
        print(f"chunk_{idx}: start={start} K={k} "
              f"depth[{pred.depth.shape}] conf[{pred.conf.shape}] "
              f"extr[{pred.extrinsics.shape}] imgs[{imgs.shape}]", flush=True)

    manifest = {
        "source_run": str(args.iphone_run_dir),
        "model": summary.get("model"),
        "height": args.height,
        "width": args.width,
        "process_res": args.process_res,
        "chunks": [
            {"index": i, "start": s, "k": k} for (i, s, k) in chunk_starts
        ],
    }
    with (args.output_dir / "iphone_chunks_manifest.json").open("w") as f:
        json.dump(manifest, f, indent=2)
    print(f"done — {len(chunk_starts)} chunks → {args.output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
