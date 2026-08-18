# DA3 分离度探针 - 步骤3: 锚点拟合 + 三方对拍 + ROC
# a = 墙面真值(法医拟合平面沿光轴逐像素深度)
# b = CasDiffMVS 深度 (out_P16k/depth_est)
# c = DA3 锚点拟合深度 (canonical ×f_proc/300 → 米, 再对稀疏锚点稳健 scale+shift → gauge)
# 门信号(可部署) g = |b - c|; 检出=偏移层像素 g>τ; 误报=干净墙像素 g>τ
import numpy as np, json, cv2

SC = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad"
OUT = SC + "/da3probe"
FRAMES = [78, 79, 80, 81, 82, 83, 85, 86, 87, 100, 103, 107, 125]
S768 = 768 / 4032.0
GAUGE_M = 0.42          # 1 gauge ≈ 0.42 m(记账口径)
CM = 42.0               # gauge → cm
TAUS_CM = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]

def robust_fit(x, y, rounds=4):
    """y ≈ a x + b, IRLS 3×1.4826×MAD 截断 (08-07 锚点拟合口径的复刻: 稳健 scale+shift)"""
    keep = np.ones(len(x), bool)
    a = b = None
    for _ in range(rounds):
        X = np.stack([x[keep], np.ones(keep.sum())], 1)
        sol, *_ = np.linalg.lstsq(X, y[keep], rcond=None)
        a, b = sol
        r = y - (a * x + b)
        med = np.median(r[keep]); mad = np.median(np.abs(r[keep] - med))
        thr = max(3 * 1.4826 * mad, 1e-4)
        keep = np.abs(r - med) < thr
    r = y - (a * x + b)
    return a, b, keep, r

res = {}
pool = dict(g_blob=[], g_clean=[], ba_blob=[], ca_blob=[], ca_clean=[], ba_clean=[],
            sba_blob=[], sca_blob=[])
for fr in FRAMES:
    P = np.load(f"{OUT}/frame_{fr}.npz")
    A = np.load(f"{OUT}/da3_{fr}.npz")
    K = P["Kfull"]
    f_proc = (K[0, 0] + K[1, 1]) / 2 * (504 / 4032.0)
    da3_m = A["depth"] * (f_proc / 300.0)               # canonical → 米
    da3_768 = cv2.resize(da3_m, (768, 576), interpolation=cv2.INTER_LINEAR)

    # ---- 锚点拟合(稀疏锚点: gauge z vs DA3 米) ----
    vis = P["anchor_vis"]
    px, py, zg = P["anchor_px"][vis], P["anchor_py"][vis], P["anchor_z"][vis]
    if len(px) > 20000:
        sel = np.random.default_rng(fr).choice(len(px), 20000, replace=False)
        px, py, zg = px[sel], py[sel], zg[sel]
    gx, gy = px * S768, py * S768
    x0 = np.clip(gx.astype(int), 0, 767); y0 = np.clip(gy.astype(int), 0, 575)
    x1 = np.clip(x0 + 1, 0, 767); y1 = np.clip(y0 + 1, 0, 575)
    wx = gx - x0; wy = gy - y0
    dd = (da3_768[y0, x0] * (1 - wx) * (1 - wy) + da3_768[y0, x1] * wx * (1 - wy)
          + da3_768[y1, x0] * (1 - wx) * wy + da3_768[y1, x1] * wx * wy)
    a_fit, b_fit, keep, resid = robust_fit(dd.astype(np.float64), zg.astype(np.float64))

    # ---- 三方对拍 ----
    aP = P["depth_plane"].astype(np.float64)   # 平面真值 z-depth (gauge)
    bM = P["depth_mvs"].astype(np.float64)     # MVS z-depth (gauge)
    cD = a_fit * da3_768[P["yy"], P["xx"]].astype(np.float64) + b_fit  # DA3 拟合 (gauge)
    loc = P["blob_loc"]; clean = P["clean"]
    ba = np.abs(bM - aP); ca = np.abs(cD - aP); g = np.abs(bM - cD)
    sba = bM - aP; sca = cD - aP
    res[fr] = dict(
        f_proc=float(f_proc), scale=float(a_fit), shift=float(b_fit),
        scale_x042=float(a_fit * GAUGE_M),
        n_anchor=int(len(dd)), inlier=float(keep.mean()),
        anchor_resid_med_cm=float(np.median(np.abs(resid[keep])) * CM),
        anchor_resid_rms_cm=float(np.sqrt(np.mean(resid[keep] ** 2)) * CM),
        n_blob=int(len(loc)), n_clean=int(clean.sum()),
        ba_blob_med_cm=float(np.median(ba[loc]) * CM) if len(loc) else None,
        ca_blob_med_cm=float(np.median(ca[loc]) * CM) if len(loc) else None,
        sba_blob_med_cm=float(np.median(sba[loc]) * CM) if len(loc) else None,
        sca_blob_med_cm=float(np.median(sca[loc]) * CM) if len(loc) else None,
        ca_clean_med_cm=float(np.median(ca[clean]) * CM) if clean.sum() else None,
        ba_clean_med_cm=float(np.median(ba[clean]) * CM) if clean.sum() else None,
        g_blob_med_cm=float(np.median(g[loc]) * CM) if len(loc) else None,
        g_clean_med_cm=float(np.median(g[clean]) * CM) if clean.sum() else None)
    pool["g_blob"].append(g[loc]); pool["g_clean"].append(g[clean])
    pool["ba_blob"].append(ba[loc]); pool["ca_blob"].append(ca[loc])
    pool["ca_clean"].append(ca[clean]); pool["ba_clean"].append(ba[clean])
    pool["sba_blob"].append(sba[loc]); pool["sca_blob"].append(sca[loc])
    print(fr, json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in res[fr].items()}, ensure_ascii=False))

P_ = {k: np.concatenate(v) for k, v in pool.items()}
def q(a, ps=[10, 25, 50, 75, 90]):
    return {str(p): round(float(np.percentile(a, p)) * CM, 2) for p in ps}

agg = dict(
    n_blob=int(len(P_["g_blob"])), n_clean=int(len(P_["g_clean"])),
    ba_blob_cm=q(P_["ba_blob"]), ca_blob_cm=q(P_["ca_blob"]),
    sba_blob_cm=q(P_["sba_blob"]), sca_blob_cm=q(P_["sca_blob"]),
    ba_clean_cm=q(P_["ba_clean"]), ca_clean_cm=q(P_["ca_clean"]),
    g_blob_cm=q(P_["g_blob"]), g_clean_cm=q(P_["g_clean"]))

# ROC: 门信号 g=|b-c|
roc = []
for tau in TAUS_CM:
    t = tau / CM
    roc.append(dict(tau_cm=tau,
                    tpr=round(float((P_["g_blob"] > t).mean()), 4),
                    fpr=round(float((P_["g_clean"] > t).mean()), 4),
                    ca_clean_exceed=round(float((P_["ca_clean"] > t).mean()), 4)))
# AUC
sc = np.concatenate([P_["g_blob"], P_["g_clean"]])
lb = np.concatenate([np.ones(len(P_["g_blob"])), np.zeros(len(P_["g_clean"]))])
o = np.argsort(sc)
rk = np.empty(len(sc)); rk[o] = np.arange(1, len(sc) + 1)
n1 = lb.sum(); n0 = len(lb) - n1
auc = (rk[lb == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
# 平面参照 ROC(oracle 口径: 检出=|b-a|…不, 检出仍是门, 此处给 |c-a| 对照): 略, ca_clean_exceed 已含
agg["auc_gate"] = round(float(auc), 4)
print("AGG", json.dumps(agg, ensure_ascii=False, indent=1))
print("ROC", json.dumps(roc, ensure_ascii=False))
json.dump(dict(per_frame=res, agg=agg, roc=roc), open(OUT + "/separation_results.json", "w"), indent=1)
print("OK")
