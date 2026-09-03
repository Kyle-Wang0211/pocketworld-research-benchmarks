#!/usr/bin/env python3
"""Convert a colored PLY point cloud into the verdict-page binary layout used by
the existing WebGL viewer: bin/<name>.pos (float32 xyz), bin/<name>.col (uint8
rgb), bin/meta.json. Mechanical copy: no vertex is moved, merged, deleted or
synthesized. The node_matrix is the same 180-degree X rotation the official GLB
exporter applies, so the page is oriented like the previous MapAnything pages."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import open3d as o3d


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


ap = argparse.ArgumentParser()
ap.add_argument("--ply", required=True)
ap.add_argument("--out_bin_dir", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--name", default="official_colmap_native")
ap.add_argument("--extra", default="{}")
args = ap.parse_args()

pcd = o3d.io.read_point_cloud(args.ply)
xyz = np.asarray(pcd.points, dtype=np.float32)
rgb = np.asarray(pcd.colors, dtype=np.float64)
assert xyz.shape[0] == rgb.shape[0] and xyz.shape[0] > 0
col = np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
out = Path(args.out_bin_dir)
out.mkdir(parents=True, exist_ok=True)
pos_path = out / f"{args.name}.pos"
col_path = out / f"{args.name}.col"
xyz.tofile(pos_path)
col.tofile(col_path)

# viewer statistics computed on the displayed (node-transformed) coordinates
node = np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]], dtype=np.float64)
disp = xyz.astype(np.float64) @ node[:3, :3].T
lo, hi = np.percentile(disp, 1, axis=0), np.percentile(disp, 99, axis=0)
center = ((lo + hi) / 2).tolist()
ext = (hi - lo).tolist()
med = np.median(disp, axis=0).tolist()
radius = float(np.linalg.norm(hi - lo) / 2)
node_matrix = [1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 1.2246467991473532e-16, 0.0, 0.0, -1.2246467991473532e-16, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
meta = {
    "tag": args.tag,
    "n": int(xyz.shape[0]),
    "raw_inference_points": int(xyz.shape[0]),
    "center": center,
    "ext": ext,
    "med": med,
    "radius": radius,
    "node_matrix": node_matrix,
    "source_ply": args.ply,
    "source_ply_sha256": sha256_file(Path(args.ply)),
    "position_sha256": sha256_file(pos_path),
    "color_sha256": sha256_file(col_path),
    "position_bytes": pos_path.stat().st_size,
    "color_bytes": col_path.stat().st_size,
    "extraction": "PLY vertices copied verbatim to float32 xyz and uint8 rgb; node matrix (180deg about X, same as official GLB exporter) applied only by viewer",
}
meta.update(json.loads(args.extra))
(out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
print(json.dumps({k: meta[k] for k in ("tag", "n", "radius", "position_bytes", "color_bytes", "position_sha256", "color_sha256")}, indent=2))
