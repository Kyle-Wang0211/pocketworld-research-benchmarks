#!/usr/bin/env python3
"""Measure 5cm-cell floor coverage for a rescue band PLY vs the SIFT production floor,
using the SAME in-plane (u,v) basis + integer cell grid as build_floor_rescue.py so cells
align 1:1. Reports: rescue total cells, cells NOT already covered by production (=new holes filled),
new area m2, and geometry-quality medians read from the band PLY's per-point props if present.
Usage: python3 fr_coverage.py <rescue_band.ply> [label]
"""
import sys, numpy as np
import fr_common as fc

CELL = 0.05
n = fc.PLANE_N.copy()
a = np.array([1.0, 0, 0])
if abs(n @ a) > 0.9: a = np.array([0, 0, 1.0])
u = a - (a @ n) * n; u /= np.linalg.norm(u); v = np.cross(n, u)

def read_ply_xyz_props(path):
    lines = open(path).read().splitlines()
    hi = lines.index("end_header")
    props = [l.split()[-1] for l in lines[:hi] if l.startswith("property")]
    data = [ln.split() for ln in lines[hi+1:] if ln.strip()]
    arr = np.array(data, float)
    return arr, props

def cells_of(xyz):
    uv = np.stack([xyz @ u, xyz @ v], 1)
    return set(map(tuple, np.floor(uv / CELL).astype(int)))

# production reference cells (ascii? it's binary) -> reuse xyz from production_floor.ply
def read_ply_binary(path):
    import struct
    buf = open(path, "rb").read()
    lines = buf.split(b"end_header\n", 1)[0].splitlines()
    nv = int([l for l in lines if l.startswith(b"element vertex")][0].split()[-1])
    body = buf.split(b"end_header\n", 1)[1]
    rec = 15  # 3 float + 3 uchar
    xyz = np.zeros((nv, 3))
    for i in range(nv):
        xyz[i] = struct.unpack_from("<fff", body, i*rec)
    return xyz

prod_xyz = read_ply_binary(fc.FR + "/production_floor.ply")
prod_cells = cells_of(prod_xyz)

path = sys.argv[1]
label = sys.argv[2] if len(sys.argv) > 2 else path
arr, props = read_ply_xyz_props(path)
xyz = arr[:, :3]
res_cells = cells_of(xyz)
new_cells = res_cells - prod_cells

def col(name):
    return arr[:, props.index(name)] if name in props else None

ta = col("tri_angle_deg"); rp = col("max_reproj_px"); nv = col("nview"); fd = col("floor_dist_m")
print(f"=== {label} ===")
print(f"floor-band points          : {len(xyz)}")
print(f"rescue 5cm cells (total)   : {len(res_cells)}   [current baseline 793]")
print(f"NEW cells (not in SIFT)     : {len(new_cells)}   area={len(new_cells)*CELL*CELL:.3f} m2")
print(f"rescue-covered area (total) : {len(res_cells)*CELL*CELL:.3f} m2   (production SIFT: {len(prod_cells)} cells)")
if ta is not None:
    print(f"tri_angle deg  median={np.median(ta):.2f}  frac>=2deg={(ta>=2).mean():.3f}")
if rp is not None:
    print(f"max_reproj px  median={np.median(rp):.3f}")
if nv is not None:
    print(f"nview          median={np.median(nv):.1f}  max={int(nv.max())}")
if fd is not None:
    print(f"|floor_dist| mm median={np.median(np.abs(fd))*1000:.2f}")
