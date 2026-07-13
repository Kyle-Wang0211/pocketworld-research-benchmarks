#!/usr/bin/env python3
"""Lever A: plane-sweep dense floor rescue on the KNOWN ARKit floor plane.

The floor plane (n, d) is certified (production_floor_stats.json). We lay a regular
grid of 3D points ON the plane and, for each, build a metric-rectified patch:
a small world-space square window (spanned by in-plane basis u,v) whose sub-samples
are projected into every 4K floor view (K_highres + ARKit pose) and bilinearly sampled.
Because all sub-samples lie on the same certified plane, the sampled patches are
geometrically aligned across views (this is the plane-induced homography, evaluated
pointwise -> a single-depth plane sweep on the known depth).

QUALITY GATE for this method = strict multi-view photometric consistency:
  - point must project into >= MIN_VIEWS floor frames (cheirality + fully in-bounds patch)
  - each view's patch must carry real texture (std >= MIN_STD) -- textureless => can't verify => reject
  - inlier views = largest set mutually agreeing with ZNCC >= NCC_MIN
  - inlier set must have >= MIN_VIEWS views AND span >= MIN_PARALLAX parallax
    (agreement across genuinely different viewpoints, not near-duplicate views)
Accept => real, verified floor point at grid location; color = median of inlier centers.
Reject (occlusion / object on floor / textureless / non-planar) is expected and reported.

Pure numpy + PIL. No production code touched."""
import os, sys, json, time, subprocess
import numpy as np
from PIL import Image
import fr_common as fc

FR = fc.FR
POSES = fc.POSES
FLOOR_IDS = fc.FLOOR_IDS
n_plane = fc.PLANE_N.astype(np.float64)
FLOOR_VAL = fc.FLOOR_VAL

# ---------------- tunables ----------------
GRID_M      = float(os.environ.get("GS", "0.02"))   # in-plane grid spacing (m)
PATCH_N     = 7           # KxK world sub-samples per patch
PATCH_R     = 0.015       # patch half-size on the plane (m) -> 3cm window
MIN_STD     = 6.0         # min intensity std (0-255) for a view's patch to be usable
NCC_MIN     = 0.70        # ZNCC inlier threshold
MIN_VIEWS   = 3           # min mutually-consistent views
MIN_PARALLAX= 5.0         # deg, min max-pairwise ray angle across inlier set
MAX_VIEWS   = 10          # cap candidate views per grid point (most head-on first)
MAX_GRAZE   = 72.0        # deg, reject views whose ray-to-normal angle exceeds this
PAD_M       = 0.05        # sweep region = production-floor bbox padded by this (m)
IMG_MARGIN  = 2.0         # px, keep patch this far inside image border

# ---------------- in-plane basis ----------------
# ensure n points "up" consistent w/ floor_dist sign is irrelevant for basis
a0 = np.array([1.0, 0, 0])
if abs(a0 @ n_plane) > 0.9: a0 = np.array([0, 0, 1.0])
u = a0 - (a0 @ n_plane) * n_plane; u /= np.linalg.norm(u)
v = np.cross(n_plane, u); v /= np.linalg.norm(v)

def to_uv(X):   # world -> (a,b) in-plane coords (X assumed near plane)
    d = X - (X @ n_plane - FLOOR_VAL)[..., None] * n_plane  # project onto plane
    return np.stack([d @ u, d @ v], -1)

# ---------------- read PLY (binary or ascii) for coverage comparison ----------------
def read_ply_xyz(path):
    with open(path, "rb") as f:
        assert f.readline().strip() == b"ply"
        fmt = f.readline().strip()
        n = 0; props = []
        while True:
            ln = f.readline().strip()
            if ln.startswith(b"element vertex"): n = int(ln.split()[-1])
            elif ln.startswith(b"property"): props.append(ln.split()[-1].decode())
            elif ln == b"end_header": break
        if fmt.endswith(b"ascii 1.0"):
            arr = np.array([list(map(float, f.readline().split()))[:3] for _ in range(n)])
            return arr
        # binary_little_endian: all props here are float except red/green/blue uchar
        dt = []
        for p in props:
            dt.append((p, "<f4") if p in ("x", "y", "z") or p not in ("red", "green", "blue") else (p, "u1"))
        data = np.frombuffer(f.read(), dtype=np.dtype(dt), count=n)
        return np.stack([data["x"], data["y"], data["z"]], -1).astype(np.float64)

# ---------------- pose caches (high-res) ----------------
def Kh(fid): return np.array(POSES[fid]["K_highres"], float)
Rc = {f: fc.R_of(f) for f in FLOOR_IDS}
tc = {f: fc.t_of(f) for f in FLOOR_IDS}
Cc = {f: fc.C_of(f) for f in FLOOR_IDS}
Kc = {f: Kh(f) for f in FLOOR_IDS}
M3 = {f: Kc[f] @ Rc[f] for f in FLOOR_IDS}          # uv_h = M3 X + Mt (homog)
Mt = {f: Kc[f] @ tc[f] for f in FLOOR_IDS}
HR_W = POSES[FLOOR_IDS[0]]["highres_w"]; HR_H = POSES[FLOOR_IDS[0]]["highres_h"]

# ---------------- load high-res RGB (uint8) ----------------
def avail(): return fc.avail_gb()
print(f"[mem] avail ~{avail():.1f} GB before image load; floor frames={len(FLOOR_IDS)}")
IMGS = {}
t0 = time.time()
for f in FLOOR_IDS:
    im = Image.open(POSES[f]["img_highres"]).convert("RGB")
    IMGS[f] = np.asarray(im, dtype=np.uint8)   # (H,W,3)
    if IMGS[f].shape[0] != HR_H or IMGS[f].shape[1] != HR_W:
        HR_H, HR_W = IMGS[f].shape[:2]
print(f"[mem] loaded {len(IMGS)} highres RGB in {time.time()-t0:.1f}s; avail ~{avail():.1f} GB")

# gray weights
GW = np.array([0.299, 0.587, 0.114])

def bilinear_rgb(img, xy):
    """img (H,W,3) uint8; xy (N,2) float -> (N,3) float. Assumes in-bounds already."""
    x = xy[:, 0]; y = xy[:, 1]
    x0 = np.floor(x).astype(np.int32); y0 = np.floor(y).astype(np.int32)
    x1 = x0 + 1; y1 = y0 + 1
    H, W = img.shape[:2]
    x1 = np.clip(x1, 0, W - 1); y1 = np.clip(y1, 0, H - 1)
    x0 = np.clip(x0, 0, W - 1); y0 = np.clip(y0, 0, H - 1)
    wx = (x - x0); wy = (y - y0)
    Ia = img[y0, x0].astype(np.float32); Ib = img[y0, x1].astype(np.float32)
    Ic = img[y1, x0].astype(np.float32); Id = img[y1, x1].astype(np.float32)
    top = Ia * (1 - wx)[:, None] + Ib * wx[:, None]
    bot = Ic * (1 - wx)[:, None] + Id * wx[:, None]
    return top * (1 - wy)[:, None] + bot * wy[:, None]

# ---------------- build grid over production-floor bbox ----------------
prod_xyz = read_ply_xyz(FR + "/production_floor.ply")
prod_uv = to_uv(prod_xyz)
amin, bmin = prod_uv.min(0) - PAD_M
amax, bmax = prod_uv.max(0) + PAD_M
avals = np.arange(amin, amax + 1e-9, GRID_M)
bvals = np.arange(bmin, bmax + 1e-9, GRID_M)
AA, BB = np.meshgrid(avals, bvals, indexing="ij")
uv_grid = np.stack([AA.ravel(), BB.ravel()], -1)               # (Ng,2)
# world center of each grid point (on plane): X = FLOOR_VAL*n + a*u + b*v
Xg = FLOOR_VAL * n_plane[None, :] + uv_grid[:, 0:1] * u[None, :] + uv_grid[:, 1:2] * v[None, :]
Ng = len(Xg)
print(f"[grid] {len(avals)}x{len(bvals)} = {Ng} candidate grid pts @ {GRID_M*100:.1f}cm "
      f"over bbox {amax-amin:.2f}x{bmax-bmin:.2f} m (padded)")

# patch offset lattice on plane (world), (P2,3)
off = np.linspace(-PATCH_R, PATCH_R, PATCH_N)
OU, OV = np.meshgrid(off, off, indexing="ij")
patch_off = OU.ravel()[:, None] * u[None, :] + OV.ravel()[:, None] * v[None, :]  # (P2,3)
P2 = patch_off.shape[0]

# ---------------- plane-sweep ----------------
FLIST = np.array(FLOOR_IDS)
# stack pose arrays for fast center-projection test
M3s = np.stack([M3[f] for f in FLOOR_IDS])   # (F,3,3)
Mts = np.stack([Mt[f] for f in FLOOR_IDS])   # (F,3)
Rzs = np.stack([Rc[f][2] for f in FLOOR_IDS])# (F,3) row for depth
tzs = np.array([tc[f][2] for f in FLOOR_IDS])# (F,)
Cs  = np.stack([Cc[f] for f in FLOOR_IDS])   # (F,3)
# view ray angle to normal per (frame): use camera center -> use per-point ray though.
nF = len(FLOOR_IDS)

acc_X = []; acc_rgb = []; acc_meta = []  # meta: [ninlier, parallax_deg, zncc_med, ncand]
rej = dict(fewcand=0, fewusable=0, fewinlier=0, lowparallax=0)
report_every = max(1, Ng // 20)
t0 = time.time()
for gi in range(Ng):
    X = Xg[gi]
    # --- fast center projection into all frames ---
    z = Rzs @ X + tzs                         # (F,)
    uvh = M3s @ X + Mts                        # (F,3)
    good = z > fc.DEPTH_MIN
    cu = uvh[:, 0] / np.where(good, uvh[:, 2], 1)
    cv = uvh[:, 1] / np.where(good, uvh[:, 2], 1)
    inb = good & (cu > IMG_MARGIN) & (cu < HR_W - 1 - IMG_MARGIN) & \
          (cv > IMG_MARGIN) & (cv < HR_H - 1 - IMG_MARGIN)
    # graze: angle between ray (X - C) and plane normal
    rays = X[None, :] - Cs
    rn = np.linalg.norm(rays, axis=1) + 1e-12
    cosang = np.abs((rays @ n_plane) / rn)
    graze_ok = cosang > np.cos(np.radians(MAX_GRAZE))
    cand = np.where(inb & graze_ok)[0]
    if len(cand) < MIN_VIEWS:
        rej["fewcand"] += 1
        if (gi % report_every == 0): print(f"  .. {gi}/{Ng}", flush=True)
        continue
    # rank candidates most head-on first, cap
    order = cand[np.argsort(-cosang[cand])][:MAX_VIEWS]
    # --- build metric-rectified patch per candidate view ---
    Xsub = X[None, :] + patch_off                       # (P2,3)
    grays = []; centers_rgb = []; used = []
    for fi in order:
        f = FLOOR_IDS[fi]
        ph = (M3[f] @ Xsub.T).T + Mt[f]                  # (P2,3)
        zz = ph[:, 2]
        if np.any(zz <= fc.DEPTH_MIN): continue
        px = ph[:, :2] / zz[:, None]
        if px[:, 0].min() < 0 or px[:, 0].max() > HR_W - 1 or \
           px[:, 1].min() < 0 or px[:, 1].max() > HR_H - 1: continue
        rgb = bilinear_rgb(IMGS[f], px)                  # (P2,3)
        g = rgb @ GW
        if g.std() < MIN_STD: continue                   # textureless in this view
        grays.append(g); used.append(fi)
        # center pixel color (patch center index)
        centers_rgb.append(rgb[P2 // 2])
    if len(used) < MIN_VIEWS:
        rej["fewusable"] += 1
        if (gi % report_every == 0): print(f"  .. {gi}/{Ng}", flush=True)
        continue
    G = np.stack(grays)                                   # (V,P2)
    Gn = G - G.mean(1, keepdims=True)
    Gn /= (np.linalg.norm(Gn, axis=1, keepdims=True) + 1e-9)
    ncc = Gn @ Gn.T                                       # (V,V) ZNCC
    np.fill_diagonal(ncc, 1.0)
    inlier_counts = (ncc >= NCC_MIN).sum(1)
    ref = int(np.argmax(inlier_counts))
    inl = np.where(ncc[ref] >= NCC_MIN)[0]
    if len(inl) < MIN_VIEWS:
        rej["fewinlier"] += 1
        if (gi % report_every == 0): print(f"  .. {gi}/{Ng}", flush=True)
        continue
    # parallax across inlier set
    used_arr = np.array(used)
    inl_frames = used_arr[inl]
    dirs = X[None, :] - Cs[inl_frames]
    dirs /= (np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-12)
    cosm = np.clip(dirs @ dirs.T, -1, 1)
    par = np.degrees(np.arccos(cosm)).max()
    if par < MIN_PARALLAX:
        rej["lowparallax"] += 1
        if (gi % report_every == 0): print(f"  .. {gi}/{Ng}", flush=True)
        continue
    # ---- accept ----
    sub = ncc[np.ix_(inl, inl)]
    zncc_med = float(np.median(sub[np.triu_indices(len(inl), 1)])) if len(inl) > 1 else 1.0
    col = np.median(np.stack([centers_rgb[k] for k in inl]), 0)
    acc_X.append(X); acc_rgb.append(col)
    acc_meta.append([len(inl), par, zncc_med, len(used)])
    if (gi % report_every == 0):
        print(f"  .. {gi}/{Ng}  acc={len(acc_X)}  avail~{avail():.1f}GB", flush=True)

dt = time.time() - t0
acc_X = np.asarray(acc_X); acc_rgb = np.asarray(acc_rgb); acc_meta = np.asarray(acc_meta)
print(f"[sweep] {Ng} grid pts in {dt:.1f}s -> ACCEPT={len(acc_X)}  rej={rej}")

# ---------------- coverage in identical 5cm (u,v) cells ----------------
def cells5(uv): return set(map(tuple, np.floor(uv / 0.05).astype(int)))
prod_cells = cells5(prod_uv)
band_xyz = read_ply_xyz(FR + "/floor_rescue_band.ply")
loftr_cells = cells5(to_uv(band_xyz))
if len(acc_X):
    ps_uv = to_uv(acc_X)
    ps_cells = cells5(ps_uv)
    new_vs_sift = ps_cells - prod_cells
    new_vs_both = ps_cells - prod_cells - loftr_cells
else:
    ps_cells = set(); new_vs_sift = set(); new_vs_both = set()

CELL_A = 0.05 * 0.05
stats = dict(
    method="plane_sweep_known_floor",
    grid_m=GRID_M, patch_n=PATCH_N, patch_r_m=PATCH_R,
    gates=dict(MIN_STD=MIN_STD, NCC_MIN=NCC_MIN, MIN_VIEWS=MIN_VIEWS,
               MIN_PARALLAX_deg=MIN_PARALLAX, MAX_GRAZE_deg=MAX_GRAZE, MAX_VIEWS=MAX_VIEWS),
    grid_candidates=Ng, accepted=int(len(acc_X)),
    rejected=rej,
    # quality (photometric-consistency is THIS method's geometric gate; points lie on
    # certified plane by construction so triangulation-reproj is not defined here)
    zncc_median=float(np.median(acc_meta[:, 2])) if len(acc_X) else None,
    zncc_p10=float(np.percentile(acc_meta[:, 2], 10)) if len(acc_X) else None,
    parallax_deg_median=float(np.median(acc_meta[:, 1])) if len(acc_X) else None,
    ninlier_median=float(np.median(acc_meta[:, 0])) if len(acc_X) else None,
    ninlier_max=int(acc_meta[:, 0].max()) if len(acc_X) else None,
    # coverage (identical 5cm u,v cells)
    cells_production_sift=len(prod_cells),
    cells_loftr_band=len(loftr_cells),
    cells_planesweep=len(ps_cells),
    cells_new_vs_sift=len(new_vs_sift),
    cells_new_vs_sift_and_loftr=len(new_vs_both),
    area_new_vs_sift_m2=len(new_vs_sift) * CELL_A,
    area_new_vs_both_m2=len(new_vs_both) * CELL_A,
    area_planesweep_m2=len(ps_cells) * CELL_A,
)
json.dump(stats, open(FR + "/fr_planesweep_stats.json", "w"), indent=1)

if len(acc_X):
    fc.write_ply(FR + "/floor_planesweep.ply", acc_X, rgb=acc_rgb.astype(int),
                 extra=acc_meta, extra_names=["ninlier", "parallax_deg", "zncc_med", "ncand"])
print("=== PLANE-SWEEP RESULT ===")
print(json.dumps(stats, indent=1))
print("wrote floor_planesweep.ply, fr_planesweep_stats.json")
