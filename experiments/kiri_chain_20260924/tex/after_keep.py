# After the keep_unseen_faces run: GLB for the page, and where the faces the default run dropped are.
# Dropped faces = faces of the fused 1cm mesh whose centroid has no face in K1_textured.obj within 0.1 mm.
import numpy as np, trimesh, json
from scipy.spatial import cKDTree

src = trimesh.load("/root/tsdf_improve/kiri/out/kiri_v0.01_t0.04_w5.ply", process=False)
res = {"src_faces": int(len(src.faces))}
for tag in ("K1_textured", "K1keep_textured"):
    sc = trimesh.load(f"/root/tsdf_improve/tex_K1/{tag}.obj", force="scene", process=False)
    if tag == "K1keep_textured":
        sc.export(f"/root/tsdf_improve/tex_K1/{tag}.glb")
    m = trimesh.util.concatenate(list(sc.geometry.values()))
    res[tag] = {"faces": int(len(m.faces)), "geoms": len(sc.geometry)}
    if tag == "K1_textured":
        kept_c = m.triangles_center
print(res, flush=True)

d, _ = cKDTree(kept_c).query(src.triangles_center, k=1)
dropped = d > 1e-4
res["dropped_faces"] = int(dropped.sum())
res["dropped_area_m2"] = float(src.area_faces[dropped].sum())
res["src_area_m2"] = float(src.area_faces.sum())
# connected pieces of the dropped set, and how big they are
drop_mesh = trimesh.Trimesh(src.vertices, src.faces[dropped], process=False)
cc = trimesh.graph.connected_components(drop_mesh.face_adjacency, nodes=np.arange(len(drop_mesh.faces)), min_len=1)
sizes = np.sort(np.array([len(c) for c in cc]))[::-1]
res["dropped_components"] = int(len(sizes))
res["dropped_component_faces_top5"] = sizes[:5].tolist()
res["dropped_component_faces_p50"] = int(np.median(sizes))
drop_mesh.remove_unreferenced_vertices()
drop_mesh.export("/root/tsdf_improve/tex_K1/K1_dropped_faces.ply")
json.dump(res, open("/root/tsdf_improve/tex_K1/keep_vs_default.json", "w"), indent=1)
print(json.dumps(res, indent=1))
