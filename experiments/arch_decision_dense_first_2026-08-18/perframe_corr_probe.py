# 白墙第2刀探针: 每帧低频偏差校正(纯锚点 IRLS, 可部署形态)后重测门可分性
# 背景: 第1刀判死, oracle 挖出真凶=干净墙 MVS 深度自身 +1.6~2.5cm 系统性后偏且逐帧漂移(fr107/125 +5cm)
# 三档校正模型(只用全场景锚点残差, 不碰法医标签):
#   C0: e ~ a                  常数偏移
#   C1: e ~ a + b*d            scale+shift(深度线性)
#   C2: e ~ a + b*u + c*v      图像域平面倾斜(u,v 归一化像素坐标)
# e = d_MVS(锚点像素) - z_锚点, 校正: d_corr = d - e_hat
# 判据① clean 墙 |d_corr - 真值平面| 逐帧 p50 < 1cm
# 判据② oracle 门(r=|d_corr - d_plane|)工作点 召回>=90% 且 误杀<=2%(基线 81%/2.8% signed tau=5cm)
# 保护性: 非墙锚点 |e| p50/p90 校正前后, 变坏=红牌
# 注: 原 da3probe/frame_*.npz 被系统清 /tmp 清掉, 本脚本全部从耐久源自算(口径=prep.py+delaunay_prior_roc.py 逐行复刻, 断言对齐 prep_summary.json)
import numpy as np, json
from PIL import Image
from scipy.spatial import Delaunay
from scipy.stats import rankdata

BASE = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
WALL = "/Users/kaidongwang/Documents/progecttwo/_artifacts/wall_forensics_20260818"
OUTD = "/Users/kaidongwang/Documents/progecttwo/_artifacts/perframe_corr_20260818"
SPARSE_PLY = "/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/ply_P16KH.ply"
FRAMES = [78, 79, 80, 81, 82, 83, 85, 86, 87, 100, 103, 107, 125]
S768 = 768 / 4032.0
CM = 42.0
TAUS = [round(t, 2) for t in np.arange(0.3, 10.01, 0.1)]   # 细网格找工作点
REL_TH = 0.15   # Delaunay 门a(第1刀原口径)
MODELS = ["C0", "C1", "C2"]
K_IRLS = 3.0

prep_ref = json.load(open("/Users/kaidongwang/Documents/progecttwo/_artifacts/da3_separation_probe_20260818/prep_summary.json"))
knife1 = json.load(open("/Users/kaidongwang/Documents/progecttwo/_artifacts/delaunay_prior_20260818/delaunay_prior_results.json"))

# ---- 墙面口径(法医原样, 只用于诊断/标签评估, 不进拟合) ----
nfl = np.load(WALL + "/floor.npy"); up = nfl[:3]
nw = np.array([0.46, -0.679, -0.572]); nw /= np.linalg.norm(nw)
u_ = np.cross(up, nw); u_ /= np.linalg.norm(u_); v_ = np.cross(nw, u_)
DW = 4.734
mw = json.load(open(WALL + "/measure_wall.json"))
NV = np.array(mw["P16k"]["nv"]); DFIT = mw["P16k"]["d"]   # 真值平面(稳健拟合)
offs = np.load(WALL + "/offs.npy"); blobI = np.load(WALL + "/blob_idx.npy")

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
    sc = np.concatenate([pos, neg]); rk = rankdata(sc)
    n1, n0 = len(pos), len(neg)
    return float((rk[:n1].sum() - n1*(n1+1)/2) / (n1*n0))

def irls(X, e, k=K_IRLS, iters=20):
    # 稳健 IRLS: MAD 硬截断, 迭代到 inlier 集稳定
    beta = np.linalg.lstsq(X, e, rcond=None)[0]
    keep = np.ones(len(e), bool)
    for _ in range(iters):
        rr = e - X @ beta
        med = np.median(rr)
        sig = max(1.4826 * np.median(np.abs(rr - med)), 1e-3)  # 下限 0.042cm 防塌缩
        nk = np.abs(rr - med) < k * sig
        if nk.sum() < X.shape[1] + 2: break
        if (nk == keep).all():
            keep = nk; break
        keep = nk
        beta = np.linalg.lstsq(X[keep], e[keep], rcond=None)[0]
    return beta, keep

SPTS = read_ply(SPARSE_PLY)
print("sparse anchors total:", len(SPTS), flush=True)

res = {}
MODELS_R = ["raw"] + MODELS
# 工作点累计: oracle(全覆盖) x {abs,signed} x model ; delaunay {nogate,gateA} x model x abs
wp_o = {m: {s: {t: [0, 0, 0, 0] for t in TAUS} for s in ("abs", "sgn")} for m in MODELS_R}
wp_d = {g: {m: {t: [0, 0, 0, 0] for t in TAUS} for m in MODELS_R} for g in ("nogate", "gateA")}

for fr in FRAMES:
    E, Kfull = read_cam(fr)
    R, t = E[:3, :3], E[:3, 3]
    D = read_pfm(f"{BASE}/out_P16k/depth_est/{fr:08d}.pfm")
    mk = np.array(Image.open(f"{BASE}/out_P16k/mask/{fr:08d}_final.png")) > 0
    H, W = D.shape
    Ks = Kfull.copy(); Ks[:2] *= S768

    # ---- 像素: 世界坐标 / 标签 / 真值平面深度(prep.py 口径) ----
    yy, xx = np.nonzero(mk)
    d = D[yy, xx].astype(np.float64)
    ptc = np.stack([(xx - Ks[0, 2]) / Ks[0, 0], (yy - Ks[1, 2]) / Ks[1, 1], np.ones(len(xx))], 1)
    XW = (ptc * d[:, None] - t) @ R
    rr_ = XW @ nw + DW; puw = XW @ u_; pvw = XW @ v_
    inb = (puw > -4.2) & (puw < 0.2) & (pvw > -1.7) & (pvw < 1.7)
    clean = inb & (np.abs(rr_) < 0.06)
    m_ = (blobI >= offs[fr]) & (blobI < offs[fr + 1])
    loc = blobI[m_] - offs[fr]
    neg_i = np.nonzero(clean)[0]
    assert len(loc) == prep_ref[str(fr)]["n_blob_prov"] and len(neg_i) == prep_ref[str(fr)]["n_clean"], f"fr{fr} label mismatch"
    C = -R.T @ t
    dirs = ptc @ R
    denom = dirs @ NV
    dpl = -(C @ NV + DFIT) / denom           # 真值平面 z-depth

    # ---- 锚点投影+遮挡门(第1刀口径) ----
    XC = SPTS @ R.T + t
    z = XC[:, 2]
    ok = z > 0.5
    idx0 = np.nonzero(ok)[0]
    px = XC[ok, 0] / z[ok] * Kfull[0, 0] + Kfull[0, 2]
    py = XC[ok, 1] / z[ok] * Kfull[1, 1] + Kfull[1, 2]
    zin = z[ok]
    inim = (px >= 0) & (px < 4032) & (py >= 0) & (py < 3024)
    px, py, zin, idx0 = px[inim], py[inim], zin[inim], idx0[inim]
    ix = np.clip((px * S768).astype(int), 0, W - 1); iy = np.clip((py * S768).astype(int), 0, H - 1)
    dm = D[iy, ix].astype(np.float64)
    vis = (dm > 0) & (np.abs(zin - dm) / np.maximum(dm, 1e-6) < 0.15)
    assert int(inim.sum()) == prep_ref[str(fr)]["n_anchor_raw"] and int(vis.sum()) == prep_ref[str(fr)]["n_anchor_vis"], f"fr{fr} anchor mismatch"
    gpx, gpy, gz, gdm, ia = px[vis], py[vis], zin[vis], dm[vis], idx0[vis]
    e = gdm - gz                      # gauge; +=MVS 比锚点深(后偏)

    # 锚点世界坐标(墙带/非墙定位, 仅诊断与安全度量)
    Xw_a = SPTS[ia]
    r_a = Xw_a @ nw + DW; pu_a = Xw_a @ u_; pv_a = Xw_a @ v_
    box = (pu_a > -4.2) & (pu_a < 0.2) & (pv_a > -1.7) & (pv_a < 1.7)
    wallband = box & (np.abs(r_a) < 0.06)
    nonwall = ~(box & (r_a > -0.55) & (r_a < 0.06))   # 排除墙带+偏移带整柱

    un_a = (gpx * S768 - W / 2) / W; vn_a = (gpy * S768 - H / 2) / H
    XD = {"C0": np.ones((len(e), 1)),
          "C1": np.stack([np.ones(len(e)), gdm], 1),
          "C2": np.stack([np.ones(len(e)), un_a, vn_a], 1)}

    fits, ehat_a = {}, {}
    for m in MODELS:
        beta, keep = irls(XD[m], e)
        fits[m] = dict(beta=[float(b) for b in beta], inlier_frac=round(float(keep.mean()), 4))
        ehat_a[m] = XD[m] @ beta

    # ---- 像素校正 ----
    un_p = (xx - W / 2) / W; vn_p = (yy - H / 2) / H
    XP = {"C0": np.ones((len(d), 1)),
          "C1": np.stack([np.ones(len(d)), d], 1),
          "C2": np.stack([np.ones(len(d)), un_p, vn_p], 1)}
    d_corr = {"raw": d}
    for m in MODELS:
        d_corr[m] = d - XP[m] @ np.array(fits[m]["beta"])

    # ---- Delaunay 先验(第1刀原样重建) ----
    gx, gy = gpx * S768, gpy * S768
    tri = Delaunay(np.stack([gx, gy], 1))
    simp = tri.simplices
    assert len(simp) == knife1["per_frame"][str(fr)]["n_tri"], f"fr{fr} n_tri mismatch"
    zv = gz[simp]
    good_a = (zv.max(1) - zv.min(1)) / zv.min(1) <= REL_TH
    Ppix = np.stack([xx, yy], 1).astype(np.float64)
    s = tri.find_simplex(Ppix)
    cov0 = s >= 0
    d_prior = np.full(len(xx), np.nan)
    ci = np.nonzero(cov0)[0]
    T = tri.transform[s[ci]]
    b2 = np.einsum('ijk,ik->ij', T[:, :2, :], Ppix[ci] - T[:, 2, :])
    w3 = np.concatenate([b2, 1 - b2.sum(1, keepdims=True)], 1)
    d_prior[ci] = 1.0 / np.einsum('ij,ij->i', w3, (1.0 / zv)[s[ci]])
    valid = {"nogate": cov0, "gateA": cov0 & np.where(s >= 0, good_a[np.maximum(s, 0)], False)}

    fres = dict(n_anchor_vis=int(vis.sum()), n_anchor_wallband=int(wallband.sum()), n_anchor_nonwall=int(nonwall.sum()),
                n_blob=len(loc), n_clean=len(neg_i),
                anchor_e_med_cm=round(float(np.median(e)) * CM, 2),
                anchor_e_med_wallband_cm=round(float(np.median(e[wallband])) * CM, 2) if wallband.sum() else None)
    # 拟合量
    for m in MODELS:
        b = fits[m]["beta"]
        fr_fit = dict(inlier_frac=fits[m]["inlier_frac"])
        if m == "C0": fr_fit["a_cm"] = round(b[0] * CM, 2)
        elif m == "C1":
            fr_fit["a_cm"] = round(b[0] * CM, 2); fr_fit["b_slope"] = round(b[1], 5)
            fr_fit["ehat_at_wallmed_cm"] = round((b[0] + b[1] * float(np.median(d[clean]))) * CM, 2) if clean.sum() else None
        else:
            fr_fit["a_center_cm"] = round(b[0] * CM, 2)
            fr_fit["bu_cm_per_img"] = round(b[1] * CM, 2); fr_fit["cv_cm_per_img"] = round(b[2] * CM, 2)
        fres[f"fit_{m}"] = fr_fit

    # ---- 保护性: 非墙锚点残差前后 ----
    saf = {}
    e_nw = np.abs(e[nonwall])
    saf["before"] = dict(p50_cm=round(float(np.percentile(e_nw, 50)) * CM, 3), p90_cm=round(float(np.percentile(e_nw, 90)) * CM, 3))
    for m in MODELS:
        ea = np.abs((e - ehat_a[m])[nonwall])
        saf[m] = dict(p50_cm=round(float(np.percentile(ea, 50)) * CM, 3), p90_cm=round(float(np.percentile(ea, 90)) * CM, 3))
    fres["safety_nonwall_abs_e"] = saf

    # ---- 判据①: clean 墙 |d_corr - 真值平面| p50 ----
    c1 = {}
    for m in MODELS_R:
        rr = d_corr[m][neg_i] - dpl[neg_i]
        c1[m] = dict(p50_abs_cm=round(float(np.median(np.abs(rr))) * CM, 3),
                     med_signed_cm=round(float(np.median(rr)) * CM, 3))
    fres["clean_vs_truthplane"] = c1

    # ---- 判据②a: oracle 门(先验=真值平面) ----
    o = {}
    for m in MODELS_R:
        sg = d_corr[m] - dpl
        pos_s, neg_s = sg[loc], sg[neg_i]
        o[m] = dict(auc_abs=round(auc(np.abs(pos_s), np.abs(neg_s)), 4),
                    auc_sgn=round(auc(pos_s, neg_s), 4))
        for tau in TAUS:
            th = tau / CM
            wa = wp_o[m]["abs"][tau]; ws = wp_o[m]["sgn"][tau]
            wa[0] += int((np.abs(pos_s) > th).sum()); wa[1] += len(loc)
            wa[2] += int((np.abs(neg_s) > th).sum()); wa[3] += len(neg_i)
            ws[0] += int((pos_s > th).sum()); ws[1] += len(loc)
            ws[2] += int((neg_s > th).sum()); ws[3] += len(neg_i)
    fres["oracle"] = o

    # ---- 判据②b: Delaunay 先验门 ----
    dd = {}
    for g in ("nogate", "gateA"):
        vv = valid[g]
        cb, cc = vv[loc], vv[neg_i]
        gg = dict(cov_blob=round(float(cb.mean()), 4) if len(loc) else None,
                  cov_clean=round(float(cc.mean()), 4) if len(neg_i) else None)
        for m in MODELS_R:
            sc_ = np.abs(d_corr[m] - d_prior)
            pos_sc, neg_sc = sc_[loc][cb], sc_[neg_i][cc]
            gg[f"auc_{m}"] = round(auc(pos_sc, neg_sc), 4) if (len(pos_sc) and len(neg_sc)) else None
            for tau in TAUS:
                th = tau / CM
                w = wp_d[g][m][tau]
                w[0] += int((pos_sc > th).sum()); w[1] += len(loc)      # 未覆盖记漏检
                w[2] += int((neg_sc > th).sum()); w[3] += len(neg_i)    # 未覆盖记不误杀
        dd[g] = gg
    fres["delaunay"] = dd
    # 第1刀复现检查(raw gateA AUC)
    fres["knife1_gateA_auc_repro"] = dict(mine=dd["gateA"]["auc_raw"], knife1=knife1["per_frame"][str(fr)]["gateA_auc"])
    res[fr] = fres
    print(fr, json.dumps(dict(e_med=fres["anchor_e_med_cm"], e_wall=fres["anchor_e_med_wallband_cm"],
                              C0=fres["fit_C0"]["a_cm"],
                              c1={m: c1[m]["p50_abs_cm"] for m in MODELS_R},
                              oA={m: o[m]["auc_abs"] for m in MODELS_R}), ensure_ascii=False), flush=True)

# ---- 汇总 ----
def wp_table(wpd, taus):
    return [dict(tau_cm=t, recall=round(wpd[t][0] / max(wpd[t][1], 1), 4), kill=round(wpd[t][2] / max(wpd[t][3], 1), 4)) for t in taus]

def best_op(wpd):
    # 找 kill<=2% 下最大 recall 的 tau; 及 recall>=90% 下最小 kill
    ops = [(t, wpd[t][0] / max(wpd[t][1], 1), wpd[t][2] / max(wpd[t][3], 1)) for t in TAUS]
    ok2 = [(r, -t, k, t) for t, r, k in ops if k <= 0.02]
    hi90 = [(k, t, r) for t, r, k in ops if r >= 0.90]
    out = {}
    if ok2:
        r, _, k, t = max(ok2); out["max_recall_at_kill2pct"] = dict(tau_cm=t, recall=round(r, 4), kill=round(k, 4))
    else: out["max_recall_at_kill2pct"] = None
    if hi90:
        k, t, r = min(hi90); out["min_kill_at_recall90"] = dict(tau_cm=t, recall=round(r, 4), kill=round(k, 4))
    else: out["min_kill_at_recall90"] = None
    out["pass_90_2"] = any(r >= 0.90 and k <= 0.02 for _, r, k in ops)
    return out

agg = dict(criterion1={}, criterion2_oracle={}, criterion2_delaunay={}, safety={})
FR12 = [f for f in FRAMES if f != 107]
for m in MODELS_R:
    p50s = {fr: res[fr]["clean_vs_truthplane"][m]["p50_abs_cm"] for fr in FRAMES}
    agg["criterion1"][m] = dict(
        per_frame_p50_cm={str(k): v for k, v in p50s.items()},
        n_under_1cm_excl107=sum(1 for fr in FR12 if p50s[fr] < 1.0), n_frames_excl107=len(FR12),
        n_under_1cm_all13=sum(1 for fr in FRAMES if p50s[fr] < 1.0),
        fr107_p50_cm=p50s[107], median_p50_cm=round(float(np.median(list(p50s.values()))), 3))
    for sk in ("abs", "sgn"):
        a = {fr: res[fr]["oracle"][m][f"auc_{sk}"] for fr in FRAMES}
        agg["criterion2_oracle"].setdefault(m, {})[sk] = dict(
            per_frame_auc={str(k): v for k, v in a.items()}, auc_median=round(float(np.median(list(a.values()))), 4),
            auc_min=round(min(a.values()), 4),
            best_op=best_op(wp_o[m][sk]),
            working_points=[w for w in wp_table(wp_o[m][sk], TAUS) if round(w["tau_cm"] * 10) % 5 == 0])
    for g in ("nogate", "gateA"):
        a = {fr: res[fr]["delaunay"][g][f"auc_{m}"] for fr in FRAMES}
        av = [x for x in a.values() if x is not None]
        agg["criterion2_delaunay"].setdefault(m, {})[g] = dict(
            per_frame_auc={str(k): v for k, v in a.items()}, auc_median=round(float(np.median(av)), 4),
            auc_min=round(min(av), 4),
            best_op=best_op(wp_d[g][m]),
            working_points=[w for w in wp_table(wp_d[g][m], TAUS) if round(w["tau_cm"] * 10) % 5 == 0])
    if m != "raw":
        b50 = [res[fr]["safety_nonwall_abs_e"]["before"]["p50_cm"] for fr in FRAMES]
        b90 = [res[fr]["safety_nonwall_abs_e"]["before"]["p90_cm"] for fr in FRAMES]
        a50 = [res[fr]["safety_nonwall_abs_e"][m]["p50_cm"] for fr in FRAMES]
        a90 = [res[fr]["safety_nonwall_abs_e"][m]["p90_cm"] for fr in FRAMES]
        agg["safety"][m] = dict(
            med_before_p50_cm=round(float(np.median(b50)), 3), med_after_p50_cm=round(float(np.median(a50)), 3),
            med_before_p90_cm=round(float(np.median(b90)), 3), med_after_p90_cm=round(float(np.median(a90)), 3),
            n_frames_p50_worse=sum(1 for x, y in zip(b50, a50) if y > x),
            n_frames_p90_worse=sum(1 for x, y in zip(b90, a90) if y > x))

json.dump(dict(config=dict(irls_k=K_IRLS, occl_gate=0.15, rel_th=REL_TH, cm_per_gauge=CM,
                           models=dict(C0="e~a", C1="e~a+b*d", C2="e~a+b*u+c*v (u,v 归一化)"),
                           fit_scope="全场景可见锚点(含墙), 不碰法医标签", frames=FRAMES,
                           fr107_note="Delaunay gateA 对 blob 覆盖=0, 单列"),
               per_frame={str(k): v for k, v in res.items()}, agg=agg),
          open(OUTD + "/perframe_corr_results.json", "w"), indent=1)
print("SAVED", OUTD + "/perframe_corr_results.json")
