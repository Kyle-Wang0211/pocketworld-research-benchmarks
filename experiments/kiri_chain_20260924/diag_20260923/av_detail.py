"""Literal check asked for: /root/tsdf/out/M_vox1.5_t7.5.ply vs M_vox3.0_t15.0.ply (AliceVision-depth arm, AV SfM frame,
voxel 1.5 / 3 mm IN AV UNITS). Local high-pass relief rms on the suitcase vs the flat floor patch (negative control), same
sample points as detail_metric.py (CD reference -> AV via the Sim3). Single meshes, so relief = detail + noise + grid artefacts;
only the suitcase/floor ratio is interpretable."""
import numpy as np, open3d as o3d, json
from scipy.spatial import cKDTree
S = json.load(open("sim3_cd2av.json")); s = S["s"]; R = np.array(S["R"]); t = np.array(S["t"])
WIN = 0.03 * s; KNN = 24; SPACING = 0.003
def samples(ref):
    m = o3d.io.read_triangle_mesh(ref); tc, cn, _ = m.cluster_connected_triangles(); tc = np.asarray(tc); cn = np.asarray(cn)
    m.remove_triangles_by_mask(cn[tc] < 1000); m.remove_unreferenced_vertices(); m = m.filter_smooth_taubin(number_of_iterations=200); m.compute_vertex_normals()
    p = o3d.geometry.PointCloud(m.vertices); p.normals = m.vertex_normals; p = p.voxel_down_sample(SPACING)
    P = np.asarray(p.points); N = np.asarray(p.normals); N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
    return (s * (R @ P.T)).T + t, (R @ N.T).T
regions = {r: samples(f"det_{r}_v0.003_t0.04_all_raw.ply") for r in ("suitcase", "floorbox")}
lo = np.min([P.min(0) for P, _ in regions.values()], 0) - 0.05; hi = np.max([P.max(0) for P, _ in regions.values()], 0) + 0.05
res = {}
for mname in ("M_vox3.0_t15.0", "M_vox1.5_t7.5"):
    m = o3d.io.read_triangle_mesh(f"/root/tsdf/out/{mname}.ply"); V = np.asarray(m.vertices); T = np.asarray(m.triangles)
    keep = np.all((V > lo) & (V < hi), 1); T = T[keep[T].all(1)]; del m
    scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(T.astype(np.uint32))); del V, T
    for r, (P, N) in regions.items():
        rr = scn.list_intersections(o3d.core.Tensor(np.concatenate([P - WIN * N, N], 1).astype(np.float32)))
        tt = rr["t_hit"].numpy() - WIN; rid = rr["ray_ids"].numpy(); ok = np.abs(tt) <= WIN; tt = tt[ok]; rid = rid[ok]
        o = np.lexsort((np.abs(tt), rid)); tt = tt[o]; rid = rid[o]; first = np.r_[True, rid[1:] != rid[:-1]]
        h = np.full(len(P), np.nan); h[rid[first]] = tt[first]
        nb = cKDTree(P).query(P, k=KNN)[1]; nbv = h[nb]; cnt = np.sum(~np.isnan(nbv), 1); hp = h - np.nanmean(nbv, 1); hp[cnt < KNN // 2] = np.nan
        res.setdefault(r, {})[mname] = dict(cover=float(np.mean(~np.isnan(hp))), hp_rms_mmAV=float(np.sqrt(np.nanmean(hp ** 2)) * 1000), hp=hp)
for r in res:
    a = res[r]["M_vox3.0_t15.0"].pop("hp"); b = res[r]["M_vox1.5_t7.5"].pop("hp"); ok = ~np.isnan(a) & ~np.isnan(b)
    res[r]["ratio_rms_1.5_over_3.0"] = res[r]["M_vox1.5_t7.5"]["hp_rms_mmAV"] / res[r]["M_vox3.0_t15.0"]["hp_rms_mmAV"]
    res[r]["corr_hp_1.5_vs_3.0"] = float(np.corrcoef(a[ok], b[ok])[0, 1])
print(json.dumps(res, indent=1)); json.dump(res, open("av_detail.json", "w"), indent=1)
