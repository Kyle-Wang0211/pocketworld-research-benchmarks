# S1 第一刀原型:2-view 点统一生命周期(RS 纪律,Q1=案 A 已按 RS 可证做法裁决)

日期:2026-07-18(exec 目录名沿用 2026-07-19 批次)。研究产物,不改生产代码。
蓝图:`../../rs_replication_blueprint_2026-07-19/`(R1/R2/R3 + BLUEPRINT §S1);裁决依据:用户 07-19 授权"执行不阻塞等签决,裁决权=RS 可证做法"。

## 统一规则(一把尺子,替代 R2#6 造 + R2#13 按出身删)

对每个可恢复出恰 2 个已验证观测的交付点:

1. **structure-only refit**:用两观测 + 精化生产位姿(位姿/K 全冻)DLT 重三角化;
2. **裁剪**:负深度 / refit 后 max reproj > 3.0px(生产 temporal-detail 门)/ 视差角 θ < 2.0°(生产 floater 门,不自创);
3. **不看出身**(provenance-blind):temporal 窗还是 spatial 远时不进判据;同一把尺子下,过几何的远时点活(#13 误杀救回方向)、不过几何的近时点死。

幸存者保留生产位置+颜色(规则只重定生死,不重定位置);观测恢复不足 2 的点全部原样保留并如实计数。

## 方法(诚实近似声明)

生产 PLY 无 provenance/track 标签;位置 NN 匹配因 ~1cm 沿射线深度歧义散射不可作身份(见 `probe_gauge.py`)。
故在**观测空间**恢复证据:把每个交付点投影到所有注册帧(精化位姿、冻结 K),3px 内的"已验证匹配 keypoint"(参与 ≥1 条 inlier two_view_geometries)= 支持观测;支持帧 ≥3 → multiview 原样保留;==2 且两 keypoint 传递匹配(union-find 同分量,RS-1 真实跨帧对应)→ 套规则;否则如实保留+计数。
偏差方向:3px 支持半径可能把真 2-view 点吸附成 multiview → **只会偏向保守(维持现状),永不多裁**。
⚠️ 本原型 = 从 sfm_live.db 重建证据,**不是生产 finalize 逐字节复刻**;墙钟为 host python 代理,非设备数。

## 同 gauge 验证(禁 Sim3)

- cap50:`probe_gauge.py` — rotation-only 0.11°,对齐不降残差 → PLY 系 == meta 位姿系;
- cap51:`probe_gauge_cap.py cap51` — rotation-only 0.08°,NN p50 0.01105→对齐后 0.01047(无改善)→ 同 gauge 确认。
- 两 cap 渲染/统计全程生产坐标系,零对齐操作。

## 四把尺子对账(baseline = 生产 sfm_sparse.ply)

| 尺子 | cap50(主) | cap51(验) |
|---|---|---|
| ①点数 | 92,849 → 92,312(−537,−0.58%) | 64,392 → 64,143(−249,−0.39%) |
| ②地板厚度 med cell p90-p10 | 0.04843 → 0.04844 m(不变) | 0.011802 → 0.011726 m(微降=更薄) |
| ②厚度 p90 cell | 0.07748 → 0.07754 m(带内不变) | 0.04336 → 0.04236 m(改善) |
| ③正确覆盖(2cm 格) | 2185 → 2182(−0.14%) | 4369 → 4363(−0.14%) |
| ④墙钟(host 代理) | 恢复 0.9s + 裁决 0.1s | 恢复 0.4s + 裁决 0.0s |
| 椅子 ROI(cap50) | near-floor 93→93,y 分位不变 → 无压扁恶化 | n/a(无冻结 ROI) |

**裁决构成**:cap50 = 535 θ<2° + 2 reproj>3px;cap51 = 247 θ<2° + 2 reproj>3px。被裁点在 floorband 图中多为离面浮点(肉眼一致)。
**救回侧**(#13 方向):通过同一规则但不在生产云中的已验证 2-view 对 — cap50:48,226 对通过、15,694 个位置距生产云 >2cm(未注入,仅呈报);cap51:28,224 / 8,538。
**质量门自评:过。**厚度不劣化(cap51 还微改善)、正确覆盖 −0.14% 量级(裁掉的本就是离面/低视差点)、椅子 ROI 无恶化、时间近零。

## 诚实边界(README 级重申)

- 80,573(cap50)/ 58,781(cap51)个点支持帧 <2 无法恢复观测,**原样保留未裁决**——真实 2-view 占比被下限估计;
- 5,389 / 2,497 个点恢复出 2 观测但不传递匹配,原样保留;
- rescue 候选未注入候选 PLY(colorize 路径与生产身份此处不可复现);
- 设备端 structure-only refit 墙钟必须真机实测后才可谈 ship(单次墙钟 ±30% 不可信)。

## 文件清单

- `build_candidate.py` — 候选生产(观测恢复+统一规则+四把尺子+render_arrays);`python3.11 build_candidate.py cap50 cap51`
- `probe_gauge.py`(cap50 硬编码,历史)/ `probe_gauge_cap.py <cap>` — 同 gauge 探针
- `render_views.py` — 同 gauge 真彩并排(俯视+立面)/ 差异着色 / rescue 覆盖 / 地板带特写 PNG
- `cap50/`, `cap51/`:`s1_caseA_<cap>.ply`(候选)、`diff_<cap>.ply`(绿=kept 2-view,红=culled,灰=其余)、`rescue_candidates_<cap>.ply`(蓝,未注入)、4×PNG、`stats.json`、`render_arrays.npz`、probe npy
- `stats_all.json` — 两 cap 汇总;`SHA256SUMS.txt` — 全部 PLY/PNG 摘要
- 网页并排肉眼对比:研究仓 stage0 的 `compare.html?right=<s1_caseA_ply>`(同 gauge 直出,禁 Sim3)

## 下一步(留编排者/用户)

1. 用户肉眼批准(compare.html 四视角)→ 才谈生产落地任务(改 finalize C++,走签决);
2. rescue 候选是否注入 = 单独裁决(需生产 colorize+身份路径);
3. 设备端 refit 墙钟实测;#13 Dart 过滤器替换与 C++ 统一门的落地拆分。
