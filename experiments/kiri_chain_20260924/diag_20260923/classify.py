"""Why is a hole a hole? For every 1.5 mm ray along the plane normal that finds NO surface in the thr=1 region mesh,
walk the MC cubes the ray crosses within +-TRUNC of the plane and classify (Open3D MC semantics, VoxelBlockGridImpl.h:1486-1491):
  X  : some cube has all 8 corner weights > 1 AND a sign change      (MC should have emitted -> should not be a hole)
  B1 : a cube with a sign change exists but its min corner weight == 1 (blocked by the strict >1.0 threshold)
  B0 : a cube with a sign change exists but has a corner with weight 0 / missing block
  C  : no sign change anywhere in the column and every corner weight >= 2 (observed >=2x, no zero crossing)  [+/- sign split]
  A  : every corner in the column has weight 0 (never observed)
  D  : no sign change, mixed weights (some 0/1)
Layout check first: trilinear tsdf at the thr1 mesh vertices must be ~0 with the [z,y,x] block layout and not with [x,y,z]."""
import numpy as np, open3d as o3d, json, sys
from scipy import ndimage as ndi
REG = sys.argv[1]; TAG = sys.argv[2]
CELL = 0.02; EROD = 5; STEP = 0.0015; WIN = 0.15
R = json.load(open("regions_planes.json")); meta = json.load(open(f"regionmeta_{REG}.json")); mask = np.load(f"regionmask_{REG}.npy")
nw = np.array(R["wall"]["n"]); dw = R["wall"]["d"]; e2w = np.array(R["wall"]["e2"]); nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]
e1f = np.array(R["floor"]["e1"]); e2f = np.array(R["floor"]["e2"])
if REG == "wall": n_, d_ = nw, dw; A = np.stack([n_, nf, e2w]); rhs = lambda u, v: np.stack([np.full_like(u, -d_), u - df, v], 1)
elif REG == "white": n_ = np.array(R["white"]["n"]); d_ = R["white"]["d"]; A = np.stack([n_, nf, e2w]); rhs = lambda u, v: np.stack([np.full_like(u, -d_), u - df, v], 1)
else: n_, d_ = nf, df; A = np.stack([nf, e1f, e2f]); rhs = lambda u, v: np.stack([np.full_like(u, -df), u, v], 1)
Ainv = np.linalg.inv(A); to3d = lambda u, v: (Ainv @ rhs(u, v).T).T
z = np.load(f"vbg_{TAG}.npz"); keys = z["keys"]; TS = z["tsdf"]; W = z["weight"].astype(np.int32); VOX = float(z["vox"]); BR = int(z["br"])
TRUNC = float(TAG.split("_t")[1].split("_")[0])
kd = {tuple(k): i for i, k in enumerate(keys)}
def lookup(I, layout="zyx"):
    bk = np.floor_divide(I, BR); lc = I - bk * BR
    bi = np.fromiter((kd.get((a, b, c), -1) for a, b, c in bk), np.int64, len(bk))
    t = np.zeros(len(I), np.float32); w = np.zeros(len(I), np.int32); ok = bi >= 0
    if layout == "zyx": t[ok] = TS[bi[ok], lc[ok, 2], lc[ok, 1], lc[ok, 0]]; w[ok] = W[bi[ok], lc[ok, 2], lc[ok, 1], lc[ok, 0]]
    else: t[ok] = TS[bi[ok], lc[ok, 0], lc[ok, 1], lc[ok, 2]]; w[ok] = W[bi[ok], lc[ok, 0], lc[ok, 1], lc[ok, 2]]
    return t, w
res = {}
# layout control: tsdf interpolated at mesh vertices
mv = np.asarray(o3d.io.read_triangle_mesh(f"mesh_{TAG}_thr1_raw.ply").vertices)[::200]
for lay in ("zyx", "xyz"):
    g = mv / VOX; i0 = np.floor(g).astype(np.int64); f = g - i0; acc = np.zeros(len(g))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                t, _ = lookup(i0 + np.array([dx, dy, dz]), lay)
                acc += t * (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
    res[f"layout_check_{lay}_median_abs_tsdf_at_vertices"] = float(np.median(np.abs(acc)))
print(res, flush=True)
# rays (same grid as holes.py) and the thr1 hole set
me = ndi.binary_erosion(mask, iterations=EROD); iu, iv = np.nonzero(me)
gg = np.arange(STEP / 2, CELL, STEP)
uu = (meta["u0"] + iu * CELL)[:, None] + np.repeat(gg, len(gg))[None, :]; vv = (meta["v0"] + iv * CELL)[:, None] + np.tile(gg, len(gg))[None, :]
X = to3d(uu.ravel(), vv.ravel())
def covered(meshfile):
    m = o3d.io.read_triangle_mesh(meshfile); scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(m))
    cov = np.zeros(len(X), bool)
    for s in range(0, len(X), 4_000_000):
        O = X[s:s + 4_000_000] + 0.4 * n_; r = scn.list_intersections(o3d.core.Tensor(np.concatenate([O, np.tile(-n_, (len(O), 1))], 1).astype(np.float32)))
        t = r["t_hit"].numpy(); rid = r["ray_ids"].numpy() + s; cov[rid[np.abs(t - 0.4) < WIN]] = True
    return cov
cov1 = covered(f"mesh_{TAG}_thr1_raw.ply")
rng = np.random.default_rng(0)
def classify(idx):
    P = X[idx]; cls = np.full(len(idx), "", object); sgn = np.zeros(len(idx), np.int8)
    # cubes crossed: sample the segment +-TRUNC around the plane at quarter-voxel steps
    ts = np.arange(-TRUNC, TRUNC + 1e-9, VOX / 4)
    has_X = np.zeros(len(idx), bool); has_B1 = np.zeros(len(idx), bool); has_B0 = np.zeros(len(idx), bool)
    all_w0 = np.ones(len(idx), bool); all_ge2 = np.ones(len(idx), bool); any_pos = np.zeros(len(idx), bool); any_neg = np.zeros(len(idx), bool)
    seen = [set() for _ in range(len(idx))]
    for t in ts:
        c0 = np.floor((P + t * n_) / VOX).astype(np.int64)
        tt = []; ww = []
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    a, b = lookup(c0 + np.array([dx, dy, dz])); tt.append(a); ww.append(b)
        tt = np.stack(tt, 1); ww = np.stack(ww, 1)
        obs = ww > 0
        pos = np.any(obs & (tt >= 0), 1); neg = np.any(obs & (tt < 0), 1); change = pos & neg
        mw = ww.min(1)
        has_X |= change & (mw > 1); has_B1 |= change & (mw == 1); has_B0 |= change & (mw == 0)
        all_w0 &= ~obs.any(1); all_ge2 &= (mw >= 2); any_pos |= pos & (mw >= 2); any_neg |= neg & (mw >= 2)
    cls[:] = "D"; cls[all_w0] = "A"; cls[~has_X & ~has_B1 & ~has_B0 & all_ge2] = "C"; cls[~has_X & ~has_B1 & has_B0] = "B0"; cls[~has_X & has_B1] = "B1"; cls[has_X] = "X"
    csign = np.where(any_pos & ~any_neg, "+", np.where(any_neg & ~any_pos, "-", "mixed"))
    out = {k: float((cls == k).mean()) for k in ("X", "B1", "B0", "C", "A", "D")}
    # ray-level refinement: trilinear tsdf along the ray itself; a crossing is attributed to the min corner weight of its cube
    fprev = None; qprev = None; rX = np.zeros(len(idx), bool); rB1 = np.zeros(len(idx), bool); rB0 = np.zeros(len(idx), bool)
    r_all_ge2 = np.ones(len(idx), bool); r_all_w0 = np.ones(len(idx), bool); rpos = np.zeros(len(idx), bool); rneg = np.zeros(len(idx), bool)
    for t in ts:
        g = (P + t * n_) / VOX; i0 = np.floor(g).astype(np.int64); f = g - i0; acc = np.zeros(len(P)); mw = np.full(len(P), 1 << 30); anyobs = np.zeros(len(P), bool)
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    a, b = lookup(i0 + np.array([dx, dy, dz]))
                    acc += a * (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                    mw = np.minimum(mw, b); anyobs |= b > 0
        if fprev is not None:
            cr = (np.sign(acc) != np.sign(fprev)) & (acc != 0); q = np.minimum(mw, qprev)
            rX |= cr & (q > 1); rB1 |= cr & (q == 1); rB0 |= cr & (q == 0)
        r_all_ge2 &= mw >= 2; r_all_w0 &= ~anyobs; rpos |= (acc >= 0) & (mw >= 2); rneg |= (acc < 0) & (mw >= 2)
        fprev = acc; qprev = mw
    rc = np.full(len(idx), "D", object); rc[r_all_w0] = "A"; rc[~rX & ~rB1 & ~rB0 & r_all_ge2] = "C"; rc[~rX & ~rB1 & rB0] = "B0"; rc[~rX & rB1] = "B1"; rc[rX] = "X"
    for k in ("X", "B1", "B0", "C", "A", "D"): out["ray_" + k] = float((rc == k).mean())
    Cr = rc == "C"; out["ray_C_all_plus"] = float((Cr & rpos & ~rneg).sum() / max(Cr.sum(), 1)); out["ray_C_all_minus"] = float((Cr & rneg & ~rpos).sum() / max(Cr.sum(), 1))
    Cm = cls == "C"
    out["C_sign_all_plus"] = float(((csign == "+") & Cm).sum() / max(Cm.sum(), 1)); out["C_sign_all_minus"] = float(((csign == "-") & Cm).sum() / max(Cm.sum(), 1))
    return out
hole = np.flatnonzero(~cov1); allr = np.arange(len(X))
hs = rng.choice(hole, min(len(hole), 150000), replace=False) if len(hole) else hole
res["n_rays"] = int(len(X)); res["hole_frac_thr1_raw"] = float(len(hole) / len(X))
res["hole_rays_class"] = classify(hs) if len(hs) else None
res["all_rays_class"] = classify(rng.choice(allr, 150000, replace=False))
print(json.dumps(res, indent=1), flush=True)
json.dump(res, open(f"classify_{TAG}.json", "w"), indent=1)
