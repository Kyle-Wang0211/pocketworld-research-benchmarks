#!/usr/bin/env python3
"""Colour the OpenMVS mesh with real photo colour: sample points on the mesh surface, then take each sample's
colour from the nearest point of OpenMVS's own dense cloud (which carries the photo RGB). Geometry is the mesh's;
colour is the pipeline's own. Also emits the dense cloud itself, so the same page can compare like with like."""
import sys, os, json, numpy as np, open3d as o3d
from scipy.spatial import cKDTree
MESH, DENSE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
NPTS = int(os.environ.get("SAMPLE_PTS", "40000000"))
os.makedirs(OUT, exist_ok=True)
def emit(tag, P, C):
    pos = P.astype(np.float32).copy(); pos[:,1] *= -1; pos[:,2] *= -1
    pos = np.ascontiguousarray(pos.astype("<f4")); pos.tofile(f"{OUT}/{tag}.pos")
    np.ascontiguousarray(C.astype(np.uint8)).tofile(f"{OUT}/{tag}.col")
    lo, hi = np.percentile(pos,1,0), np.percentile(pos,99,0); med = np.median(pos,0)
    json.dump({tag: {"n": int(len(pos)), "center": ((lo+hi)/2).tolist(), "ext": (hi-lo).tolist(),
                     "med": med.astype(float).tolist(),
                     "radius": float(np.percentile(np.linalg.norm(pos-med,axis=1),95))}},
              open(f"{OUT}/meta_{tag}.json","w"))
    print("wrote", tag, len(pos), "med", np.round(med,3).tolist(), flush=True)
pc = o3d.io.read_point_cloud(DENSE)
D = np.asarray(pc.points); DC = (np.asarray(pc.colors)*255)
print("OpenMVS dense cloud:", len(D), "points, has colour:", pc.has_colors(), flush=True)
emit("openmvs_dense", D, DC)
m = o3d.io.read_triangle_mesh(MESH)
print("mesh:", len(m.vertices), "verts", len(m.triangles), "tris", flush=True)
s = m.sample_points_uniformly(number_of_points=NPTS)
P = np.asarray(s.points)
print("sampled", len(P), "surface points; colouring from the dense cloud", flush=True)
tree = cKDTree(D)
C = np.empty((len(P),3))
for i in range(0, len(P), 5_000_000):
    _, idx = tree.query(P[i:i+5_000_000], k=1, workers=-1)
    C[i:i+5_000_000] = DC[idx]
    print("  %d/%d" % (min(i+5_000_000,len(P)), len(P)), flush=True)
emit("openmvs_mesh_rgb", P, C)
