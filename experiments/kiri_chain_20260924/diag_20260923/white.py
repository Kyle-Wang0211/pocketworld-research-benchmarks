"""Second (primary) low-texture region: the painted white wall S1, parallel to the fabric wall, ~0.41 CD in front of it.
Refit plane, polygon (height-above-floor x e2w), occupancy image, then add label code 4 into labels.npz -> labels4.npz."""
import numpy as np, open3d as o3d, json, cv2, sys
from scipy import ndimage as ndi
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_camera_parameters
R = json.load(open("regions_planes.json")); nw = np.array(R["wall"]["n"]); dw = R["wall"]["d"]; e2w = np.array(R["wall"]["e2"])
nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]
pc = o3d.io.read_point_cloud("/root/arm_full_ep0_tsdf/pc_t3.ply"); P = np.asarray(pc.points); Cc = np.asarray(pc.colors)
n = nw.copy(); d = dw - 0.408
for b in (0.05, 0.03, 0.02):
    sel = np.abs(P @ n + d) < b; Q = P[sel]; mu = Q.mean(0); _, _, Vt = np.linalg.svd(Q[::max(1, len(Q) // 2000000)] - mu, full_matrices=False)
    n2 = Vt[2]; n = n2 if n2 @ n > 0 else -n2; d = -n @ mu
sel = np.abs(P @ n + d) < 0.02; r = P[sel] @ n + d
print("white plane n", n.round(5), "d", round(d, 5), "angle to fabric wall", np.degrees(np.arccos(min(1, n @ nw))).round(2), "offset", round(float(np.median(P[sel] @ nw + dw)), 4), "inliers", int(sel.sum()), "resid std", r.std().round(4))
CELL = 0.02; sel = np.abs(P @ n + d) < 0.04; Q = P[sel]; Cq = Cc[sel]
u = Q @ nf + df; v = Q @ e2w
u0, v0 = np.percentile(u, 0.05) - 0.5, np.percentile(v, 0.05) - 0.5; H = int((np.percentile(u, 99.95) + 0.5 - u0) / CELL) + 1; W = int((np.percentile(v, 99.95) + 0.5 - v0) / CELL) + 1
iu = ((u - u0) / CELL).astype(int); iv = ((v - v0) / CELL).astype(int); ok = (iu >= 0) & (iu < H) & (iv >= 0) & (iv < W)
cnt = np.zeros((H, W), np.int32); np.add.at(cnt, (iu[ok], iv[ok]), 1); col = np.zeros((H, W, 3)); np.add.at(col, (iu[ok], iv[ok]), Cq[ok]); col /= np.maximum(cnt, 1)[..., None]
occ = cnt >= 3; lab, nl = ndi.label(occ); sz = ndi.sum(occ, lab, range(1, nl + 1)); big = lab == (1 + np.argmax(sz))
disk = lambda r: (np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r)
m = ndi.binary_closing(np.pad(big, 20), disk(15))[20:-20, 20:-20]; m = ndi.binary_fill_holes(m); m = ndi.binary_erosion(m, disk(3))
# keep only the WHITE part of the polygon: per-cell colour (empty cells take the nearest occupied cell colour), low saturation & bright
_, (ni, nj) = ndi.distance_transform_edt(~occ, return_indices=True); colf = col[ni, nj]
mx = colf.max(2); mn = colf.min(2); sat = (mx - mn) / np.maximum(mx, 1e-6)
whitec = (sat < 0.35) & (mx > 0.45)
whitec = ndi.binary_opening(whitec, disk(2)); m = m & whitec
lab2, nl2 = ndi.label(m); sz2 = ndi.sum(m, lab2, range(1, nl2 + 1)); m = lab2 == (1 + np.argmax(sz2)); m = ndi.binary_erosion(m, disk(2))
print("white polygon cells", int(m.sum()), "area CD^2", m.sum() * CELL ** 2, "height range", u0 + np.nonzero(m)[0].min() * CELL, u0 + np.nonzero(m)[0].max() * CELL, "occupied frac", round(float((occ & m).sum() / m.sum()), 3), "mean colour", col[m & occ].mean(0).round(3))
img = (np.clip(col[..., ::-1], 0, 1) * 255).astype(np.uint8); img[cnt < 3] = (255, 0, 255); img[~m & (cnt >= 3)] //= 3
cv2.imwrite("occ_white.png", cv2.resize(img[::-1], (W * 2, H * 2), interpolation=cv2.INTER_NEAREST))
R["white"] = dict(n=n.tolist(), d=float(d), e2=e2w.tolist()); json.dump(R, open("regions_planes.json", "w"), indent=1)
PL = dict(np.load("polygons.npz")); PL["white"] = m; PL["white_meta"] = np.array([u0, v0]); np.savez_compressed("polygons.npz", **PL)
# labels: code 4 where ray hits white plane inside polygon and coarse mesh shows nothing > M in front
L = np.load("labels.npz")["labels"]
cm = o3d.io.read_triangle_mesh("coarse12_thr0.ply"); scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(cm))
uu, vv = np.meshgrid(np.arange(768) + 0.0, np.arange(576) + 0.0); M = 0.08
for k in range(132):
    K, E, _, _ = read_camera_parameters(f"/root/arm_full_ep0_tsdf/cams/{k:08d}_cam.txt"); Rw = E[:3, :3].astype(np.float64); C = -Rw.T @ E[:3, 3]
    rw = (Rw.T @ (np.linalg.inv(K.astype(np.float64)) @ np.stack([uu.ravel(), vv.ravel(), np.ones(uu.size)]))).T; nr = np.linalg.norm(rw, axis=1)
    th = scn.cast_rays(o3d.core.Tensor(np.concatenate([np.tile(C, (len(rw), 1)), rw / nr[:, None]], 1).astype(np.float32)))["t_hit"].numpy(); zhit = np.where(np.isfinite(th), th / nr, np.inf)
    z = -(n @ C + d) / (rw @ n); X = C + z[:, None] * rw; uq = X @ nf + df; vq = X @ e2w
    iu = ((uq - u0) / CELL).astype(int); iv = ((vq - v0) / CELL).astype(int); okk = (iu >= 0) & (iu < H) & (iv >= 0) & (iv < W)
    inp = np.zeros(len(z), bool); inp[okk] = m[iu[okk], iv[okk]]
    w4 = (z > 0) & inp & (zhit >= z - M) & (L[k].ravel() != 3)
    lk = L[k].ravel().copy(); lk[w4] = 4; L[k] = lk.reshape(576, 768)
np.savez_compressed("labels4.npz", labels=L)
np.save("white_cellcolour.npy", colf)
print("pixels per code 1..4:", [int((L == c).sum()) for c in (1, 2, 3, 4)], "views with >=5000 white px", int(((L == 4).sum((1, 2)) >= 5000).sum()))
