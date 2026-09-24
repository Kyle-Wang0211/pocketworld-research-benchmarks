# Where are the faces texrecon dropped? distance to nearest kept surface + largest pieces (centroid, mean normal, extent)
import numpy as np, trimesh, json
from scipy.spatial import cKDTree
src = trimesh.load("/root/tsdf_improve/kiri/out/kiri_v0.01_t0.04_w5.ply", process=False)
sc = trimesh.load("/root/tsdf_improve/tex_K1/K1_textured.obj", force="scene", process=False)
kept = trimesh.util.concatenate(list(sc.geometry.values()))
kc = kept.triangles_center; kt = cKDTree(kc)
d0, _ = kt.query(src.triangles_center, k=1); drop = d0 > 1e-4
dm = trimesh.Trimesh(src.vertices, src.faces[drop], process=False)
# distance from each dropped face to the nearest kept face centroid (kept faces are ~1cm, so <1.5cm ~ touching)
dd, _ = kt.query(dm.triangles_center, k=1)
A = dm.area_faces
out = {"dist_to_kept_mm_p50_p90": [float(np.percentile(dd, 50) * 1e3), float(np.percentile(dd, 90) * 1e3)]}
for lo, hi in [(0, .015), (.015, .05), (.05, .2), (.2, 9)]:
    s = (dd >= lo) & (dd < hi); out[f"area_share_{int(lo*1e3)}-{int(hi*1e3)}mm"] = round(float(A[s].sum() / A.sum()), 3)
cc = trimesh.graph.connected_components(dm.face_adjacency, nodes=np.arange(len(dm.faces)), min_len=1)
cc = sorted(cc, key=len, reverse=True)
big = []
for c in cc[:6]:
    c = np.asarray(c); w = A[c]
    ctr = (dm.triangles_center[c] * w[:, None]).sum(0) / w.sum()
    n = (dm.face_normals[c] * w[:, None]).sum(0); nn = np.linalg.norm(n)
    ext = dm.triangles_center[c].max(0) - dm.triangles_center[c].min(0)
    big.append(dict(faces=len(c), area_m2=round(float(w.sum()), 3), center=ctr.round(3).tolist(), mean_normal=(n / nn).round(3).tolist(),
                    normal_coherence=round(float(nn / w.sum()), 3), extent_m=ext.round(2).tolist(),
                    med_dist_to_kept_mm=round(float(np.median(dd[c]) * 1e3), 1)))
out["largest"] = big
out["share_of_dropped_area_in_top6"] = round(float(sum(b["area_m2"] for b in big) / A.sum()), 3)
out["share_in_pieces_le_10_faces"] = round(float(sum(A[np.asarray(c)].sum() for c in cc if len(c) <= 10) / A.sum()), 3)
print(json.dumps(out, indent=1))
json.dump(out, open("/root/tsdf_improve/tex_K1/where_dropped.json", "w"), indent=1)
