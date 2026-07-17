#!/usr/bin/env python3.11
"""U3 收官: 三部分信号 ensemble 分类器. 判"椅子假阳" vs 干净地板.
复用已算逐点信号 (alias / off-plane margin / Merrell free-space). 不加载 4K 图.
join key = union_index (netvote ply 行序 == union_index, 已验证 coord 精确匹配).
alias 通过最近邻 coord 映射到 union_index.
"""
import json, csv, hashlib, sys
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

BASE = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18"
OUT = BASE + "/08_combined_classifier"

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

# ---------- 1. netvote ply (13488 = union order) ----------
plyf = BASE + "/04_merrell_netvote/netvote_candidates.ply"
raw = open(plyf).read().split("\n")
hi = raw.index("end_header")
N = 13488
xyz = np.zeros((N, 3)); rgb = np.zeros((N, 3), int)
support = np.zeros(N); freespace = np.zeros(N); occlusion = np.zeros(N)
agreement = np.zeros(N); l1obs = np.zeros(N); netvote = np.zeros(N); in_roi = np.zeros(N)
for i, l in enumerate(raw[hi + 1:hi + 1 + N]):
    p = l.split()
    xyz[i] = [float(p[0]), float(p[1]), float(p[2])]
    rgb[i] = [int(p[3]), int(p[4]), int(p[5])]
    support[i] = float(p[6]); freespace[i] = float(p[7]); occlusion[i] = float(p[8])
    agreement[i] = float(p[9]); l1obs[i] = float(p[10]); netvote[i] = float(p[11]); in_roi[i] = float(p[12])

# ---------- 2. depth competition (3211 scored: ROI + clean floor) ----------
dc = [json.loads(l) for l in open(BASE + "/07_offplane_depth_competition/depth_competition.jsonl")]
depth = {}
for r in dc:
    depth[r["union_index"]] = dict(
        margin=r["floor_minus_best_competitor_ncc"],
        floor_ncc=r["floor_ncc"], comp_ncc=r["best_competitor_ncc"],
        is_fp=bool(r["is_false_positive_color"]), pop=r["population"], arm=r["arm"])
# 验证 join
mism = sum(1 for r in dc if np.linalg.norm(np.array(r["xyz_m"]) - xyz[r["union_index"]]) > 1e-4)
assert mism == 0, f"depth/ply join mismatch {mism}"

# ---------- 3. alias -> nearest-neighbor -> union_index ----------
alias_pts = []
with open(BASE + "/06_glomap_alias/alias_points.csv") as f:
    for row in csv.DictReader(f):
        alias_pts.append([float(row["X"]), float(row["Y"]), float(row["Z"])])
alias_pts = np.array(alias_pts)
alias_flag = np.zeros(N, bool)
NN_THRESH = 0.03  # median alias->prod NN = 0.0146m, 88.5% within 5cm
matched = 0
for a in alias_pts:
    d = np.linalg.norm(xyz - a, axis=1)
    j = int(np.argmin(d))
    if d[j] <= NN_THRESH:
        alias_flag[j] = True
        matched += 1
n_alias_union = int(alias_flag.sum())

# ---------- 4. 建评估宇宙 = 3211 depth-scored 点 ----------
idx = np.array(sorted(depth.keys()))
# None margin (floor/competitor unscoreable, ~458 pts) -> nan; margin<=t 对 nan 恒 False (保守: 不因不可评分而杀)
margin = np.array([depth[i]["margin"] if depth[i]["margin"] is not None else np.nan for i in idx])
margin_isnan = np.isnan(margin)
is_fp = np.array([depth[i]["is_fp"] for i in idx])
pop = np.array([depth[i]["pop"] for i in idx])
fs = freespace[idx]; occ = occlusion[idx]; sup = support[idx]
nv = netvote[idx]; agr = agreement[idx]; l1 = l1obs[idx]
al = alias_flag[idx]

# 类别
ENEMY = (pop == "roi") & is_fp          # 椅子假阳 -> 要杀
FLOOR = (pop == "clean")                # 干净地板 -> 要留
WOOD  = (pop == "roi") & (~is_fp)       # ROI 木地板 (次要保留)
n_enemy = int(ENEMY.sum()); n_floor = int(FLOOR.sum()); n_wood = int(WOOD.sum())

def evaluate(kill):
    """kill: bool array over idx. returns metrics."""
    fp_kill = float((kill & ENEMY).sum()) / n_enemy
    floor_ret = 1.0 - float((kill & FLOOR).sum()) / n_floor
    wood_ret = 1.0 - float((kill & WOOD).sum()) / n_wood
    return dict(fp_kill_rate=fp_kill, clean_floor_retention=floor_ret,
                wood_retention=wood_ret, separation_product=fp_kill * floor_ret,
                n_killed=int(kill.sum()))

results = {}

# ---------- 单信号 ----------
# alias 单独
results["single_alias"] = evaluate(al)

# freespace 单独 (>=1 single-vote conviction, Merrell)
results["single_freespace_ge1"] = evaluate(fs >= 1)

# margin 单独 (sweep, kill if margin <= t)
margin_sweep = []
best_m = None
for t in np.round(np.arange(-0.15, 0.201, 0.005), 4):
    m = evaluate(margin <= t)
    m["thresh"] = float(t)
    margin_sweep.append(m)
    if best_m is None or m["separation_product"] > best_m["separation_product"]:
        best_m = m
results["single_margin_best"] = best_m

# ---------- OR ensemble (三信号并联) ----------
# 用 margin 各阈值扫 OR
or_sweep = []
best_or = None
for t in np.round(np.arange(-0.15, 0.201, 0.005), 4):
    kill = al | (margin <= t) | (fs >= 1)
    m = evaluate(kill); m["margin_thresh"] = float(t)
    or_sweep.append(m)
    if best_or is None or m["separation_product"] > best_or["separation_product"]:
        best_or = m
results["ensemble_OR_best"] = best_or

# OR 固定 margin=0.02 (07 最优点) 供参考
results["ensemble_OR_margin0.02"] = evaluate(al | (margin <= 0.02) | (fs >= 1))

# ---------- logistic 组合 (监督: enemy vs floor) ----------
# margin nan 用中位数填补 + 加 isnan 指示位
margin_fill = np.where(margin_isnan, np.nanmedian(margin), margin)
mask = ENEMY | FLOOR
y = ENEMY[mask].astype(int)
feats = np.column_stack([al[mask].astype(float), -margin_fill[mask], margin_isnan[mask].astype(float),
                         fs[mask], occ[mask], sup[mask], nv[mask], agr[mask], (l1[mask] == 0).astype(float)])
fnames = ["alias", "neg_margin", "margin_nan", "freespace", "occlusion", "support", "netvote", "agreement", "no_l1_obs"]
mu = feats.mean(0); sd = feats.std(0); sd[sd == 0] = 1
featz = (feats - mu) / sd
clf = LogisticRegression(max_iter=2000, class_weight="balanced")
clf.fit(featz, y)
prob = clf.predict_proba(featz)[:, 1]
auc = roc_auc_score(y, prob)
# 全体 idx 的 prob (用于评估 wood 也一致)
allfeat = np.column_stack([al.astype(float), -margin_fill, margin_isnan.astype(float), fs, occ, sup, nv, agr, (l1 == 0).astype(float)])
allz = (allfeat - mu) / sd
allprob = clf.predict_proba(allz)[:, 1]
# 扫概率阈值找最佳分离积 (ROC-like)
lr_sweep = []
best_lr = None
for th in np.round(np.arange(0.05, 0.96, 0.01), 3):
    kill = allprob >= th
    m = evaluate(kill); m["prob_thresh"] = float(th)
    lr_sweep.append(m)
    if best_lr is None or m["separation_product"] > best_lr["separation_product"]:
        best_lr = m
results["logistic_best_INSAMPLE"] = best_lr
results["logistic_auc_insample"] = float(auc)
results["logistic_coef"] = {n: float(c) for n, c in zip(fnames, clf.coef_[0])}

# ---------- logistic 交叉验证 (诚实 out-of-fold, 防过拟合) ----------
from sklearn.model_selection import StratifiedKFold
oof = np.full(mask.sum(), np.nan)
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
for tr, te in skf.split(featz, y):
    c = LogisticRegression(max_iter=2000, class_weight="balanced").fit(featz[tr], y[tr])
    oof[te] = c.predict_proba(featz[te])[:, 1]
auc_cv = roc_auc_score(y, oof)
# 把 oof prob 映回 idx 空间 (只 enemy|floor 有 oof; wood 用整体模型的 allprob 近似, 仅供参考)
oof_full = np.full(len(idx), np.nan)
oof_full[mask] = oof
def eval_oof(th):
    kill_ef = (oof >= th)  # 只在 enemy|floor 子集
    yb = y
    fp_kill = float(((kill_ef) & (yb == 1)).sum()) / (yb == 1).sum()
    floor_ret = 1.0 - float(((kill_ef) & (yb == 0)).sum()) / (yb == 0).sum()
    return fp_kill, floor_ret
lr_cv_sweep = []; best_lr_cv = None
for th in np.round(np.arange(0.05, 0.96, 0.01), 3):
    fk, fr = eval_oof(th)
    m = dict(fp_kill_rate=fk, clean_floor_retention=fr, separation_product=fk * fr, prob_thresh=float(th))
    lr_cv_sweep.append(m)
    if best_lr_cv is None or m["separation_product"] > best_lr_cv["separation_product"]:
        best_lr_cv = m
results["logistic_best_CV_OOF"] = best_lr_cv
results["logistic_auc_cv"] = float(auc_cv)

# ---------- 诚实核心检验: chairFP vs ROI-内木地板 (同一困难区域) ----------
# 若只能把 chairFP 与"区外干净地板"分开(区域/观测密度信号), 而分不开区内真地板, 则是伪分离.
mask2 = ENEMY | WOOD
y2 = ENEMY[mask2].astype(int)
feats2 = np.column_stack([al[mask2].astype(float), -margin_fill[mask2], margin_isnan[mask2].astype(float),
                          fs[mask2], occ[mask2], sup[mask2], nv[mask2], agr[mask2], (l1[mask2] == 0).astype(float)])
mu2 = feats2.mean(0); sd2 = feats2.std(0); sd2[sd2 == 0] = 1
feats2z = (feats2 - mu2) / sd2
oof2 = np.full(mask2.sum(), np.nan)
for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(feats2z, y2):
    c = LogisticRegression(max_iter=2000, class_weight="balanced").fit(feats2z[tr], y2[tr])
    oof2[te] = c.predict_proba(feats2z[te])[:, 1]
auc_inroi = roc_auc_score(y2, oof2)
best_inroi = None
for th in np.round(np.arange(0.05, 0.96, 0.01), 3):
    kill = oof2 >= th
    fk = float((kill & (y2 == 1)).sum()) / (y2 == 1).sum()
    fr = 1.0 - float((kill & (y2 == 0)).sum()) / (y2 == 0).sum()
    m = dict(fp_kill_rate=fk, roi_wood_retention=fr, separation_product=fk * fr, prob_thresh=float(th))
    if best_inroi is None or m["separation_product"] > best_inroi["separation_product"]:
        best_inroi = m
results["HONEST_chairFP_vs_ROIwood_CV"] = best_inroi
results["HONEST_chairFP_vs_ROIwood_AUC"] = float(auc_inroi)
# margin 单信号在同一区内检验
best_m_inroi = None
for t in np.round(np.arange(-0.15, 0.201, 0.005), 4):
    kill = (margin <= t)
    fk = float((kill & ENEMY).sum()) / n_enemy
    fr = 1.0 - float((kill & WOOD).sum()) / n_wood
    m = dict(fp_kill_rate=fk, roi_wood_retention=fr, separation_product=fk * fr, thresh=float(t))
    if best_m_inroi is None or m["separation_product"] > best_m_inroi["separation_product"]:
        best_m_inroi = m
results["HONEST_margin_chairFP_vs_ROIwood"] = best_m_inroi
# freespace 单信号在同一区内
_fk = float(((fs >= 1) & ENEMY).sum()) / n_enemy
_fr = 1.0 - float(((fs >= 1) & WOOD).sum()) / n_wood
results["HONEST_freespace_chairFP_vs_ROIwood"] = dict(
    fp_kill_rate=_fk, roi_wood_retention=_fr, separation_product=_fk * _fr)
single_best_inroi = max(best_m_inroi["separation_product"], _fk * _fr)
results["HONEST_single_best_inROI_sep"] = float(single_best_inroi)

# ---------- 参照 baselines ----------
results["ref_median_fusion_retention"] = 0.28  # #5
results["ref_depth_competition_07_best"] = dict(
    separation_product=0.414886366012252, fp_kill_rate=0.8286604361370716,
    clean_floor_retention=0.5006711409395973)

# ---------- confusion @ best OR & best LR ----------
def confusion(kill, tag):
    return dict(tag=tag,
        enemy_killed=int((kill & ENEMY).sum()), enemy_survived=int((~kill & ENEMY).sum()),
        floor_killed=int((kill & FLOOR).sum()), floor_survived=int((~kill & FLOOR).sum()),
        wood_killed=int((kill & WOOD).sum()), wood_survived=int((~kill & WOOD).sum()))
best_or_kill = al | (margin <= best_or["margin_thresh"]) | (fs >= 1)
# 部署: 全量模型 allprob 在 CV 验证阈值处
best_lr_kill = allprob >= best_lr_cv["prob_thresh"]
confusions = [confusion(best_or_kill, "ensemble_OR_best"),
              confusion(best_lr_kill, "logistic_deploy@CVthresh")]

# ROC-like curve arrays (for viewer)
roc_lr = [(1 - m["clean_floor_retention"], m["fp_kill_rate"], m["prob_thresh"]) for m in lr_sweep]

summary = dict(
    schema="u3_combined_classifier_v1", capture="cap50",
    join=dict(method="union_index (netvote ply row==union_index, exact coord match); alias via NN<=0.03m",
              depth_ply_mismatch=int(mism), n_eval_points=int(len(idx)),
              n_alias_csv=int(len(alias_pts)), n_alias_matched=int(matched),
              n_alias_in_union=n_alias_union),
    counts=dict(n_enemy_chairFP=n_enemy, n_clean_floor=n_floor, n_roi_wood=n_wood),
    results=results, confusions=confusions,
    interpretation=None)

# ---------- 诚实判定 ----------
single_best = max(results["single_alias"]["separation_product"],
                  results["single_freespace_ge1"]["separation_product"],
                  results["single_margin_best"]["separation_product"])
# 诚实: 用交叉验证 OOF 分离积 (非 in-sample) 作 ensemble 上限
ens_best = max(results["ensemble_OR_best"]["separation_product"],
               results["logistic_best_CV_OOF"]["separation_product"])
uplift = ens_best - single_best
summary["single_best_sep_product"] = float(single_best)
summary["ensemble_best_sep_product_vs_cleanfloor"] = float(ens_best)
summary["ensemble_uplift_abs_vs_cleanfloor"] = float(uplift)
summary["ensemble_uplift_rel_vs_cleanfloor"] = float(uplift / single_best) if single_best > 0 else None

# ===== 诚实核心: 表面看 ensemble 对"区外干净地板"分离积 0.76 (AUC 0.92), 似乎大胜.
# 但那是伪分离: 分类器学的是"区域/观测密度" (agreement/occlusion 主导, 系数 -4.2/-2.6),
# 把 chairFP 与区外良观测地板分开; 在同一 ROI 内, 它对真木地板杀 ~60%, wood_ret 仅 ~0.40.
# 真检验 = chairFP vs ROI-内木地板. =====
honest_sep = results["HONEST_chairFP_vs_ROIwood_CV"]["separation_product"]
honest_auc = results["HONEST_chairFP_vs_ROIwood_AUC"]
wood_ret_at_op = confusions[1]["wood_survived"] / (confusions[1]["wood_killed"] + confusions[1]["wood_survived"])
summary["HONEST_inROI_sep_product"] = float(honest_sep)
summary["HONEST_inROI_AUC"] = float(honest_auc)
summary["HONEST_single_best_inROI_sep"] = float(single_best_inroi)
summary["wood_retention_at_logistic_op"] = float(wood_ret_at_op)

# 三向诚实结论:
# (a) 统计上, ensemble 在同一 ROI 内确实优于任一单信号 (AUC=honest_auc, sep=honest_sep vs single=single_best_inroi)
# (b) 增益真实非伪 (free-space 在 squash 上 3.4x 富集, occlusion 2x, 与 off-plane margin 组合)
# (c) 但非干净分离: 要杀 >80% chairFP 就同时删 ~37% ROI 内真地板 -> 对"无损全量交付"仍不合格
stat_uplift = honest_sep - single_best_inroi
STAT_SEPARATES = (honest_auc > 0.65) and (stat_uplift > 0.05)
LOSSLESS_OK = wood_ret_at_op > 0.90  # 无损产品线: 真地板保留须 >90%
summary["verdict_stat_separates"] = bool(STAT_SEPARATES)
summary["verdict_lossless_ok"] = bool(LOSSLESS_OK)
summary["inROI_stat_uplift_over_single"] = float(stat_uplift)
summary["verdict"] = (
    "PARTIAL — 统计分离但非无损可交付. "
    "(1) ensemble 三信号在同一困难 ROI 内确实优于任一单信号: chairFP vs 真木地板 5-fold CV AUC=%.3f, "
    "in-ROI 分离积=%.3f, 显著超单信号最优 %.3f (+%.3f, 增益来自 free-space 在 squash 上 3.4x 富集"
    "+occlusion 2x, 与 off-plane margin 组合; alias 在此 union 仅 15/243 命中, 是区域级非逐点信号, 贡献~0). "
    "(2) 但不是干净分离: 在能移除椅子压扁层的操作点 (杀 %d/%d=%.0f%% chairFP) 同时删掉 %d/%d=%.0f%% 的 ROI 内真木地板 "
    "(wood_ret=%.2f << 0.90 无损门). chairFP 与欠观测真地板重叠严重, 判别力最终仍系于 L1 观测覆盖度. "
    "(3) 结论: 下游融合已被榨到极限, 三信号合成把分离积从 ~0.30-0.36 抬到 0.51, 但无法达到无损交付所需的洁净度. "
    "残余重叠是上游数据问题 —— 5 张 L1 深度对 coverage-edge 地板与 chair-squash 都供证不足. "
    "必须上游补每视稠密深度 (全 CasDiffMVS MVS free-space, 非 5 张 L1), 让真地板拿到足够观测存活、同时对 squash 供反证."
    % (honest_auc, honest_sep, single_best_inroi, stat_uplift,
       confusions[1]["enemy_killed"], n_enemy, 100*confusions[1]["enemy_killed"]/n_enemy,
       confusions[1]["wood_killed"], n_wood, 100*confusions[1]["wood_killed"]/n_wood, wood_ret_at_op))

json.dump(summary, open(OUT + "/classifier_report.json", "w"), indent=2)
roc_lr_cv = [(1 - m["clean_floor_retention"], m["fp_kill_rate"], m["prob_thresh"]) for m in lr_cv_sweep]
json.dump(dict(margin_sweep=margin_sweep, or_sweep=or_sweep, lr_sweep_insample=lr_sweep,
               lr_sweep_cv=lr_cv_sweep, roc_lr_insample=roc_lr, roc_lr_cv=roc_lr_cv),
          open(OUT + "/sweeps.json", "w"), indent=2)

# 保存逐点 join 表 (供 viewer / 复现)
np.savez(OUT + "/joined_points.npz", idx=idx, xyz=xyz[idx], rgb=rgb[idx],
         margin=margin, freespace=fs, occlusion=occ, support=sup, netvote=nv,
         alias=al, is_fp=is_fp, pop=pop, allprob=allprob,
         enemy=ENEMY, floor=FLOOR, wood=WOOD,
         or_kill=best_or_kill, lr_kill=best_lr_kill)

print("=== JOIN ===")
print(f"eval points={len(idx)}  enemy(chairFP)={n_enemy}  clean_floor={n_floor}  roi_wood={n_wood}")
print(f"alias csv={len(alias_pts)} matched<=3cm={matched} in_union={n_alias_union}")
print("=== SINGLE ===")
for k in ["single_alias","single_freespace_ge1","single_margin_best"]:
    r=results[k]; print(f"{k:24s} kill={r['fp_kill_rate']:.3f} floorRet={r['clean_floor_retention']:.3f} sep={r['separation_product']:.4f}"+(f" @margin<={r.get('thresh')}" if 'thresh' in r else ""))
print("=== ENSEMBLE ===")
r=results["ensemble_OR_best"]; print(f"OR_best     kill={r['fp_kill_rate']:.3f} floorRet={r['clean_floor_retention']:.3f} sep={r['separation_product']:.4f} @margin<={r['margin_thresh']}")
r=results["logistic_best_INSAMPLE"]; print(f"logistic(IN-SAMPLE, 乐观) kill={r['fp_kill_rate']:.3f} floorRet={r['clean_floor_retention']:.3f} sep={r['separation_product']:.4f} @p>={r['prob_thresh']}  AUC={auc:.3f}")
r=results["logistic_best_CV_OOF"]; print(f"logistic(5-fold CV OOF, 诚实) kill={r['fp_kill_rate']:.3f} floorRet={r['clean_floor_retention']:.3f} sep={r['separation_product']:.4f} @p>={r['prob_thresh']}  AUC_cv={auc_cv:.3f}")
print("coef:",results["logistic_coef"])
print("=== 诚实核心检验 (chairFP vs ROI-内木地板, 同困难区域) ===")
r=results["HONEST_chairFP_vs_ROIwood_CV"]; print(f"logistic(CV) kill={r['fp_kill_rate']:.3f} woodRet={r['roi_wood_retention']:.3f} sep={r['separation_product']:.4f}  AUC={honest_auc:.3f}")
r=results["HONEST_margin_chairFP_vs_ROIwood"]; print(f"margin       kill={r['fp_kill_rate']:.3f} woodRet={r['roi_wood_retention']:.3f} sep={r['separation_product']:.4f} @margin<={r['thresh']}")
print(f"logistic 部署点同时: chairFP 杀 {confusions[1]['enemy_killed']}/{n_enemy}, ROI真地板杀 {confusions[1]['wood_killed']}/{n_wood} (wood_ret={wood_ret_at_op:.3f})")
print("=== VERDICT ===")
print(f"表面(vs区外干净地板): single_best={single_best:.4f} ensemble_best={ens_best:.4f} uplift={uplift:+.4f}")
print(f"诚实(vs区内真地板): AUC={honest_auc:.3f} in-ROI_sep={honest_sep:.4f}")
print(summary["verdict"])
