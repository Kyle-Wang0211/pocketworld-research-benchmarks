#!/usr/bin/env python3
"""Positive control for space carving, before it is allowed to judge anything.

Synthetic scene: a wall at z = 3 m, and a 0.3 x 0.3 m MEMBRANE floating at z = 1.5 m in front of
part of it -- the shape of a white-wall sticking artefact. Scan A (origin at 0) contains the
membrane. Scan B (origin at 0) contains the wall BEHIND the membrane, so B's rays pass straight
through the membrane's voxels.

Expected: space_carving=False keeps the membrane; space_carving=True deletes it.
If that does not happen, the knob is not doing what the paper says and nothing downstream counts.
"""
import numpy as np, vdbfusion

VOX, TRUNC = 0.01, 0.03
g = np.arange(-0.6, 0.6, 0.004)
X, Y = np.meshgrid(g, g)
wall = np.stack([X.ravel(), Y.ravel(), np.full(X.size, 3.0)], 1)
inside = (np.abs(wall[:, 0]) < 0.15) & (np.abs(wall[:, 1]) < 0.15)

gm = np.arange(-0.15, 0.15, 0.002)
Xm, Ym = np.meshgrid(gm, gm)
membrane = np.stack([Xm.ravel(), Ym.ravel(), np.full(Xm.size, 1.5)], 1)

scanA = np.vstack([membrane, wall[~inside]])          # sees the membrane, wall occluded behind it
scanB = wall                                           # sees the whole wall, rays pass through the membrane
O = np.zeros(3)

def count_membrane(vert):
    if len(vert) == 0: return 0
    v = np.asarray(vert)
    return int(((np.abs(v[:, 2] - 1.5) < 0.1)).sum())

for carve in (False, True):
    vol = vdbfusion.VDBVolume(voxel_size=VOX, sdf_trunc=TRUNC, space_carving=carve)
    vol.integrate(np.ascontiguousarray(scanA), O)
    vol.integrate(np.ascontiguousarray(scanB), O)
    vert, tri = vol.extract_triangle_mesh(fill_holes=False, min_weight=1.0)
    v = np.asarray(vert)
    nm = count_membrane(vert)
    nw = int((np.abs(v[:, 2] - 3.0) < 0.1).sum()) if len(v) else 0
    print(f"space_carving={carve!s:5}  total verts {len(vert):7d}   membrane(z~1.5) {nm:7d}   wall(z~3.0) {nw:7d}", flush=True)
