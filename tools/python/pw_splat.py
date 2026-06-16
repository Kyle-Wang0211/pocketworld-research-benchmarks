"""Headless numpy z-buffer point splatter (no GL/Filament). Renders a colored
point cloud (or mesh vertices) from a chosen ARKit camera pose so DiffMVS output
and the DA3 baseline can be compared at matched, scene-relevant viewpoints.

Usage: pw_splat.py <ply> <out_png> <win> <ref_local> [splat]
"""
import sys, json
from pathlib import Path
import numpy as np
import open3d as o3d

ROOT = Path(__file__).resolve().parents[2]
EXPAC = ROOT / "data/expAC_rewindow_span_2026_06_13"
OBASE = ROOT / "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/external_pose_k_vs_res_2026_06_10"

ply = Path(sys.argv[1]); out = Path(sys.argv[2])
win = int(sys.argv[3]); ref = int(sys.argv[4])
splat = int(sys.argv[5]) if len(sys.argv) > 5 else 2
SCALE = 2.0  # render at 2x the npz 896x504 for crisper view
W, H = int(896 * SCALE), int(512 * SCALE)

# virtual camera from a real npz window frame
z = np.load(EXPAC / "windows" / f"win_{win:02d}.npz")
K = z["K"][ref].astype(np.float64).copy(); w2c = z["w2c"][ref].astype(np.float64)
K[:2, :] *= SCALE  # scale intrinsics to render resolution (npz K is 896x504)

# load geometry as points (.npz per-frame dump, mesh .ply, or point .ply)
if ply.suffix == ".npz":
    d2 = np.load(ply); m2 = d2["conf"] > 0.5
    xyz = d2["xyz"][m2]; rgb = d2["rgb"][m2].astype(np.float64) / 255.0
else:
    g = o3d.io.read_triangle_mesh(str(ply))
    if len(g.vertices) > 0:
        xyz = np.asarray(g.vertices); rgb = np.asarray(g.vertex_colors)
        if len(rgb) == 0:
            rgb = np.ones_like(xyz) * 0.7
    else:
        p = o3d.io.read_point_cloud(str(ply)); xyz = np.asarray(p.points); rgb = np.asarray(p.colors)
print(f"{ply.name}: {len(xyz):,} pts", flush=True)

cam = (w2c[:3, :3] @ xyz.T + w2c[:3, 3:4]).T
zc = cam[:, 2]
front = zc > 0.05
cam = cam[front]; col = (rgb[front] * 255).astype(np.uint8); zc = zc[front]
uv = (K @ cam.T).T; uv = uv[:, :2] / uv[:, 2:3]
u = np.round(uv[:, 0]).astype(int); v = np.round(uv[:, 1]).astype(int)
inb = (u >= 0) & (u < W) & (v >= 0) & (v < H)
u, v, zc, col = u[inb], v[inb], zc[inb], col[inb]

img = np.full((H, W, 3), 26, np.uint8)
zbuf = np.full((H, W), 1e9, np.float32)
order = np.argsort(-zc)  # far first so near overwrites
u, v, zc, col = u[order], v[order], zc[order], col[order]
for du in range(-splat, splat + 1):
    for dv in range(-splat, splat + 1):
        uu = np.clip(u + du, 0, W - 1); vv = np.clip(v + dv, 0, H - 1)
        img[vv, uu] = col          # col is RGB; o3d Image expects RGB
o3d.io.write_image(str(out), o3d.geometry.Image(np.ascontiguousarray(img)))
print("wrote", out.name, f"({front.sum():,} in front)", flush=True)
