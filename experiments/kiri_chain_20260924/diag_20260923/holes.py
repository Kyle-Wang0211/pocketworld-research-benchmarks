"""Hole / layer metrics on a planar region, by rays along the plane normal through a 1.5 mm grid on the region polygon
(eroded by EROD cells from the region edge). Also: voxel weights on the plane, hole attribution, Taubin positive control."""
import numpy as np, open3d as o3d, json, sys, time
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
REG = sys.argv[1]; TAG = sys.argv[2]; PROD = len(sys.argv) > 3 and sys.argv[3] == "prod"
CELL = 0.02; EROD = 5; STEP = 0.0015; WIN = 0.15; LAYERGAP = 0.02 / 0.2664   # 2 cm in AV(SfM) units, as layer2F
R = json.load(open("regions_planes.json")); meta = json.load(open(f"regionmeta_{REG}.json")); mask = np.load(f"regionmask_{REG}.npy")
nw = np.array(R["wall"]["n"]); dw = R["wall"]["d"]; e2w = np.array(R["wall"]["e2"])
nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]; e1f = np.array(R["floor"]["e1"]); e2f = np.array(R["floor"]["e2"])
if REG == "wall":
    A = np.stack([nw, nf, e2w]); rhs = lambda u, v: np.stack([np.full_like(u, -dw), u - df, v], 1); n_ = nw; d_ = dw
elif REG == "white":
    n_ = np.array(R["white"]["n"]); d_ = R["white"]["d"]; A = np.stack([n_, nf, e2w]); rhs = lambda u, v: np.stack([np.full_like(u, -d_), u - df, v], 1)
else:
    A = np.stack([nf, e1f, e2f]); rhs = lambda u, v: np.stack([np.full_like(u, -df), u, v], 1); n_ = nf; d_ = df
Ainv = np.linalg.inv(A); to3d = lambda u, v: (Ainv @ rhs(u, v).T).T
me = ndi.binary_erosion(mask, iterations=EROD); iu, iv = np.nonzero(me)
g = np.arange(STEP / 2, CELL, STEP)
uu = (meta["u0"] + iu * CELL)[:, None] + np.repeat(g, len(g))[None, :]; vv = (meta["v0"] + iv * CELL)[:, None] + np.tile(g, len(g))[None, :]
X = to3d(uu.ravel(), vv.ravel()); print(REG, "sample rays", len(X), "area CD^2", me.sum() * CELL * CELL, flush=True)
lo, hi = X.min(0) - 0.3, X.max(0) + 0.3
def metrics(mesh, name):
    V = np.asarray(mesh.vertices); T = np.asarray(mesh.triangles)
    scn = o3d.t.geometry.RaycastingScene()
    scn.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(T.astype(np.uint32)))
    O = X + 0.4 * n_; D = np.tile(-n_, (len(X), 1))
    out = dict(name=name); cover = np.zeros(len(X), bool); multi = np.zeros(len(X), bool); nh = np.zeros(len(X), np.int32)
    for s in range(0, len(X), 4_000_000):
        res = scn.list_intersections(o3d.core.Tensor(np.concatenate([O[s:s+4_000_000], D[s:s+4_000_000]], 1).astype(np.float32)))
        t = res["t_hit"].numpy(); rid = res["ray_ids"].numpy() + s
        ok = np.abs(t - 0.4) < WIN; t = t[ok]; rid = rid[ok]
        cover[rid] = True; np.add.at(nh, rid, 1)
        if len(rid):
            o = np.lexsort((t, rid)); t = t[o]; rid = rid[o]
            first = np.r_[True, rid[1:] != rid[:-1]]; last = np.r_[rid[1:] != rid[:-1], True]
            span = t[last] - t[first]; multi[rid[first][span > LAYERGAP]] = True
    out["hole_frac"] = float(1 - cover.mean()); out["multilayer_frac_gt2cmAV"] = float(multi.mean()); out["hits_per_covered_ray_mean"] = float(nh[cover].mean())
    print(" ", out, flush=True); return out, cover, multi
res = {}
# negative / positive controls for the metric: perfect plane, and plane with 10% of triangles removed at random
um, vm = np.nonzero(me)
gu = np.arange(meta["u0"] + um.min() * CELL, meta["u0"] + (um.max() + 1) * CELL, 0.003); gv = np.arange(meta["v0"] + vm.min() * CELL, meta["v0"] + (vm.max() + 1) * CELL, 0.003)
GU, GV = np.meshgrid(gu, gv, indexing="ij"); P = to3d(GU.ravel(), GV.ravel()); nu, nv = GU.shape
idx = np.arange(nu * nv).reshape(nu, nv); a = idx[:-1, :-1].ravel(); b = idx[1:, :-1].ravel(); c = idx[:-1, 1:].ravel(); d = idx[1:, 1:].ravel()
Tp = np.concatenate([np.stack([a, b, c], 1), np.stack([b, d, c], 1)])
pm = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(P), o3d.utility.Vector3iVector(Tp))
res["ctrl_plane"] = metrics(pm, "control: complete synthetic plane (expect hole 0)")[0]
rng = np.random.default_rng(0); keep = rng.random(len(Tp)) > 0.10
pm2 = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(P), o3d.utility.Vector3iVector(Tp[keep]))
res["ctrl_plane_10pct"] = metrics(pm2, "control: synthetic plane, 10% triangles removed (expect hole ~0.10)")[0]
Pd = np.concatenate([P, P + 0.05 * n_]); pm3 = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(Pd), o3d.utility.Vector3iVector(np.concatenate([Tp, Tp + len(P)])))
res["ctrl_double"] = metrics(pm3, "control: two planes 5cm CD apart (expect multilayer 1.0)")[0]
covers = {}
for thr in ("1", "0"):
    m = o3d.io.read_triangle_mesh(f"mesh_{TAG}_thr{thr}_raw.ply")
    r, cov, mul = metrics(m, f"region MC thr{thr} raw"); res[f"thr{thr}_raw"] = r; covers[thr] = cov
    # production post-processing on the region mesh: cluster<100 removal + Taubin x10
    m2 = o3d.geometry.TriangleMesh(m)
    tc, cn, _ = m2.cluster_connected_triangles(); tc = np.asarray(tc); cn = np.asarray(cn)
    m2.remove_triangles_by_mask(cn[tc] < 100); m2 = m2.filter_smooth_taubin(number_of_iterations=10)
    r2, cov2, _ = metrics(m2, f"region MC thr{thr} + cc100 + taubin10"); res[f"thr{thr}_post"] = r2
    o3d.io.write_triangle_mesh(f"mesh_{TAG}_thr{thr}_post.ply", m2)
# hole attribution by voxel weights on the plane
z = np.load(f"vbg_{TAG}.npz"); keys = z["keys"]; W = z["weight"]; VOX = float(z["vox"]); BR = int(z["br"])
kd = {tuple(k): i for i, k in enumerate(keys)}
def wlookup(Y):
    vi = np.round(Y / VOX).astype(np.int64); bk = np.floor_divide(vi, BR); lc = vi - bk * BR
    out = np.zeros(len(Y), np.int32)
    bi = np.array([kd.get(tuple(k), -1) for k in bk])
    ok = bi >= 0; out[ok] = W[bi[ok], lc[ok, 2], lc[ok, 1], lc[ok, 0]]   # flat = x + BR*(y + BR*z) -> [z,y,x]
    return out
sub = np.arange(0, len(X), 4)   # every 4th ray (3 mm spacing ~ voxel)
wmax = np.max(np.stack([wlookup(X[sub] + t * n_) for t in (-0.006, -0.003, 0.0, 0.003, 0.006)]), 0)
w0 = wlookup(X[sub])
hist = lambda w: {"0": float((w == 0).mean()), "1": float((w == 1).mean()), "2": float((w == 2).mean()), "3-5": float(((w >= 3) & (w <= 5)).mean()), "6-10": float(((w >= 6) & (w <= 10)).mean()), ">10": float((w > 10).mean())}
res["weight_on_plane_voxel"] = hist(w0); res["weight_max_within_6mm_of_plane"] = hist(wmax)
c1 = covers["1"][sub]; c0 = covers["0"][sub]
res["attribution"] = dict(covered_thr1=float(c1.mean()), hole_thr1_filled_thr0=float((~c1 & c0).mean()), hole_both=float((~c1 & ~c0).mean()),
    hole_thr1__wmax_hist=hist(wmax[~c1]), hole_both__wmax_hist=hist(wmax[~c1 & ~c0]), covered_thr1__wmax_hist=hist(wmax[c1]))
print(json.dumps(res["weight_on_plane_voxel"]), "\n", json.dumps(res["weight_max_within_6mm_of_plane"]), "\n", json.dumps(res["attribution"], indent=1), flush=True)
if PROD:
    t0 = time.time(); pm = o3d.io.read_triangle_mesh("/root/tsdf_mesh_ep0/tsdf_mesh_full_ep0_v0.003_t0.04_nofill.ply")
    Vp = np.asarray(pm.vertices); Tpp = np.asarray(pm.triangles); print("prod loaded", len(Vp), len(Tpp), f"{time.time()-t0:.0f}s", flush=True)
    inb = np.all((Vp > lo) & (Vp < hi), 1); tk = inb[Tpp].all(1)
    crop = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(Vp), o3d.utility.Vector3iVector(Tpp[tk])); crop.remove_unreferenced_vertices()
    del pm, Vp, Tpp
    res["production_nofill_crop"] = metrics(crop, "PRODUCTION nofill mesh, same rays")[0]
    # positive control: my region thr1 + cc100 + taubin10 vertices vs production vertices (interior only)
    mine = np.asarray(o3d.io.read_triangle_mesh(f"mesh_{TAG}_thr1_post.ply").vertices)
    # interior = within the eroded polygon footprint and within 3cm of plane
    kdp = cKDTree(np.asarray(crop.vertices)); dd, _ = kdp.query(mine[np.abs(mine @ n_ + d_) < 0.03][::10])
    res["taubin_repro_nn_dist_CD"] = dict(p50=float(np.median(dd)), p90=float(np.percentile(dd, 90)), p99=float(np.percentile(dd, 99)), frac_lt_1e5=float((dd < 1e-5).mean()))
    print("positive control (mine post vs production):", res["taubin_repro_nn_dist_CD"], flush=True)
json.dump(res, open(f"holes_{TAG}.json", "w"), indent=1)
