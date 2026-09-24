"""Holes as the viewer would see them, on the PRODUCTION nofill mesh:
(1) boundary-edge density per region; (2) from the real camera poses, fraction of region pixels whose ray passes the
region surface without hitting the mesh (no hit, or first hit > GAP behind the plane / coarse surface) = see-through;
(3) vertex colour darkness per region. Region labels = labels.npz (plane+polygon+occlusion)."""
import numpy as np, open3d as o3d, json, sys, time, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_camera_parameters
MESH = sys.argv[1]; OUT = sys.argv[2]; STEP = int(sys.argv[3]) if len(sys.argv) > 3 else 3
OF = "/root/arm_full_ep0_tsdf"; GAP = 0.1
R = json.load(open("regions_planes.json")); PL = np.load("polygons.npz")
nw = np.array(R["wall"]["n"]); dw = R["wall"]["d"]; e2w = np.array(R["wall"]["e2"])
nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]; e1f = np.array(R["floor"]["e1"]); e2f = np.array(R["floor"]["e2"]); gf = R["floor"]["grid"]
L = np.load("labels4.npz")["labels"]; nW = np.array(R["white"]["n"]); dW = R["white"]["d"]
t0 = time.time(); m = o3d.io.read_triangle_mesh(MESH); V = np.asarray(m.vertices); T = np.asarray(m.triangles).astype(np.int64)
Cv = np.asarray(m.vertex_colors) if m.has_vertex_colors() else None
print("loaded", len(V), len(T), f"{time.time()-t0:.0f}s", flush=True)
def region_of(P):
    lab = np.zeros(len(P), np.int8)
    def inpoly(mask, meta, u, v):
        iu = ((u - meta[0]) / 0.02).astype(int); iv = ((v - meta[1]) / 0.02).astype(int); ok = (iu >= 0) & (iu < mask.shape[0]) & (iv >= 0) & (iv < mask.shape[1])
        r = np.zeros(len(u), bool); r[ok] = mask[iu[ok], iv[ok]]; return r
    h = P @ nf + df
    lab[(np.abs(h) < 0.05) & inpoly(PL["floor"], PL["floor_meta"], P @ e1f, P @ e2f)] = 2
    lab[(np.abs(P @ nw + dw) < 0.1) & inpoly(PL["wall"], PL["wall_meta"], h, P @ e2w)] = 1
    a = P @ e1f; b = P @ e2f
    lab[(a > gf["a0"] + 1.5) & (a < gf["a0"] + 3.9) & (b > gf["b0"] + 3.3) & (b < gf["b0"] + 6.9) & (h > 0.03) & (h < 2.0)] = 3
    return lab
res = {}
# (1) boundary edges
N = np.int64(len(V))
e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]); e.sort(1); key = e[:, 0] * N + e[:, 1]; del e
key.sort(); first = np.r_[True, key[1:] != key[:-1]]; idx = np.flatnonzero(first); cnt = np.diff(np.r_[idx, len(key)])
bkey = key[idx[cnt == 1]]; nonman = int((cnt > 2).sum()); del key, first, idx, cnt
ba = bkey // N; bb = bkey % N; mid = 0.5 * (V[ba] + V[bb]); blab = region_of(mid)
# triangle area per region (for density)
tc = (V[T[:, 0]] + V[T[:, 1]] + V[T[:, 2]]) / 3; tl = region_of(tc)
ar = 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1)
names = {1: "wall", 2: "floor", 3: "suitcase", 0: "other"}
for c, n in names.items():
    A = float(ar[tl == c].sum()); nb = int((blab == c).sum())
    res[n] = dict(mesh_area_CD2=A, boundary_edges=nb, boundary_edges_per_CD2=nb / max(A, 1e-9))
res["total"] = dict(boundary_edges=int(len(bkey)), nonmanifold_edges=nonman)
print(json.dumps(res), flush=True)
del tc, ar, mid
# (3) vertex colour darkness
if Cv is not None:
    vl = region_of(V); lum = Cv @ np.array([0.299, 0.587, 0.114])
    for c, n in names.items():
        l = lum[vl == c]
        if len(l): res[n].update(vcol_lum_p1_p5_p50=np.percentile(l, [1, 5, 50]).round(3).tolist(), vcol_frac_lt_0p25=float((l < 0.25).mean()))
    del vl, lum
# (2) see-through from camera poses
scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(T.astype(np.uint32)))
del T
cm = o3d.io.read_triangle_mesh("coarse12_thr0.ply"); scc = o3d.t.geometry.RaycastingScene(); scc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(cm))
uu, vv = np.meshgrid(np.arange(768) + 0.0, np.arange(576) + 0.0)
st = {n: [0, 0] for n in ("wall", "floor", "suitcase", "white")}; per_view = []
for k in range(0, 132, STEP):
    K, E, _, _ = read_camera_parameters(f"{OF}/cams/{k:08d}_cam.txt"); Rw = E[:3, :3].astype(np.float64); C = -Rw.T @ E[:3, 3]
    rw = (Rw.T @ (np.linalg.inv(K.astype(np.float64)) @ np.stack([uu.ravel(), vv.ravel(), np.ones(uu.size)]))).T; nr = np.linalg.norm(rw, axis=1); dirs = rw / nr[:, None]
    rays = o3d.core.Tensor(np.concatenate([np.tile(C, (len(dirs), 1)), dirs], 1).astype(np.float32))
    zp = scn.cast_rays(rays)["t_hit"].numpy() / nr; zc = scc.cast_rays(rays)["t_hit"].numpy() / nr
    lab = L[k].ravel(); row = dict(view=k)
    for code, n, pl in [(1, "wall", (nw, dw)), (2, "floor", (nf, df)), (3, "suitcase", None), (4, "white", (nW, dW))]:
        msk = lab == code
        if msk.sum() == 0: continue
        zref = (-(pl[0] @ C + pl[1]) / (rw[msk] @ pl[0])) if pl is not None else zc[msk]
        see = ~np.isfinite(zp[msk]) | (zp[msk] > zref + GAP)
        st[n][0] += int(msk.sum()); st[n][1] += int(see.sum()); row[n] = [int(msk.sum()), int(see.sum())]
        if k in (0, 20, 90, 131) and n == "white":
            img = cv2.imread(f"{OF}/images/{k:08d}.jpg"); s = np.zeros(len(lab), bool); s[np.flatnonzero(msk)[see]] = True
            img.reshape(-1, 3)[s] = (255, 0, 255); cv2.imwrite(f"{OUT}_view{k}.png", img)
    per_view.append(row)
res.setdefault("white", {})
for n in st: res[n]["seethrough_frac_camera_views"] = st[n][1] / max(st[n][0], 1); res[n]["seethrough_pixels"] = st[n]
res["per_view"] = per_view
json.dump(res, open(OUT + ".json", "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "per_view"}, indent=1))
