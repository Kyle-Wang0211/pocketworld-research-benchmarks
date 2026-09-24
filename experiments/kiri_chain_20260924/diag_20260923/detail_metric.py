"""Reproducible fine relief (split-half): sample points on a heavily smoothed reference surface; for each mesh measure the signed
normal offset h(p) to the nearest surface within +-WIN; high-pass hp = h - mean(h over the K nearest samples).
signal = cov(hp_even, hp_odd) = relief that two DISJOINT view halves agree on; noise = var(hp_even - hp_odd)/2.
Negative control: flat floor patch (signal should stay ~0 at all voxel sizes). Positive control: coarse voxels must lose signal."""
import numpy as np, open3d as o3d, json, sys
from scipy.spatial import cKDTree
BOX = sys.argv[1]; REF = sys.argv[2]; PAIRS = sys.argv[3:]      # PAIRS: label=meshA,meshB[,meshF]
WIN = 0.03; KNN = 24; SPACING = 0.003
import os; SINGLE = os.environ.get("SINGLE", "1") == "1"
ref = o3d.io.read_triangle_mesh(REF)
tc, cn, _ = ref.cluster_connected_triangles(); tc = np.asarray(tc); cn = np.asarray(cn); ref.remove_triangles_by_mask(cn[tc] < 1000); ref.remove_unreferenced_vertices()
ref = ref.filter_smooth_taubin(number_of_iterations=200); ref.compute_vertex_normals()
pcd = o3d.geometry.PointCloud(ref.vertices); pcd.normals = ref.vertex_normals; pcd = pcd.voxel_down_sample(SPACING)
P = np.asarray(pcd.points); N = np.asarray(pcd.normals); N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
print(BOX, "reference samples", len(P), flush=True)
nb = cKDTree(P).query(P, k=KNN)[1]
def offsets(path):
    m = o3d.io.read_triangle_mesh(path); scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(m))
    h = np.full(len(P), np.nan); cnt = np.zeros(len(P), np.int32)
    for s in range(0, len(P), 2_000_000):
        O = P[s:s + 2_000_000] - WIN * N[s:s + 2_000_000]; D = N[s:s + 2_000_000]
        r = scn.list_intersections(o3d.core.Tensor(np.concatenate([O, D], 1).astype(np.float32)))
        t = r["t_hit"].numpy() - WIN; rid = r["ray_ids"].numpy() + s; ok = np.abs(t) <= WIN; t = t[ok]; rid = rid[ok]; np.add.at(cnt, rid, 1)
        o = np.lexsort((np.abs(t), rid)); t = t[o]; rid = rid[o]; first = np.r_[True, rid[1:] != rid[:-1]]
        h[rid[first]] = t[first]
    if SINGLE: h[cnt != 1] = np.nan      # keep only rays that meet exactly one surface (no layer jumping)
    return h
def hp(h):
    nbv = h[nb]; mu = np.nanmean(nbv, 1); cnt = np.sum(~np.isnan(nbv), 1)
    out = h - mu; out[cnt < KNN // 2] = np.nan; return out
res = {}
for spec in PAIRS:
    label, files = spec.split("="); fs = files.split(",")
    hA = hp(offsets(fs[0])); hB = hp(offsets(fs[1])); ok = ~np.isnan(hA) & ~np.isnan(hB)
    a = hA[ok] - hA[ok].mean(); b = hB[ok] - hB[ok].mean()
    sig = float(np.mean(a * b)); noise = float(np.var(a - b) / 2)
    r = dict(n=int(ok.sum()), cover=float(ok.mean()), signal_rms_mmCD=float(np.sign(sig) * np.sqrt(abs(sig)) * 1000), noise_rms_mmCD=float(np.sqrt(noise) * 1000),
             corr=float(np.corrcoef(a, b)[0, 1]), total_rms_A_mmCD=float(np.sqrt(np.mean(a * a)) * 1000))
    if len(fs) > 2:
        hF = hp(offsets(fs[2])); okF = ok & ~np.isnan(hF); f = hF[okF] - hF[okF].mean(); r["rms_full_mmCD"] = float(np.sqrt(np.mean(f * f)) * 1000)
    res[label] = r; print(BOX, label, r, flush=True)
json.dump(res, open(f"detail_{BOX}_{os.environ.get('TAGM','x')}.json", "w"), indent=1)
