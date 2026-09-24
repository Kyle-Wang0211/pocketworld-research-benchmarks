"""How far does production Taubin x10 move vertices? raw MC vs (cluster<100 removal + Taubin x10) of the SAME mesh; vertex arrays
stay index-aligned (remove_triangles_by_mask keeps vertices). Also the normal component (what changes the shape) vs tangential."""
import numpy as np, open3d as o3d, json, sys
res = {}
for name, raw, post in [(a.split("=")[0], *a.split("=")[1].split(",")) for a in sys.argv[1:]]:
    mr = o3d.io.read_triangle_mesh(raw); mp = o3d.io.read_triangle_mesh(post)
    Vr = np.asarray(mr.vertices); Vp = np.asarray(mp.vertices); assert len(Vr) == len(Vp)
    used = np.zeros(len(Vr), bool); used[np.asarray(mp.triangles).ravel()] = True
    mr.compute_vertex_normals(); Nr = np.asarray(mr.vertex_normals)
    d = Vp[used] - Vr[used]; mag = np.linalg.norm(d, axis=1); nor = np.abs(np.sum(d * Nr[used], 1))
    res[name] = dict(n=int(used.sum()), disp_mmCD_p50_p90_p99=(np.percentile(mag, [50, 90, 99]) * 1000).round(3).tolist(),
                     normal_disp_mmCD_p50_p90_p99=(np.percentile(nor, [50, 90, 99]) * 1000).round(3).tolist(), rms_normal_disp_mmCD=float(np.sqrt(np.mean(nor ** 2)) * 1000))
    print(name, res[name], flush=True)
json.dump(res, open("taubin_disp.json", "w"), indent=1)
