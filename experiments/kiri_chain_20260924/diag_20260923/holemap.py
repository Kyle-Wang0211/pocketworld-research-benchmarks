"""Hole map on the region: per 1.5mm ray -> hole / first hit front-facing / first hit back-facing; hole component stats; PNG."""
import numpy as np, open3d as o3d, json, sys, cv2
from scipy import ndimage as ndi
REG = sys.argv[1]; MESH = sys.argv[2]; OUT = sys.argv[3]
CELL = 0.02; EROD = 5; STEP = 0.0015; WIN = 0.15
R = json.load(open("regions_planes.json")); meta = json.load(open(f"regionmeta_{REG}.json")); mask = np.load(f"regionmask_{REG}.npy")
nw = np.array(R["wall"]["n"]); dw = R["wall"]["d"]; e2w = np.array(R["wall"]["e2"])
nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]; e1f = np.array(R["floor"]["e1"]); e2f = np.array(R["floor"]["e2"])
if REG == "wall": A = np.stack([nw, nf, e2w]); rhs = lambda u, v: np.stack([np.full_like(u, -dw), u - df, v], 1); n_ = nw
elif REG == "white": n_ = np.array(R["white"]["n"]); d_ = R["white"]["d"]; A = np.stack([n_, nf, e2w]); rhs = lambda u, v: np.stack([np.full_like(u, -d_), u - df, v], 1)
else: A = np.stack([nf, e1f, e2f]); rhs = lambda u, v: np.stack([np.full_like(u, -df), u, v], 1); n_ = nf
Ainv = np.linalg.inv(A); to3d = lambda u, v: (Ainv @ rhs(u, v).T).T
me = ndi.binary_erosion(mask, iterations=EROD)
um, vm = np.nonzero(me); ns = int(round(CELL / STEP))
H = (um.max() - um.min() + 1) * ns; W = (vm.max() - vm.min() + 1) * ns
gi, gj = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
cu = um.min() + gi // ns; cv = vm.min() + gj // ns; inside = me[cu, cv]
u = meta["u0"] + um.min() * CELL + (gi + 0.5) * STEP; v = meta["v0"] + vm.min() * CELL + (gj + 0.5) * STEP
X = to3d(u[inside], v[inside])
m = o3d.io.read_triangle_mesh(MESH); V = np.asarray(m.vertices); T = np.asarray(m.triangles)
lo, hi = X.min(0) - 0.3, X.max(0) + 0.3; inb = np.all((V > lo) & (V < hi), 1); T = T[inb[T].all(1)]
tn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]); tn /= np.linalg.norm(tn, axis=1, keepdims=True) + 1e-30
scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.core.Tensor(V.astype(np.float32)), o3d.core.Tensor(T.astype(np.uint32)))
O = X + 0.4 * n_; D = np.tile(-n_, (len(X), 1))
r = scn.cast_rays(o3d.core.Tensor(np.concatenate([O, D], 1).astype(np.float32)))
t = r["t_hit"].numpy(); pid = r["primitive_ids"].numpy().astype(np.int64)
hit = np.abs(t - 0.4) < WIN
facing = np.zeros(len(X)); facing[hit] = tn[pid[hit]] @ n_          # +: normal points toward the camera side (+n)
state = np.zeros(len(X), np.int8); state[hit & (facing > 0)] = 1; state[hit & (facing <= 0)] = 2   # 0 hole, 1 front, 2 back
img = np.full((H, W), 3, np.int8); img[inside] = state
hole = img == 0; lab, nl = ndi.label(hole); sz = np.bincount(lab.ravel())[1:] * STEP * STEP
area = inside.sum() * STEP * STEP
res = dict(mesh=MESH, area_CD2=float(area), hole_frac=float((state == 0).mean()), firsthit_front_frac=float((state == 1).mean()), firsthit_back_frac=float((state == 2).mean()),
           n_holes=int(nl), holes_per_CD2=float(nl / area), hole_size_mm2CD_p50_p90_p99=(np.percentile(sz, [50, 90, 99]) * 1e6).round(2).tolist() if nl else None,
           holes_per_m2_AV=float(nl / area / 0.2664 ** 2))
print(json.dumps(res), flush=True)
col = np.zeros((H, W, 3), np.uint8); col[img == 1] = (200, 200, 200); col[img == 2] = (0, 0, 255); col[img == 0] = (0, 0, 0); col[img == 3] = (60, 60, 60)
cv2.imwrite(OUT + ".png", col[::-1])
c0 = H // 2; c1 = W // 2; cv2.imwrite(OUT + "_zoom.png", cv2.resize(col[::-1][c0 - 200:c0 + 200, c1 - 300:c1 + 300], (1200, 800), interpolation=cv2.INTER_NEAREST))
json.dump(res, open(OUT + ".json", "w"), indent=1)
