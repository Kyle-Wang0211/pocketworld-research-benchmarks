#!/usr/bin/env python3
"""Merge all floor-rescue levers' GOOD points, dedup, and compute merged floor coverage
vs current LoFTR baseline (793 cells) and production SIFT (1101 cells).
Every input point already passed its gate:
  - LoFTR levers (B=native-1024, C=g4 split): cheirality+reproj<3+tri>=2+MAGSAC/Sampson<3
  - plane-sweep (A): multi-view ZNCC>=0.70 + >=3 consistent views + parallax>=5deg
No production code touched. python3.11 (cv2/vtk)."""
import sys, json, struct, numpy as np
import fr_common as fc

CELL = 0.05
# in-plane basis IDENTICAL to fr_coverage.py / build_floor_rescue.py
n = fc.PLANE_N.copy()
a = np.array([1.0, 0, 0])
if abs(n @ a) > 0.9: a = np.array([0, 0, 1.0])
u = a - (a @ n) * n; u /= np.linalg.norm(u); v = np.cross(n, u)

def cells_of(xyz):
    uv = np.stack([xyz @ u, xyz @ v], 1)
    return set(map(tuple, np.floor(uv / CELL).astype(int)))

def read_ply_ascii(path):
    lines = open(path).read().splitlines()
    hi = lines.index("end_header")
    props = [l.split()[-1] for l in lines[:hi] if l.startswith("property")]
    data = np.array([ln.split() for ln in lines[hi+1:] if ln.strip()], float)
    return data, props

def read_ply_binary_rgb(path):
    buf = open(path, "rb").read()
    hdr = buf.split(b"end_header\n", 1)[0]
    nv = int([l for l in hdr.splitlines() if l.startswith(b"element vertex")][0].split()[-1])
    body = buf.split(b"end_header\n", 1)[1]
    xyz = np.zeros((nv, 3)); rgb = np.zeros((nv, 3), np.uint8)
    for i in range(nv):
        xyz[i] = struct.unpack_from("<fff", body, i*15)
        rgb[i] = struct.unpack_from("<BBB", body, i*15+12)
    return xyz, rgb

# ---- references ----
sift_xyz, sift_rgb = read_ply_binary_rgb(fc.FR + "/production_floor.ply")
sift_cells = cells_of(sift_xyz)

# ---- lever inputs (band = floor 20mm only, already gated) ----
ps_grid = sys.argv[1] if len(sys.argv) > 1 else "1cm"
ps_file = "floor_planesweep.ply" if ps_grid == "1cm" else "floor_planesweep_5mm.ply"
A_xyz, A_props = read_ply_ascii(fc.FR + "/" + ps_file)          # plane-sweep (colored)
A_xyz3 = A_xyz[:, :3]
B_xyz, B_props = read_ply_ascii(fc.FR + "/floor_rescue_D_band.ply")   # LoFTR native 1024
B_xyz3 = B_xyz[:, :3]
C_xyz, C_props = read_ply_ascii(fc.FR + "/floor_rescue_band_improved.ply")  # LoFTR g4 split
C_xyz3 = C_xyz[:, :3]

levers = {
    "A_planesweep_%s" % ps_grid: A_xyz3,
    "B_loftr_native1024":        B_xyz3,
    "C_loftr_g4split":           C_xyz3,
}

print("=== per-lever floor-band points & 5cm coverage ===")
lever_cells = {}
for name, xyz in levers.items():
    c = cells_of(xyz)
    lever_cells[name] = c
    new = c - sift_cells
    print(f"{name:26s} pts={len(xyz):6d}  cells={len(c):5d}  new_vs_SIFT={len(new):5d} ({len(new)*CELL*CELL:.3f} m2)")

# ---- union coverage (dedup-invariant) ----
rescue_cells = set().union(*lever_cells.values())
rescue_new = rescue_cells - sift_cells
union_all = sift_cells | rescue_cells
print("\n=== MERGED (A u B u C) ===")
print(f"rescue union cells        : {len(rescue_cells)}   [current LoFTR baseline 793]")
print(f"rescue NEW vs SIFT        : {len(rescue_new)}   area={len(rescue_new)*CELL*CELL:.3f} m2")
print(f"SIFT cells                : {len(sift_cells)}   area={len(sift_cells)*CELL*CELL:.3f} m2")
print(f"SIFT u rescue TOTAL cells : {len(union_all)}   area={len(union_all)*CELL*CELL:.3f} m2")
print(f"  => floor footprint gain over SIFT-alone: +{(len(union_all)-len(sift_cells))/len(sift_cells)*100:.1f}%")

# ---- marginal attribution: cells reachable ONLY by one lever (among rescue) ----
print("\n=== marginal cell attribution (among rescue levers) ===")
names = list(lever_cells.keys())
for name in names:
    others = set().union(*[lever_cells[o] for o in names if o != name])
    only = lever_cells[name] - others
    only_new = only - sift_cells   # cells only this lever provides AND not in SIFT
    print(f"{name:26s} cells_only_here={len(only):5d}  of_which_new_vs_SIFT={len(only_new):5d}")

# incremental value: add levers in an order, watch new-vs-SIFT grow
print("\n=== incremental new-vs-SIFT cells (greedy add order) ===")
order = ["A_planesweep_%s" % ps_grid, "C_loftr_g4split", "B_loftr_native1024"]
acc = set()
prev_new = 0
for name in order:
    acc |= lever_cells[name]
    cur_new = len(acc - sift_cells)
    print(f"+ {name:26s} -> cumulative new_vs_SIFT={cur_new:5d}  (delta +{cur_new-prev_new})")
    prev_new = cur_new

# ---- spatially-deduped merged point count (in-plane voxel) ----
def dedup(xyz_list, res):
    allp = np.vstack(xyz_list)
    uv = np.stack([allp @ u, allp @ v], 1)
    keys = np.floor(uv / res).astype(np.int64)
    seen = set(); keep = []
    for i, k in enumerate(map(tuple, keys)):
        if k not in seen: seen.add(k); keep.append(i)
    return len(keep), len(allp)
for res in (0.005, 0.01):
    kept, raw = dedup([A_xyz3, B_xyz3, C_xyz3], res)
    print(f"\nmerged points  raw_sum={raw}  dedup@{int(res*1000)}mm_inplane={kept}")

# density over union footprint
kept5, raw = dedup([A_xyz3, B_xyz3, C_xyz3], 0.005)
area = len(union_all)*CELL*CELL
print(f"\n=== density ===")
print(f"SIFT density              : {len(sift_xyz)/ (len(sift_cells)*CELL*CELL):.0f} pts/m2 (over SIFT footprint {len(sift_cells)*CELL*CELL:.2f} m2)")
print(f"merged density (dedup5mm) : {kept5/area:.0f} pts/m2 (over union footprint {area:.2f} m2)")

out = {
  "ps_grid": ps_grid,
  "sift_cells": len(sift_cells), "sift_pts": len(sift_xyz),
  "loftr_baseline_cells": 793,
  "per_lever": {name: {"pts": int(len(levers[name])), "cells": len(lever_cells[name]),
                        "new_vs_sift": len(lever_cells[name]-sift_cells)} for name in names},
  "merged": {
    "rescue_union_cells": len(rescue_cells),
    "rescue_new_vs_sift_cells": len(rescue_new),
    "rescue_new_vs_sift_m2": round(len(rescue_new)*CELL*CELL,4),
    "sift_union_rescue_cells": len(union_all),
    "sift_union_rescue_m2": round(len(union_all)*CELL*CELL,4),
    "footprint_gain_over_sift_pct": round((len(union_all)-len(sift_cells))/len(sift_cells)*100,1),
    "merged_pts_dedup5mm": kept5,
    "merged_pts_raw_sum": raw,
  },
}
json.dump(out, open(fc.FR + "/fr_merge_stats_%s.json" % ps_grid, "w"), indent=1)
print("\nwrote fr_merge_stats_%s.json" % ps_grid)
