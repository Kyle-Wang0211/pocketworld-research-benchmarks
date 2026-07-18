#!/usr/bin/env python3
"""E22-s1: LoFTR semi-dense evidence for starved pairs (cap51 host prototype).

Pair selection: existing TVG pairs with < STARVED_INLIERS inliers (evidence-
starved) + never-matched forward-gated spatial pairs (E20 semantics), capped.
LoFTR (kornia indoor weights — HOST EXPERIMENT ONLY, ScanNet non-commercial,
ship blocker acknowledged) on photos at 1/4 res (960x540, exact scale, photo
frame == gray frame pixel-identical for cap51) -> coords x4 -> verify with
production-refined-pose F + Sampson<3px -> keep pairs with >= MIN_INLIERS.
Output: e22_loftr_matches.npz {"{i1}_{i2}_kp1/_kp2"} in gray/native coords.
"""
import json, os, sqlite3, sys, time
import numpy as np

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
DATA = f"{ROOT}/data/pocketworld_captures"
OUT = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/E22_rebirth_prototype"
DB = f"{DATA}/cap51/replay_database/sfm_live.db"
META = f"{DATA}/cap51/device_full_pull_2026-07-17/sfm_sparse_meta.json"
FED = f"{DATA}/cap51/private_manifests/sfm_fed_frames.jsonl"
PHOTOS = f"{DATA}/cap51/device_full_pull_2026-07-17/photos_highres"
MAX_IMAGE_ID = 2147483647
STARVED_INLIERS = 60
MIN_INLIERS = 15  # kSpatialPreliminaryInliers production semantics
SAMPSON_PX = 3.0
CAP_PAIRS = int(os.environ.get("E22_CAP_PAIRS", "250"))
SCALE = 4  # 3840/960

def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])

def sampson(F, x1, x2):
    h1 = np.hstack([x1, np.ones((len(x1), 1))]); h2 = np.hstack([x2, np.ones((len(x2), 1))])
    Fx1 = h1 @ F.T; Ftx2 = h2 @ F
    num = (h2 * Fx1).sum(1)
    den = Fx1[:, 0]**2 + Fx1[:, 1]**2 + Ftx2[:, 0]**2 + Ftx2[:, 1]**2
    return np.abs(num) / np.sqrt(np.maximum(den, 1e-12))

meta = json.load(open(META)); assert meta["refined"]
poses = {p["frame_id"]: (quat_to_R(np.array(p["quat_wxyz"])), np.array(p["t"]))
         for p in meta["poses"] if p.get("registered")}
fed = {}
for line in open(FED):
    j = json.loads(line)
    fed[j["frameId"]] = os.path.basename(j["jpegPath"])

db = sqlite3.connect(f"file:{DB}?mode=ro&immutable=1", uri=True)
c = db.cursor()
cam = c.execute("SELECT params FROM cameras").fetchone()[0]
f_, cx_, cy_ = np.frombuffer(cam, np.float64)[:3]
K = np.array([[f_, 0, cx_], [0, f_, cy_], [0, 0, 1]]); Kinv = np.linalg.inv(K)
img_ids = [r[0] for r in c.execute("SELECT image_id FROM images ORDER BY image_id")]
tvg = {}
for pid, rows in c.execute("SELECT pair_id, rows FROM two_view_geometries"):
    tvg[(pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID)] = rows
matched = set()
for (pid,) in c.execute("SELECT pair_id FROM matches"):
    matched.add((pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID))
db.close()

R_of, C_of, fwd = {}, {}, {}
for iid in img_ids:
    fid = iid - 1
    if fid in poses:
        R, t = poses[fid]
        R_of[iid] = (R, t); C_of[iid] = -R.T @ t; fwd[iid] = R[2, :]
min_dot = np.cos(np.deg2rad(45.0))
cands = []
for (i1, i2), inl in tvg.items():
    if inl < STARVED_INLIERS and i1 in R_of and i2 in R_of:
        cands.append((i1, i2, 0, inl))
for a in range(len(img_ids)):
    i1 = img_ids[a]
    if i1 not in fwd: continue
    for b in range(a + 1, len(img_ids)):
        i2 = img_ids[b]
        if i2 not in fwd or (i1, i2) in matched: continue
        if float(np.dot(fwd[i1], fwd[i2])) < min_dot: continue
        cands.append((i1, i2, 1, 0))
cands.sort(key=lambda x: (x[2], x[3]))
cands = cands[:CAP_PAIRS]
print(f"pairs selected: {len(cands)} (starved={sum(1 for x in cands if x[2]==0)}, "
      f"never-matched={sum(1 for x in cands if x[2]==1)})", flush=True)

import torch, cv2
import kornia.feature as KF
dev = "mps" if torch.backends.mps.is_available() else "cpu"
matcher = KF.LoFTR(pretrained="indoor").eval().to(dev)
cache = {}
def load_pair(iid):
    """(low-res tensor for LoFTR, native uint8 gray for ZNCC refine)"""
    if iid in cache: return cache[iid]
    p = os.path.join(PHOTOS, fed[iid - 1])
    # IGNORE_ORIENTATION: db keypoints live in the raw sensor frame (3840x2160
    # landscape); photos carry EXIF ori=6 and cv2 would silently rotate them.
    im = cv2.imread(p, cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION)
    if im is None: cache[iid] = None; return None
    assert im.shape == (2160, 3840), f"unexpected photo shape {im.shape}"
    lo = cv2.resize(im, (960, 540), interpolation=cv2.INTER_AREA)
    t = torch.from_numpy(lo).float()[None, None] / 255.0
    if len(cache) > 12: cache.pop(next(iter(cache)))
    cache[iid] = (t, im)
    return cache[iid]

TPL, WIN = 10, 20  # template half 10 (21x21), search half 20 (41x41) at native res
def zncc_refine(im1, im2, kp1, kp2):
    """Refine kp2 against kp1 anchor by native-res ZNCC; returns refined kp2 + keep mask."""
    h, w = im1.shape
    out = kp2.copy(); keep = np.zeros(len(kp1), bool)
    for i, ((x1, y1), (x2, y2)) in enumerate(zip(kp1, kp2)):
        x1i, y1i, x2i, y2i = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
        if not (TPL <= x1i < w-TPL and TPL <= y1i < h-TPL): continue
        if not (WIN+TPL <= x2i < w-WIN-TPL and WIN+TPL <= y2i < h-WIN-TPL): continue
        tpl = im1[y1i-TPL:y1i+TPL+1, x1i-TPL:x1i+TPL+1]
        win = im2[y2i-WIN-TPL:y2i+WIN+TPL+1, x2i-WIN-TPL:x2i+WIN+TPL+1]
        r = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, ml = cv2.minMaxLoc(r)
        if mx < 0.5: continue
        px, py = ml
        # parabola subpixel on the correlation peak
        dx = dy = 0.0
        if 0 < px < r.shape[1]-1:
            a, b_, c2 = r[py, px-1], r[py, px], r[py, px+1]
            d = a - 2*b_ + c2
            if abs(d) > 1e-9: dx = float(np.clip(0.5*(a-c2)/d, -1, 1))
        if 0 < py < r.shape[0]-1:
            a, b_, c2 = r[py-1, px], r[py, px], r[py+1, px]
            d = a - 2*b_ + c2
            if abs(d) > 1e-9: dy = float(np.clip(0.5*(a-c2)/d, -1, 1))
        out[i] = (x2i - WIN + px + dx, y2i - WIN + py + dy)
        keep[i] = True
    return out, keep

out = {}
stats = []
t0 = time.time()
kept = 0
for k, (i1, i2, klass, inl0) in enumerate(cands):
    p1, p2 = load_pair(i1), load_pair(i2)
    if p1 is None or p2 is None:
        stats.append((i1, i2, klass, -1, -1)); continue
    with torch.no_grad():
        r = matcher({"image0": p1[0].to(dev), "image1": p2[0].to(dev)})
    kp1 = r["keypoints0"].cpu().numpy() * SCALE
    kp2 = r["keypoints1"].cpu().numpy() * SCALE
    conf = r["confidence"].cpu().numpy()
    m = conf >= 0.2
    kp1, kp2 = kp1[m], kp2[m]
    n_inl = 0
    if len(kp1) >= MIN_INLIERS:
        R1, t1 = R_of[i1]; R2, t2 = R_of[i2]
        R = R2 @ R1.T; t = t2 - R @ t1
        E = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]]) @ R
        F = Kinv.T @ E @ Kinv
        # stage 1: loose Sampson at LoFTR-at-quarter-res precision
        pre = sampson(F, kp1, kp2) < 12.0
        kp1, kp2 = kp1[pre], kp2[pre]
        if len(kp1) >= MIN_INLIERS:
            # stage 2: native-res ZNCC subpixel refine of kp2, then strict gate
            kp2r, ok = zncc_refine(p1[1], p2[1], kp1, kp2)
            kp1, kp2 = kp1[ok], kp2r[ok]
            if len(kp1) >= MIN_INLIERS:
                good = sampson(F, kp1, kp2) < SAMPSON_PX
                n_inl = int(good.sum())
                if n_inl >= MIN_INLIERS:
                    out[f"{i1}_{i2}_kp1"] = kp1[good].astype(np.float32)
                    out[f"{i1}_{i2}_kp2"] = kp2[good].astype(np.float32)
                    kept += 1
    stats.append((i1, i2, klass, len(kp1), n_inl))
    if (k + 1) % 25 == 0 or k == len(cands) - 1:
        print(f"{k+1}/{len(cands)} matched, kept {kept}, {time.time()-t0:.0f}s", flush=True)

np.savez_compressed(f"{OUT}/e22_loftr_matches.npz", **out)
st = np.array(stats, np.float64)
np.savez_compressed(f"{OUT}/e22_loftr_stats.npz", stats=st,
                    cols=np.array(["i1", "i2", "class", "n_raw_conf", "n_inl_3px"]))
led = {
    "pairs_tried": len(cands), "pairs_kept": kept,
    "inliers_total": int(sum(len(out[k]) for k in out if k.endswith("_kp1"))),
    "starved_kept": int(((st[:, 2] == 0) & (st[:, 4] >= MIN_INLIERS)).sum()),
    "never_matched_kept": int(((st[:, 2] == 1) & (st[:, 4] >= MIN_INLIERS)).sum()),
    "wall_s": round(time.time() - t0, 1), "device": dev,
    "weights": "kornia LoFTR-indoor (ScanNet, NON-COMMERCIAL — host experiment only)",
}
json.dump(led, open(f"{OUT}/e22_s1_ledger.json", "w"), indent=1)
print(json.dumps(led, indent=1))
