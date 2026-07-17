# 08 合成分类器 (U3 收官) — chairFP vs 真地板

**任务**: 把三个已算逐点信号合成 ensemble, 测能否分开椅子压扁假阳 vs 干净地板 (每个单信号已证单独失败)。
**产候选不自批准**; 只出脚本/数字/viewer/manifest+SHA。

## Join
- key = `union_index`。已验证 `04/netvote_candidates.ply` 行序 == union_index (13488 点, 与 07 depth 的 `xyz_m` 逐点精确匹配, 误差 0)。
- free-space 信号 (support/freespace_opposition/occlusion/agreement/l1_obs/netvote) 从 netvote ply 按 union_index 直取。
- off-plane margin = 07 的 `floor_minus_best_competitor_ncc` (458 点为 None=不可评分 → nan, margin≤t 对 nan 恒 False)。
- alias (06): 243 点经最近邻 (≤3cm) 映射到 union → **仅 15/243 命中此 union**。alias 是**区域级**信号 (ROI 3.73× 富集) 非逐点信号, 在此分类器贡献 ≈ 0。
- 评估宇宙 = 3211 个 depth-scored 点 = ROI 2466 (chairFP 642 + 真木地板 1824) + 区外干净地板 subsample 745。

## 核心结果 (5-fold CV, 防过拟合; CV≈in-sample 证非过拟合)

| 检验 | 负类 | 杀 chairFP | 真地板保留 | 分离积 | AUC |
|---|---|---|---|---|---|
| single alias | — | 0.00 | 1.00 | 0.000 | — |
| single freespace≥1 | 区外干净地板 | 0.389 | 0.868 | 0.338 | — |
| single margin (best) | 区外干净地板 | 0.709 | 0.562 | 0.399 | — |
| **ensemble logistic** | **区外干净地板** | 0.963 | 0.785 | **0.756** | **0.920** |
| **ensemble logistic (诚实)** | **ROI 内真木地板** | 0.813 | 0.632 | **0.514** | **0.810** |
| single margin (诚实) | ROI 内真木地板 | 0.709 | 0.502 | 0.356 | — |
| 参照 07 depth best | ROI 内真木地板 | 0.829 | 0.355 | 0.294 | — |
| 参照 #5 median | — | — | 0.28 | — | — |

## 诚实判定: **PARTIAL — 统计分离但非无损可交付**

1. **表面 0.76 分离积 (AUC 0.92) 有区域混淆**: 负类用的是**区外**干净地板 (better-observed 的另一区域)。分类器学的是"观测密度/区域" (系数 agreement −4.2, occlusion −2.6 主导)。
2. **诚实检验 (chairFP vs 同一 ROI 内真木地板)**: 增益是**真的、非伪**: free-space opposition 在 squash 上 **3.4× 富集** (0.389 vs 0.115), occlusion 2× (0.63 vs 0.31), 与 off-plane margin 组合 → CV AUC 0.81, 分离积 0.514, **显著超单信号最优 0.356 (+0.158, +44%)**, 也超 07 baseline 0.294 与 #5 median 0.28。
3. **但不是干净分离**: 在能移除椅子压扁层的操作点 (杀 81–96% chairFP), 同时**误删 37–59% 的 ROI 内真木地板** (wood_ret 0.40–0.63 << 0.90 无损门)。chairFP 与欠观测真地板重叠严重, 判别力最终仍系于 L1 观测覆盖度。

**→ 下游融合已榨到极限** (三信号合成把 in-ROI 分离积从 ~0.30-0.36 抬到 0.51), **但达不到无损全量交付所需的洁净度**。残余重叠是**上游数据问题**: 5 张 L1 深度对 coverage-edge 真地板与 chair-squash 都供证不足。**必须上游补每视稠密深度 (全 CasDiffMVS MVS free-space, 非 5 张 L1)**, 让真地板拿到足够观测存活、同时对 squash 供反证。

## 产物
- `combine_classifier.py` / `render_viewer.py` — 脚本 (python3.11, numpy+sklearn)
- `classifier_report.json` — 全指标 + confusion + coef + verdict
- `sweeps.json` — margin/OR/logistic (in-sample & CV) 全阈值扫 + ROC-like 曲线
- `joined_points.npz` — 逐点 join 表 (idx/xyz/rgb/6 free-space attr/margin/alias/标签/概率/kill mask)
- `viewer_roi_kill_vs_keep_truecolor.png` — 真彩 top-down: ROI 全部 / ensemble 杀 / ensemble 留 (面板标题 CJK 因缺字体显示为方块, 计数见 report.json confusions)
- `roc_like_honest_vs_confound.png` — ROC: 区外干净地板(伪) vs ROI内真地板(诚实)
- `SHA256SUMS.txt`

**过夜铁律遵守**: 仅在研究 worktree 08 子目录写; 未碰生产/未 reset/clean/未动他人 dirty/未 git commit。
