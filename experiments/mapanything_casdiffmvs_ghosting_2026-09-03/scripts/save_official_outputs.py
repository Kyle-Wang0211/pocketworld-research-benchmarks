#!/usr/bin/env python3
"""Replay the exact official Apache images-only demo inference and persist every
per-view output tensor. Diagnostic only: no filtering, no fusion, no threshold
changes. Inference arguments are copied verbatim from
scripts/demo_images_only_inference.py (lines 172-180)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

if torch.cuda.is_available():
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

sys.path.insert(0, os.getcwd())

from mapanything.models import MapAnything  # noqa: E402
from mapanything.utils.device import get_device  # noqa: E402
from mapanything.utils.geometry import depthmap_to_world_frame  # noqa: E402
from mapanything.utils.image import load_images  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image_folder", required=True)
    parser.add_argument("--output_dir", required=True)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()

    image_paths = sorted(
        p
        for p in Path(args.image_folder).iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    manifest = [
        {"name": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}
        for p in image_paths
    ]
    manifest_sha = hashlib.sha256(
        "\n".join(f"{m['sha256']}  {m['name']}" for m in manifest).encode()
    ).hexdigest()

    device = get_device()
    model = MapAnything.from_pretrained("facebook/map-anything-apache").to(device)
    views = load_images(args.image_folder)
    assert len(views) == len(image_paths), (len(views), len(image_paths))

    torch.cuda.synchronize()
    t_inf = time.time()
    outputs = model.infer(
        views,
        memory_efficient_inference=True,
        minibatch_size=1,
        use_amp=True,
        amp_dtype="bf16",
        apply_mask=True,
        mask_edges=True,
    )
    torch.cuda.synchronize()
    inference_seconds = time.time() - t_inf

    # Persist every tensor-valued key generically.
    keys = sorted(k for k, v in outputs[0].items() if isinstance(v, torch.Tensor))
    saved = {}
    for key in keys:
        arrs = []
        for pred in outputs:
            t = pred[key].detach().cpu()
            arrs.append(t)
        stacked = torch.cat(arrs, dim=0) if arrs[0].dim() > 0 else torch.stack(arrs)
        np_arr = stacked.numpy()
        if key == "img_no_norm":
            np_arr = np.clip(np_arr * 255.0 + 0.5, 0, 255).astype(np.uint8)
        elif np_arr.dtype == np.bool_:
            pass
        elif np_arr.dtype != np.float32:
            np_arr = np_arr.astype(np.float32)
        np.save(out / f"{key}.npy", np_arr)
        saved[key] = {"shape": list(np_arr.shape), "dtype": str(np_arr.dtype)}

    # Recompute the demo's exported vertex set exactly as the official script does.
    demo_vertex_count = 0
    per_view_counts = []
    for pred in outputs:
        depthmap = pred["depth_z"][0].squeeze(-1)
        intr = pred["intrinsics"][0]
        pose = pred["camera_poses"][0]
        _, valid = depthmap_to_world_frame(depthmap, intr, pose)
        mask = pred["mask"][0].squeeze(-1).cpu().numpy().astype(bool)
        mask = mask & valid.cpu().numpy()
        per_view_counts.append(int(mask.sum()))
        demo_vertex_count += int(mask.sum())

    info = {
        "purpose": "diagnostic replay of official images-only demo; per-view tensors saved verbatim",
        "repo_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "model": "facebook/map-anything-apache",
        "image_folder": args.image_folder,
        "num_views": len(views),
        "ordered_image_manifest_sha256": manifest_sha,
        "image_manifest": manifest,
        "infer_kwargs": {
            "memory_efficient_inference": True,
            "minibatch_size": 1,
            "use_amp": True,
            "amp_dtype": "bf16",
            "apply_mask": True,
            "mask_edges": True,
        },
        "saved_keys": saved,
        "demo_export_vertex_count": demo_vertex_count,
        "per_view_vertex_counts": per_view_counts,
        "inference_seconds": inference_seconds,
        "total_seconds": time.time() - started,
        "torch": torch.__version__,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "peak_cuda_bytes": int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else 0,
    }
    (out / "info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps({k: v for k, v in info.items() if k not in ("image_manifest", "per_view_vertex_counts")}, indent=2))


if __name__ == "__main__":
    main()
