#!/usr/bin/env python3
"""Thin-band arbiter: keep only points within BAND of the graph-cut surface, on either side. Unlike the earlier
"on the surface OR inside the solid" rule, this also drops the layer hiding inside the solid, which is where a
ghost shell sits. Kept points are unchanged (no resampling, no recolouring)."""
import sys, os, json, numpy as np, open3d as o3d
MESH, CLOUD, OUT, TAG = sys.argv[1:5]
BAND = float(sys.argv[5]) if len(sys.argv) > 5 else 0.006
os.makedirs(OUT, exist_ok=True)
m=o3d.io.read_triangle_mesh(MESH)
if os.environ.get("MESH_FLIP_YZ")=="1":
    v=np.asarray(m.vertices); v[:,1]*=-1; v[:,2]*=-1; m.vertices=o3d.utility.Vector3dVector(v)
m.remove_degenerate_triangles(); m.remove_duplicated_vertices(); m.remove_unreferenced_vertices()
print("mesh %d verts %d tris"%(len(m.vertices),len(m.triangles)),flush=True)
pc=o3d.io.read_point_cloud(CLOUD); P=np.asarray(pc.points).astype(np.float32); C=(np.asarray(pc.colors)*255).astype(np.uint8)
sc=o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(m))
d=np.empty(len(P),np.float32)
for i in range(0,len(P),2_000_000):
    d[i:i+2_000_000]=sc.compute_distance(o3d.core.Tensor(P[i:i+2_000_000],dtype=o3d.core.Dtype.Float32)).numpy()
keep=d<=BAND
print("band %.0f mm: kept %d / %d (%.1f%%); distance p50 %.1f mm p90 %.1f mm"%(BAND*1000,keep.sum(),len(P),100*keep.mean(),np.median(d)*1000,np.percentile(d,90)*1000),flush=True)
pos=P[keep].copy(); pos[:,1]*=-1; pos[:,2]*=-1; pos=np.ascontiguousarray(pos.astype("<f4")); col=np.ascontiguousarray(C[keep])
pos.tofile(f"{OUT}/{TAG}.pos"); col.tofile(f"{OUT}/{TAG}.col")
lo,hi=np.percentile(pos,1,0),np.percentile(pos,99,0); med=np.median(pos,0)
json.dump({TAG:{"n":int(len(pos)),"center":((lo+hi)/2).tolist(),"ext":(hi-lo).tolist(),"med":med.astype(float).tolist(),
                "radius":float(np.percentile(np.linalg.norm(pos-med,axis=1),95))}},open(f"{OUT}/meta_{TAG}.json","w"))
print("wrote",TAG,len(pos),flush=True)
