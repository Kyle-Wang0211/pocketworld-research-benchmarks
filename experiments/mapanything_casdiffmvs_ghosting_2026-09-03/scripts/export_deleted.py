#!/usr/bin/env python3
"""Export the points the graph cut DELETED (their own original colours) so the eye can see what visibility voting
threw away, plus stats on where they sit."""
import sys, json, numpy as np, open3d as o3d
MESH, CLOUD, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
TOL = float(sys.argv[5]) if len(sys.argv) > 5 else 0.01
from pathlib import Path
Path(OUT).mkdir(parents=True, exist_ok=True)
m = o3d.io.read_triangle_mesh(MESH); m.remove_degenerate_triangles(); m.remove_duplicated_vertices(); m.remove_unreferenced_vertices()
pc = o3d.io.read_point_cloud(CLOUD)
P = np.asarray(pc.points).astype(np.float32); C = (np.asarray(pc.colors)*255).astype(np.uint8)
scene = o3d.t.geometry.RaycastingScene(); scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(m))
d = np.empty(len(P), np.float32); o = np.empty(len(P), np.float32)
for i in range(0, len(P), 2_000_000):
    q = o3d.core.Tensor(P[i:i+2_000_000], dtype=o3d.core.Dtype.Float32)
    d[i:i+2_000_000] = scene.compute_distance(q).numpy(); o[i:i+2_000_000] = scene.compute_occupancy(q).numpy()
drop = ~((d <= TOL) | (o > 0))
print("deleted %d (%.2f%%)" % (drop.sum(), 100*drop.mean()), flush=True)
print("deleted distance to mesh: p10 %.0f p50 %.0f p90 %.0f mm" % tuple(np.percentile(d[drop],[10,50,90])*1000), flush=True)
# where: colour brightness (white wall is bright), and height
bright = C.astype(np.float32).mean(1)
print("brightness: all p50 %.0f | deleted p50 %.0f ; deleted share among bright(>170) %.2f%% vs among dark(<100) %.2f%%"
      % (np.median(bright), np.median(bright[drop]), 100*drop[bright>170].mean(), 100*drop[bright<100].mean()), flush=True)
pos = P[drop].copy(); pos[:,1]*=-1; pos[:,2]*=-1; pos=np.ascontiguousarray(pos.astype("<f4")); col=np.ascontiguousarray(C[drop])
pos.tofile(f"{OUT}/{TAG}.pos"); col.tofile(f"{OUT}/{TAG}.col")
lo,hi=np.percentile(pos,1,0),np.percentile(pos,99,0); med=np.median(pos,0); rad=float(np.percentile(np.linalg.norm(pos-med,axis=1),95))
json.dump({TAG:{"n":int(len(pos)),"center":((lo+hi)/2).tolist(),"ext":(hi-lo).tolist(),"med":med.astype(float).tolist(),"radius":rad}}, open(f"{OUT}/meta_{TAG}.json","w"))
print("wrote", TAG, len(pos), flush=True)
