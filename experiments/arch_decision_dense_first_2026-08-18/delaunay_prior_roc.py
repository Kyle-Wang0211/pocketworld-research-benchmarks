# 第1档第一刀: 稀疏锚点 Delaunay 平面先验 ROC(只测可分性, 不装门)
# 骨架抄 ACMMP GetSupportPoints→Delaunay→PriorPlane; 支撑点=ply_P16KH.ply 锚点(与 cam.txt 同 gauge)
# 口径与 da3_separation_probe_20260818/prep.py 完全一致:
#   相机=mvs_P16k/cams, 768x576, 遮挡门=|z_anchor - D_mvs|/D_mvs < 0.15
#   标签: blob=blob_idx.npy 溯源(正类), clean=|r|<0.06 gauge 墙面像素(负类)
# 先验: 图像域 Delaunay, 逐三角以三锚点定 3D 平面 => 像素先验深度 = 重心坐标插值 1/z(数学上精确等于三点平面沿视线深度)
# 兜底门 a: 三角三顶点深度极差 (zmax-zmin)/zmin > 0.15 => 无先验区
# 兜底门 b(可选): 三角平面法向既不近水平面(竖直面)也不近竖直(水平面) => 剔除; 20度带
import numpy as np, json, sys
from PIL import Image
from scipy.spatial import Delaunay
from scipy.stats import rankdata

BASE = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
WALL = "/Users/kaidongwang/Documents/progecttwo/_artifacts/wall_forensics_20260818"
SPARSE_PLY = "/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/ply_P16KH.ply"
OUTD = "/Users/kaidongwang/Documents/progecttwo/_artifacts/delaunay_prior_20260818"
SCRATCH = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad"
FRAMES = [78, 79, 80, 81, 82, 83, 85, 86, 87, 100, 103, 107, 125]
S768 = 768 / 4032.0
CM = 42.0  # gauge -> cm
TAUS_CM = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0]
REL_TH = 0.15          # 门a: 顶点深度极差阈
ANG = np.deg2rad(20.0) # 门b: 20度带
SIN_A, COS_A = np.sin(ANG), np.cos(ANG)

def read_cam(fr):
    L = open(f"{BASE}/mvs_P16k/cams/{fr:08d}_cam.txt").read().split("\n")
    E = np.array([[float(x) for x in L[i+1].split()] for i in range(4)])
    K = np.array([[float(x) for x in L[i+7].split()] for i in range(3)])
    return E, K

def read_pfm(fp):
    with open(fp, "rb") as f:
        assert f.readline().strip() == b"Pf"
        w, h = map(int, f.readline().split()); scale = float(f.readline())
        d = np.frombuffer(f.read(w*h*4), dtype="<f4" if scale < 0 else ">f4").reshape(h, w)
        return np.flipud(d).copy()

def read_ply(fp):
    with open(fp, "rb") as f:
        hdr = b""
        while True:
            l = f.readline(); hdr += l
            if l.strip() == b"end_header": break
        n = int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1])
        DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        M = np.frombuffer(f.read(n*DT.itemsize), dtype=DT)
    return np.stack([M["x"], M["y"], M["z"]], 1).astype(np.float64)

def auc(pos, neg):
    if len(pos) == 0 or len(neg) == 0: return None
    sc = np.concatenate([pos, neg])
    rk = rankdata(sc)
    n1, n0 = len(pos), len(neg)
    return float((rk[:n1].sum() - n1*(n1+1)/2) / (n1*n0))

# ---- 墙面口径(法医原样) ----
nfl = np.load(WALL + "/floor.npy"); up = nfl[:3]; dfl = nfl[3]
nw = np.array([0.46, -0.679, -0.572]); nw /= np.linalg.norm(nw)
u_ = np.cross(up, nw); u_ /= np.linalg.norm(u_); v_ = np.cross(nw, u_)
DW = 4.734
offs = np.load(WALL + "/offs.npy"); blobI = np.load(WALL + "/blob_idx.npy")
prep_ref = json.load(open("/Users/kaidongwang/Documents/progecttwo/_artifacts/da3_separation_probe_20260818/prep_summary.json"))

SPTS = read_ply(SPARSE_PLY)
r_a = SPTS @ nw + DW; pu_a = SPTS @ u_; pv_a = SPTS @ v_
box_a = (pu_a > -4.2) & (pu_a < 0.2) & (pv_a > -1.7) & (pv_a < 1.7)
a_wallband = box_a & (np.abs(r_a) < 0.06)            # 锚点在真墙带
a_blobband = box_a & (r_a > -0.55) & (r_a < -0.08)   # 锚点在偏移带(锚点自身污染)
print(f"sparse anchors {len(SPTS)}, wall-band {a_wallband.sum()}, blob-band {a_blobband.sum()}", flush=True)

VARIANTS = ["nogate", "gateA", "gateAB"]
res = {}
wp = {v: {t: dict(det_b=0, tot_b=0, kill_c=0, tot_c=0) for t in TAUS_CM} for v in VARIANTS}
pool = {v: dict(pos=[], neg=[]) for v in VARIANTS}
save_px = {}

for fr in FRAMES:
    E, Kfull = read_cam(fr)
    R, t = E[:3,:3], E[:3,3]
    D = read_pfm(f"{BASE}/out_P16k/depth_est/{fr:08d}.pfm")
    mk = np.array(Image.open(f"{BASE}/out_P16k/mask/{fr:08d}_final.png")) > 0
    H, W = D.shape
    Ks = Kfull.copy(); Ks[:2] *= S768

    # ---- 锚点投影(探针口径逐行复刻, 带索引) ----
    XC = SPTS @ R.T + t
    z = XC[:, 2]
    ok = z > 0.5
    idx0 = np.nonzero(ok)[0]
    px = XC[ok,0]/z[ok]*Kfull[0,0]+Kfull[0,2]; py = XC[ok,1]/z[ok]*Kfull[1,1]+Kfull[1,2]
    zin = z[ok]
    inim = (px>=0)&(px<4032)&(py>=0)&(py<3024)
    px, py, zin, idx0 = px[inim], py[inim], zin[inim], idx0[inim]
    ix = np.clip((px*S768).astype(int),0,W-1); iy = np.clip((py*S768).astype(int),0,H-1)
    dm = D[iy,ix]
    vis = (dm>0)&(np.abs(zin-dm)/np.maximum(dm,1e-6)<0.15)
    assert int(inim.sum())==prep_ref[str(fr)]["n_anchor_raw"] and int(vis.sum())==prep_ref[str(fr)]["n_anchor_vis"], f"fr{fr} anchor mismatch"
    gx, gy, za, ia = px[vis]*S768, py[vis]*S768, zin[vis], idx0[vis]
    n_a_wall = int(a_wallband[ia].sum()); n_a_blob = int(a_blobband[ia].sum())

    # ---- Delaunay + 逐三角平面 ----
    tri = Delaunay(np.stack([gx, gy], 1))
    simp = tri.simplices                      # (nt,3)
    zv = za[simp]                             # 顶点深度
    relrange = (zv.max(1)-zv.min(1))/zv.min(1)
    good_a = relrange <= REL_TH
    # 门b: 三角 3D 平面法向(相机系->世界系)
    Xc = np.stack([(gx-Ks[0,2])/Ks[0,0]*za, (gy-Ks[1,2])/Ks[1,1]*za, za], 1)
    P0, P1, P2 = Xc[simp[:,0]], Xc[simp[:,1]], Xc[simp[:,2]]
    nrm = np.cross(P1-P0, P2-P0)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    ndu = np.abs((nrm @ R) @ up)              # 世界系法向与重力上向夹角余弦
    good_b = good_a & ((ndu < SIN_A) | (ndu > COS_A))   # 近竖直面 或 近水平面
    n_tri = len(simp)

    # ---- 像素先验 ----
    yy, xx = np.nonzero(mk)
    dpx = D[yy, xx].astype(np.float64)
    Ppix = np.stack([xx, yy], 1).astype(np.float64)
    s = tri.find_simplex(Ppix)
    cov0 = s >= 0
    d_prior = np.full(len(xx), np.nan)
    ci = np.nonzero(cov0)[0]
    sc_ = s[ci]
    T = tri.transform[sc_]                    # (m,3,2->) transform
    b2 = np.einsum('ijk,ik->ij', T[:,:2,:], Ppix[ci]-T[:,2,:])
    w3 = np.concatenate([b2, 1-b2.sum(1, keepdims=True)], 1)
    invzv = 1.0/zv                            # (nt,3)
    d_prior[ci] = 1.0/np.einsum('ij,ij->i', w3, invzv[sc_])
    valid = {"nogate": cov0,
             "gateA":  cov0 & np.where(s>=0, good_a[np.maximum(s,0)], False),
             "gateAB": cov0 & np.where(s>=0, good_b[np.maximum(s,0)], False)}

    # ---- 标签(法医溯源) ----
    m = (blobI >= offs[fr]) & (blobI < offs[fr+1])
    loc = blobI[m] - offs[fr]                 # 正类: 偏移层像素
    ptc = np.stack([(xx-Ks[0,2])/Ks[0,0], (yy-Ks[1,2])/Ks[1,1], np.ones(len(xx))], 1)
    XW = (ptc*dpx[:,None]-t) @ R
    rr = XW @ nw + DW; puw = XW @ u_; pvw = XW @ v_
    inb = (puw>-4.2)&(puw<0.2)&(pvw>-1.7)&(pvw<1.7)
    clean = inb & (np.abs(rr) < 0.06)
    neg_i = np.nonzero(clean)[0]
    assert len(loc)==prep_ref[str(fr)]["n_blob_prov"] and int(clean.sum())==prep_ref[str(fr)]["n_clean"], f"fr{fr} label mismatch"

    score = np.abs(dpx - d_prior)             # gauge
    fres = dict(n_anchor_vis=int(vis.sum()), n_anchor_wallband=n_a_wall, n_anchor_blobband=n_a_blob,
                n_tri=n_tri, n_tri_gateA_bad=int((~good_a).sum()), n_tri_gateAB_bad=int((~good_b).sum()),
                n_blob=len(loc), n_clean=len(neg_i))
    lab_tri = s[np.concatenate([loc, neg_i])]
    fres["n_tri_wall_region"] = int(len(np.unique(lab_tri[lab_tri>=0])))
    for v in VARIANTS:
        vv = valid[v]
        fres[f"{v}_cov_mask"] = round(float(vv.mean()), 4)
        cb = vv[loc]; cc = vv[neg_i]
        fres[f"{v}_cov_blob"] = round(float(cb.mean()), 4) if len(loc) else None
        fres[f"{v}_cov_clean"] = round(float(cc.mean()), 4) if len(neg_i) else None
        pos_sc = score[loc][cb]; neg_sc = score[neg_i][cc]
        fres[f"{v}_auc"] = round(auc(pos_sc, neg_sc), 4) if (len(pos_sc) and len(neg_sc)) else None
        if v == "gateA":
            fres["blob_score_med_cm"] = round(float(np.median(pos_sc))*CM, 2) if len(pos_sc) else None
            fres["clean_score_med_cm"] = round(float(np.median(neg_sc))*CM, 2) if len(neg_sc) else None
        pool[v]["pos"].append(pos_sc); pool[v]["neg"].append(neg_sc)
        for tau in TAUS_CM:
            th = tau/CM
            wp[v][tau]["det_b"] += int((pos_sc > th).sum()); wp[v][tau]["tot_b"] += len(loc)
            wp[v][tau]["kill_c"] += int((neg_sc > th).sum()); wp[v][tau]["tot_c"] += len(neg_i)
    res[fr] = fres
    save_px[f"fr{fr}_loc"] = loc.astype(np.int64)
    save_px[f"fr{fr}_neg"] = neg_i.astype(np.int64)
    save_px[f"fr{fr}_score_blob"] = score[loc].astype(np.float32)
    save_px[f"fr{fr}_score_clean"] = score[neg_i].astype(np.float32)
    save_px[f"fr{fr}_validA_blob"] = valid["gateA"][loc]
    save_px[f"fr{fr}_validA_clean"] = valid["gateA"][neg_i]
    print(fr, json.dumps(fres, ensure_ascii=False), flush=True)

# ---- 汇总 ----
agg = {}
for v in VARIANTS:
    aucs = [res[fr][f"{v}_auc"] for fr in FRAMES if res[fr][f"{v}_auc"] is not None]
    # 加权(按 blob 数)中位与逐帧列表
    agg[v] = dict(
        per_frame_auc={str(fr): res[fr][f"{v}_auc"] for fr in FRAMES},
        auc_median=round(float(np.median(aucs)), 4), auc_min=round(float(np.min(aucs)), 4), auc_max=round(float(np.max(aucs)), 4),
        pooled_auc_CAVEAT_inflated=round(auc(np.concatenate(pool[v]["pos"]), np.concatenate(pool[v]["neg"])), 4),
        blob_uncovered_frac=round(1 - sum(res[fr][f"{v}_cov_blob"]*res[fr]["n_blob"] for fr in FRAMES)/sum(res[fr]["n_blob"] for fr in FRAMES), 4),
        clean_uncovered_frac=round(1 - sum(res[fr][f"{v}_cov_clean"]*res[fr]["n_clean"] for fr in FRAMES)/sum(res[fr]["n_clean"] for fr in FRAMES), 4))
    tbl = []
    for tau in TAUS_CM:
        d = wp[v][tau]
        tbl.append(dict(tau_cm=tau,
                        eff_recall=round(d["det_b"]/max(d["tot_b"],1), 4),      # 未覆盖记漏检
                        eff_kill=round(d["kill_c"]/max(d["tot_c"],1), 4)))      # 未覆盖记不误杀
    agg[v]["working_points"] = tbl
json.dump(dict(per_frame=res, agg=agg,
               anchors_total=len(SPTS), anchors_wallband=int(a_wallband.sum()), anchors_blobband=int(a_blobband.sum()),
               config=dict(rel_th=REL_TH, angle_deg=20.0, occl_gate=0.15, taus_cm=TAUS_CM)),
          open(OUTD + "/delaunay_prior_results.json", "w"), indent=1)
np.savez_compressed(OUTD + "/labeled_scores.npz", **save_px)
print("SAVED", OUTD)
