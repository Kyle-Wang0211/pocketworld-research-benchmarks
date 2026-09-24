"""expAW v4: joint scale+shift Bundle Adjustment at WINDOW or FRAME granularity.

- GRAN=window: one (a,b) per window. All 33 windows as conf-weighted alignment
  bridges, export only the 12 good. (Saturates floor ~18mm.)
- GRAN=frame:  one (a,b) per FRAME (the 12 good windows -> 216 frames), to kill
  the residual PER-FRAME depth bias that per-window BA can't touch (each frame
  places the floor at a slightly different absolute depth). Correspondences now
  INCLUDE same-window/different-frame pairs (heavily overlapping -> strongly
  constrained); a Tikhonov PRIOR (a->1, b->0) tames the 432-DOF degeneracy.

Model per unit u (window or frame): z = a_u*(s_w*d) + b_u  (a init 1, b init 0).
Loss = Σ w Huber(||X_A-X_B||) + W_ANCHOR Σ w Huber(anchor) [+ PRIOR(a,b) frame].
Floor thickness (RANSAC, robust spread) on the 12 good windows. Solver = Adam.
Exports ba_scaleshift.npz (gran-tagged) -> expAX applies per-window or per-frame.

Tunables (argv): N_CAND W_ANCHOR ITERS STRIDE CONF_BAR GRAN PRIOR
"""
import json, sys, time, warnings
from pathlib import Path
import numpy as np
import open3d as o3d
warnings.filterwarnings("ignore")
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import da3_window_scale_fixb as fixb

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
EXPAC = Path("data/expAC_rewindow_span_2026_06_13")
ANCH = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
CONF_PCT = 40.0
N_CAND   = int(sys.argv[1])   if len(sys.argv) > 1 else 6
W_ANCHOR = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
ITERS    = int(sys.argv[3])   if len(sys.argv) > 3 else 600
STRIDE   = int(sys.argv[4])   if len(sys.argv) > 4 else 16
CONF_BAR = float(sys.argv[5]) if len(sys.argv) > 5 else 6.0
GRAN     = sys.argv[6]        if len(sys.argv) > 6 else "window"   # window | frame
PRIOR    = float(sys.argv[7]) if len(sys.argv) > 7 else 2.0        # frame-mode Tikhonov a->1,b->0
DET_LONG = 1536.0; CAP = 150000; UP = 1


def log(m): print(f"[expAW {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
zf = np.load(ANCH)
anchors = fixb.AnchorSet(zf["pts"], zf["obs_frame"], zf["obs_uv"], zf["obs_aidx"])


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1)); out[:, :3, :] = ext; return out
    return ext.reshape(-1, 4, 4)


rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
sc = [r for r in rows if r["kind"] == "scales"][0]
FRAME_MODE = (GRAN == "frame")
ws, confmed = [], []
for w in range(len(sc["s_B"])):
    if FRAME_MODE and sc["conf_medians"][w] < CONF_BAR: continue   # frame mode: good windows only
    p = EXPAC / "windows" / f"win_{w:02d}.npz"
    if not p.exists(): continue
    z = np.load(p)
    ws.append(dict(depth=z["depth"].astype(np.float64), conf=z["conf"].astype(np.float32),
                   K=z["K"].astype(np.float64), w2c=w2c4(z["w2c"]),
                   fidx=list(wdef[w]["frame_idx"]), s=float(sc["s_B"][w])))
    confmed.append(float(sc["conf_medians"][w]))
NWIN = len(ws); confmed = np.array(confmed)
wgood = confmed >= CONF_BAR

# ---- flatten frames; assign UNIT (window idx | frame idx) ----
FR = []
for wi, W in enumerate(ws):
    depth, conf, K, w2c, s = W["depth"], W["conf"], W["K"], W["w2c"], W["s"]
    n, H, Wd = depth.shape; fl = np.percentile(conf, CONF_PCT)
    for k in range(n):
        dfixb = (s * depth[k]).astype(np.float64); dfixb[(conf[k] < fl) | (depth[k] <= 1e-3)] = 0.0
        c2w = np.linalg.inv(w2c[k])
        uid = (len(FR) if FRAME_MODE else wi)
        FR.append(dict(dfixb=dfixb, K=K[k], w2c=w2c[k], R=c2w[:3, :3], t=c2w[:3, 3],
                       C=c2w[:3, 3], win=wi, uid=uid, gd=bool(wgood[wi]), H=H, W=Wd))
NU = (len(FR) if FRAME_MODE else NWIN)
funit = np.array([f["uid"] for f in FR]); centers = np.array([f["C"] for f in FR])
# per-unit conf weight + which units to export
if FRAME_MODE:
    ucw = np.ones(NU); uexport = np.ones(NU, bool)            # all frames good
else:
    ucw = np.clip(confmed / CONF_BAR, 0.15, 1.0); uexport = wgood
log(f"{NWIN} windows / {len(FR)} frames | GRAN={GRAN} -> {NU} units, export {uexport.sum()}")


def dir_of(K, u, v):
    return np.stack([(u + 0.5 - K[0, 2]) / K[0, 0], (v + 0.5 - K[1, 2]) / K[1, 1], np.ones_like(u, float)], -1)


# ---- reprojection correspondences (exclude SAME UNIT) ----
UA, RA, tA, dirA, dfA, UB, RB, tB, dirB, dfB = ([] for _ in range(10))
for fa in FR:
    K = fa["K"]; vv, uu = np.where(fa["dfixb"] > 1e-3)
    sel = (vv % STRIDE == 0) & (uu % STRIDE == 0); vv, uu = vv[sel], uu[sel]
    if not len(vv): continue
    da = fa["dfixb"][vv, uu]; dA = dir_of(K, uu, vv)
    Xw = (fa["R"] @ (dA * da[:, None]).T).T + fa["t"]
    d2 = np.sum((centers - fa["C"]) ** 2, 1)
    cand = [j for j in np.argsort(d2) if funit[j] != fa["uid"]][:N_CAND]
    for j in cand:
        fb = FR[j]; Kb = fb["K"]
        cam = (fb["w2c"][:3, :3] @ Xw.T + fb["w2c"][:3, 3:4]).T; zc = cam[:, 2]
        ub = np.round(Kb[0, 0] * cam[:, 0] / np.where(zc == 0, 1, zc) + Kb[0, 2]).astype(int)
        vb = np.round(Kb[1, 1] * cam[:, 1] / np.where(zc == 0, 1, zc) + Kb[1, 2]).astype(int)
        ok = (zc > 1e-3) & (ub >= 0) & (ub < fb["W"]) & (vb >= 0) & (vb < fb["H"])
        if not ok.any(): continue
        db = np.zeros(len(zc)); db[ok] = fb["dfixb"][np.clip(vb, 0, fb["H"]-1)[ok], np.clip(ub, 0, fb["W"]-1)[ok]]
        keep = ok & (db > 1e-3)
        if not keep.any(): continue
        idx = np.where(keep)[0]
        UA.append(np.full(len(idx), fa["uid"])); RA.append(np.tile(fa["R"], (len(idx),1,1))); tA.append(np.tile(fa["t"], (len(idx),1)))
        dirA.append(dA[idx]); dfA.append(da[idx])
        UB.append(np.full(len(idx), fb["uid"])); RB.append(np.tile(fb["R"], (len(idx),1,1))); tB.append(np.tile(fb["t"], (len(idx),1)))
        dirB.append(dir_of(Kb, ub[idx], vb[idx])); dfB.append(db[idx])
UA=np.concatenate(UA); RA=np.concatenate(RA); tA=np.concatenate(tA); dirA=np.concatenate(dirA); dfA=np.concatenate(dfA)
UB=np.concatenate(UB); RB=np.concatenate(RB); tB=np.concatenate(tB); dirB=np.concatenate(dirB); dfB=np.concatenate(dfB)
if len(UA) > CAP:
    sl = slice(None, None, len(UA)//CAP)
    UA,RA,tA,dirA,dfA = UA[sl][:CAP],RA[sl][:CAP],tA[sl][:CAP],dirA[sl][:CAP],dfA[sl][:CAP]
    UB,RB,tB,dirB,dfB = UB[sl][:CAP],RB[sl][:CAP],tB[sl][:CAP],dirB[sl][:CAP],dfB[sl][:CAP]
WCROSS = ucw[UA] * ucw[UB]
log(f"{len(UA):,} correspondences")

# ---- anchor metric terms (per unit) ----
AAU, AADF, AAZ = [], [], []
for wi, W in enumerate(ws):
    depth, conf, K, w2c, fidx, s = W["depth"], W["conf"], W["K"], W["w2c"], W["fidx"], W["s"]
    n, H, Wd = depth.shape; fl = np.percentile(conf, CONF_PCT); scd = Wd / DET_LONG
    fbase = sum(ws[x]["depth"].shape[0] for x in range(wi))           # global frame offset
    for k, gf in enumerate(fidx):
        seln = anchors.obs_frame == gf
        if not seln.any(): continue
        uv = anchors.obs_uv[seln]; aidx = anchors.obs_aidx[seln]
        ud = np.round((uv[:, 0]+0.5)*scd-0.5).astype(int); vd = np.round((uv[:, 1]+0.5)*scd-0.5).astype(int)
        gd = (ud >= 0) & (ud < Wd) & (vd >= 0) & (vd < H); ud, vd, aidx = ud[gd], vd[gd], aidx[gd]
        dp = depth[k][vd, ud]; cp = conf[k][vd, ud]
        ztrue = (w2c[k][:3, :3] @ anchors.pts[aidx].T + w2c[k][:3, 3:4])[2]
        g2 = (cp >= fl) & (dp > 1e-3) & (ztrue > 1e-3)
        uid = (fbase + k) if FRAME_MODE else wi
        AAU.append(np.full(int(g2.sum()), uid)); AADF.append(s*dp[g2]); AAZ.append(ztrue[g2])
AAU=np.concatenate(AAU); AADF=np.concatenate(AADF); AAZ=np.concatenate(AAZ); WANC = ucw[AAU]
log(f"{len(AAU):,} anchor terms")

# ---- floor obs (GOOD windows) ----
ob = []
for f in FR:
    if not f["gd"]: continue
    vv, uu = np.where(f["dfixb"] > 1e-3); s4 = (vv % 6 == 0) & (uu % 6 == 0); vv, uu = vv[s4], uu[s4]
    ob.append((f["R"], f["t"], dir_of(f["K"], uu, vv), f["dfixb"][vv, uu], np.full(len(vv), f["uid"])))
ODIR=np.concatenate([o[2] for o in ob]); ODF=np.concatenate([o[3] for o in ob]); OU=np.concatenate([o[4] for o in ob])
OR_=np.concatenate([np.tile(o[0],(len(o[3]),1,1)) for o in ob]); OT_=np.concatenate([np.tile(o[1],(len(o[3]),1)) for o in ob])


def world_np(a, b, R, t, dirs, df, u):
    return np.einsum("nij,nj->ni", R, dirs * (a[u]*df+b[u])[:, None]) + t


def floor_thickness(a, b):
    P = world_np(a, b, OR_, OT_, ODIR, ODF, OU)
    low = P[P[:, UP] < np.percentile(P[:, UP], 45)]; pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(low))
    for _ in range(4):
        if len(pc.points) < 500: break
        plane, inl = pc.segment_plane(0.05, 3, 200); nrm = np.array(plane[:3]); pts = np.asarray(pc.points)[inl]
        if abs(nrm[UP]) > 0.7:
            d = pts @ nrm + plane[3]; return float(np.percentile(d,84)-np.percentile(d,16)), float(d.std()), len(inl)
        pc = pc.select_by_index(inl, invert=True)
    return float("nan"), float("nan"), 0


th0, sd0, _ = floor_thickness(np.ones(NU), np.zeros(NU))
log(f"floor (FixB): 16-84% {th0*1000:.1f}mm  std {sd0*1000:.1f}mm")

# ---- torch optimize ----
FT = torch.float32
def T(x, dt=FT): return torch.tensor(x, dtype=dt)
RAt,tAt,dAt,dfAt,uAt = T(RA),T(tA),T(dirA),T(dfA),T(UA, torch.long)
RBt,tBt,dBt,dfBt,uBt = T(RB),T(tB),T(dirB),T(dfB),T(UB, torch.long)
WCt = T(WCROSS); aut,adft,azt,wanct = T(AAU, torch.long),T(AADF),T(AAZ),T(WANC)
a = torch.ones(NU, dtype=FT, requires_grad=True); b = torch.zeros(NU, dtype=FT, requires_grad=True)


def world_t(R, t, dirs, df, u):
    return torch.einsum("nij,nj->ni", R, dirs * (a[u]*df+b[u])[:, None]) + t


def huber(r, d):
    x = torch.abs(r); return torch.where(x <= d, 0.5*r*r, d*(x-0.5*d))


opt = torch.optim.Adam([a, b], lr=0.01); t0 = time.time()
for it in range(ITERS):
    opt.zero_grad()
    rc = huber(torch.norm(world_t(RAt,tAt,dAt,dfAt,uAt)-world_t(RBt,tBt,dBt,dfBt,uBt), dim=1), 0.02)
    cross = (WCt*rc).sum()/WCt.sum()
    anc = (wanct*huber(a[aut]*adft+b[aut]-azt, 0.05)).sum()/wanct.sum()
    loss = cross + W_ANCHOR*anc
    if FRAME_MODE: loss = loss + PRIOR*(((a-1)**2).mean() + (b**2).mean())
    loss.backward(); opt.step()
    if it % 150 == 0 or it == ITERS-1:
        log(f"  it {it:3d} loss {loss.item():.5f} cross {cross.item()*1000:.2f}mm anc {anc.item()*1000:.2f}mm")
log(f"optimized {ITERS} steps ({NU} units, {GRAN}) in {time.time()-t0:.1f}s")
an, bn = a.detach().numpy(), b.detach().numpy()
np.savez(EXPAC / "ba_scaleshift.npz", a=an[uexport], b=bn[uexport], gran=GRAN, conf_bar=CONF_BAR)
log(f"saved ba_scaleshift.npz ({GRAN}, {int(uexport.sum())} units)")
th1, sd1, _ = floor_thickness(an, bn)

print(f"\n================ RESULT (GRAN={GRAN}) ================")
print(f"  地板厚度 16-84%  FixB {th0*1000:6.1f}mm -> BA {th1*1000:6.1f}mm  ({100*(1-th1/th0):+.0f}%)")
print(f"  地板厚度 std     FixB {sd0*1000:6.1f}mm -> BA {sd1*1000:6.1f}mm  ({100*(1-sd1/sd0):+.0f}%)")
if not FRAME_MODE:
    print(f"  good a: {np.round(an[uexport],4)}")
    print(f"  good b(mm): {np.round(bn[uexport]*1000,1)}")
else:
    print(f"  per-frame b(mm): mean {bn.mean()*1000:.1f}  std {bn.std()*1000:.1f}  range [{bn.min()*1000:.0f},{bn.max()*1000:.0f}]")
log("EXPAW-DONE")
