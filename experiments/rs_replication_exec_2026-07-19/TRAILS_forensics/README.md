# E2-A 拖尾法医(specular/mirror trails)— cap50 主 + cap51 验

日期 2026-07-18(exec 目录沿用 07-19 批次)。研究产物,不改生产、不动 capture 数据、不 commit(编排者统一提交)。
靶标:用户 07-19 扩大鬼层定义——镜面/反光物体的长拖尾点云,RS 预览完全没有("预览零鬼层"验收项)。
本目录只做**取证与指纹**,不做裁剪、不出候选交付云(质量无损硬门:动交付点必须另立签决)。

## 方法(三条签名并用,全部构造性、无手挑区域)

证据恢复复用 S1 已验证方法(sfm_live.db two_view_geometries 重建 verified 对应 + meta 精化位姿投影,3px 支持门;同 gauge,禁 Sim3)。每点指纹:n_support / 残差 / tri-angle / 视线 ray / 局部 PCA 细长比+射线对齐 / 地板面高度(ghost_mask.json 全局平面,**不用逐点 bits**,因 93,360(裁前) vs 92,849(交付) 顺序不可对齐)/ 视线走廊遮挡。

检测器 = 四签名并集(`detect_trails.py` 常量区):
- **S_behind**:主相机→点视线穿过 ≥3 个实体体素(5cm 体素 ≥6 点)——真表面点被直视,镜面虚点藏在真表面之后;
- **S_below**:低于生产地板面 10cm+(已知双地板带 2-3.5cm 之下=物理不可能);
- **S_streak**:稀疏 wisp(10cm 邻域 ≤10 点)连成串(15cm 链接,≥4 点),串 PCA 细长比 ≥3 且主轴与平均视线 |cos|≥0.8 =任务签名①"沿视线拉长";
- **S_out**:任务签名②的数据驱动实现——脱离稠密场景壳(10cm 邻域 ≥40 点为核,距核 >25cm 且自身 ≤10 点)。

候选 20cm 连通域聚簇,逐簇报指纹;`audit_crops.py` 把簇/随机单点投影回原照片裁块供肉眼误报抽查。

## 结果

| | cap50 | cap51 |
|---|---|---|
| 候选点 | **1,004 / 92,849(1.08%)** | 525 / 64,392(0.82%) |
| S_behind / S_below / S_streak / S_out | 325 / 161 / 86(9串) / 532 | 169 / 25 / 20(3串) / 322 |
| 簇(≥3 点)/ 孤点 | 126 簇 / 102 孤点 | 92 簇 / 59 孤点 |

指纹对比(trail vs clean,cap50):局部密度中位 **7 vs 398**(57×);tri-angle 中位 **5.7° vs 17.6°**(低视差尾部坐实);cam_depth 中位 1.42 vs 0.84m。n_support=0 比例两组几乎同(0.645 vs 0.654)→ "无可恢复观测"**不是**判别指纹(全云 65% 恢复不出,S1 已知边界)。

拖尾集中区(cap50,俯视热区见 `trails_topview_elev_cap50.png`):
1. **墙外长尾 Z −4.3→−9.7**(玻璃门/窗方向,185 点):窗格玻璃里的房间倒影被三角化到玻璃后(cluster06 裁块实锤);**但 Z≈−9.1 的 cluster12 裁块显示是真门洞外邻室货架=真几何**,与此前 mirror-cull "真门洞非有界镜"裁决一致——墙外点是"镜像虚点+门洞真景"的混合体,不能一刀切;
2. **地板下反射层 fh<−0.10**(161 点,cluster01/04 实锤):高光木地板把床脚/柜脚反射三角化到地板下 10-15cm——这在双地板带(2-3.5cm)之下,是独立于 47 号双层地板的另一病理;
3. **黑色钢琴漆/镜面家具后**(cluster02):百叶窗倒影打进柜面之后;
4. **缎面被子云**(cluster00 n=205,AMB):高光+可形变织物,镜面拖尾与真实褶皱混杂。

## 误报抽查(诚实,单评审员=本 agent,非用户签认)

`audit_verdicts.json` 全表。点级(随机 20/cap):cap50 明确 FP **3/20=15%**(含模糊上界 40%);cap51 明确 FP **7/20=35%**(上界 60%,FP 主因=白墙/天花弱纹理浮点——是预览可见的尘埃但**不是**镜面拖尾)。簇级(cap50 已审 10 簇):3 FP=天花 wisp、真实背包/墙(S_behind 主相机错配)、门洞外真几何。
**结论:检测器适合当"取证探照灯",不适合直接当裁剪刀**;若走裁剪必须 RS-faithful 机制(2.0px 重投影裁剪线索在 E2 主线)而非本启发式。

## 文件清单(SHA256SUMS.txt 为准)

- `compute_fingerprints.py` / `detect_trails.py` / `audit_crops.py` — 三段管线(python3.11,复跑同序)
- `cap50/`, `cap51/`:`fingerprints.npz`+info、`trail_detect.npz`、`trail_mask.npy`、`trail_stats.json`(含逐簇指纹表)、`trail_highlight_<cap>.ply`(拖尾红/其余生产真彩)、`trails_only_<cap>.ply`(仅拖尾真彩)、`trails_topview_elev_<cap>.png`、`fingerprint_dists_<cap>.png`、`recon_overview.png`、`audit_crops/*.jpg`(34/cap)、`audit_rand_sheet.png`、`audit_manifest.json`
- `audit_verdicts.json` — 肉眼审计判定
- 肉眼并排:研究仓 stage0 `compare.html?right=<trail_highlight ply>`(同 gauge 直出,禁 Sim3)

## 诚实边界

- 证据恢复非生产 finalize 逐字节复刻;65% 点观测恢复不出(S1 已知下限),其 ray 用最近相机代理(`ray_proxy` 标记);
- S_behind 依赖主相机选择,对无观测点方向可能错 → cluster09 型误报;
- 阈值(体素 5cm/≥6、核 40、脱壳 25cm 等)是本实验固定的取证参数,非认证配置,不得直接进生产;
- cap51 的候选多为弱纹理浮点而非镜面拖尾(该场景镜面少),两 cap 病理构成不同;
- RS mobile 内部实现 = UNRESOLVED 红线,本目录不声称 RS 如何做,只声称我们的云里有什么。
