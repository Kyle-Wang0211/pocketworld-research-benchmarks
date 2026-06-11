# 414 帧全程多窗管线 + fusion 部件落地报告（2026-06-11 夜跑）

一句话：**ship 配置（K=18 @ 504×896，stride 9，ARKit pose）在 414 帧全捕获上
45 窗串跑全成（28.9 分钟，~40s/窗），fusion 两部件落地并量化：链式 scale 对齐
（部件 A）修正中位 3.0%/最大 12.9%/累计漂移 ×1.55——是承重墙不是优化；
一致性过滤（部件 B）几何保留 53.7%，conf 过滤后再砍 40%（1.12 亿 → 6,680 万
有效点），双版本 3M 点 PLY 已出供目检 A/B。**

## 1 R1：45 窗串跑（expG_multiwindow_k18_runner.py）

- 输入：`k414_full_pose_manifest.json`（从 capture 的 da3_input_manifest.json 换算，
  extrinsics 原样、intrinsics 换回源图尺度，与 strict manifest 交叉验证位级一致；
  全 414 帧照片零缺失）
- 配置：K=18 @ process_res 896（官方 preprocess），stride 9（50% overlap），
  saddle_balanced，每窗独立 umeyama pose_scale，模型单次加载，chunked SDPA
- 结果：45/45 success，总 28.9 分钟（~40s/窗），产物 3.7GB（npy 本地）
- **全捕获的真实纹理**：窗级 conf median 跨度 1.57~10.24，中位仅 3.31，30/45 个窗 <4。
  机制（窗 001 诊断钉死）：conf 是窗级后验——同一帧在纯易区窗里 conf ~9.7，
  混入难区帧（背光帘 + 0.26-0.33m 大跳步）的窗里掉到 ~3.4。窗的成分决定窗的 conf；
  414 全序列把策展期掉过的难帧全包含进来了。
- 附带验证：全序列前 35 帧 == strict 策展 35（路径逐一相同）；窗 001 复现了
  此前 ladder_k18_res896_win1 参考的 conf 3.1——runner 与单窗管线完全同源。

## 2 部件 A：链式逐窗 scale 对齐（expH_window_chain_fusion.chain_scales）

相邻窗 9 个共享帧的双侧高 conf 中值比 → 每窗 1 标量，窗 0 锚定链式传播：

- **边修正幅度：中位 3.02%，最大 12.89%**（014→015），累计 scale 跨 [0.98, 1.55]
- 对比双窗实验 C 的 1.85%：45 窗未策展全序列的逐窗 umeyama 噪声远大于策展双窗
  ——**没有部件 A，融合点云直接散架（最远窗间 55% 尺度差）**，从"优化项"升级为
  "必需项"的结论由此 grounded
- 对齐后相邻窗残差中位 1.61%（策展易区 0.23-0.77%、难区 2.17% 的混合，符合预期）

## 3 部件 B：跨帧一致性过滤（expH_window_chain_fusion.consistency_filter）

COLMAP fusion 语义（≤1% 相对深度差 + ≥2 邻帧一致，邻域 ±4 帧，最近邻采样），
全像素向量化，414 帧 × 8 邻 ≈ 3.3 分钟：

- **几何保留率 53.7%**（46.3% 的像素连 2 个邻帧都说服不了——含高光带、
  大跳步孤帧、背光玻璃）
- 与官方 conf 过滤（全局 P40 规则，本次阈值 2.706）叠加：
  control 有效 112,173,469 → filtered **66,808,378**（再砍 40%）
- 双版本均按官方 GLB 规则降采样 3,000,000 点导出

## 4 产物与目检

- `expH_fusion/fused_filtered_rgb.ply` / `fused_control_rgb.ply`（各 43MB，已入库 LFS）
- 桌面：`全程414帧_K18x896_融合_过滤版.ply` / `_对照版.ply`
- viewer：`/tmp/ply_compare/k414.html`（双栏联动 A/B）
- 工具入库：`expG_multiwindow_k18_runner.py`（断点可续多窗 R1）、
  `expH_window_chain_fusion.py`（部件 A+B+官方导出）、`k414_full_pose_manifest.json`
- 中间产物：`expG_k414_multiwindow/window_{000..044}/`（3.7GB npy 本地，
  可由入库代码 + manifest 确定性重建）

## 5 给早晨的待讨论项

1. **目检 A/B**：过滤版 vs 对照版的地板/高光区/重影差异（k414.html）
2. 窗级 conf 中位 3.31 的含义：全捕获难区占比高 → 是否需要 capture 端
   策展（质量门控）回流到窗口规划（da3_k_windows.json 的 cell 策展逻辑本来就在）
3. 链最大边 12.9%（014→015）等大修正边的根因（值得看那两窗的内容）
4. 部件 A 的链式 vs 全局 log-LSQ（45 窗链随机游走 ~0.7% 漂移，目前可接受；
   全局解是 20 行升级）
5. TSDF（已锁定 conf × n·v × ramp 方案）吃这套输入的 W4 落地

---

## 附录（v2，用户目检"散架"后的根因核查与重导出）

### A1 官方流程完整性核查（用户问题 1）

三处实现逐行同构，**官方单窗流程抄全无遗漏**：
- 官方 `api.py:341-365 _align_to_input_extrinsics_intrinsics`
- 6/5 原版 `official_pytorch_window_export.py:100-109`
- 本管线 `expG_multiwindow_k18_runner.py`（窗 000 复现 ladder 参考 conf 10.10）

官方流程终点 = 逐窗 umeyama metric 深度；pose-conditioned 模式**官方不存在任何
跨窗融合方案**（调研已证：仅 image-only streaming 有 Sim3 + 回环）。

### A2 散架根因链（全部 grounded）

1. **官方 umeyama 这步在难窗是弱环**：它靠模型预测 pose 反推尺度；难窗预测 pose
   烂 → 逐窗 metric 尺度噪声达 ±13%（链边实测 3-13%）。
2. **解析尺度捷径不存在（假设已测试并证伪）**：umeyama 与 1/输入归一化尺度系统性
   差 5-10 倍 → 模型输出尺度是自己的 point-map 规约（论文 §3.3 损失归一化），
   不回声输入 pose 尺度。**umeyama 不可省，官方语义正确**，只是噪声随窗质量恶化。
3. 链式对齐锚定窗 0，44 条边累计漂移 ×1.55。
4. 全局 P40 conf 阈值被难窗拉低到 2.71（易窗子集自己的 P40 = 7.06，差 2.6 倍）
   → 大量垃圾点过门。
5. 3M 采样上限（112M 取 2.7%）把残余结构雾化（用户问题 2；上限来自官方 GLB
   默认 1M 的放大，对 414 帧不适用，已移除）。

### A3 v2 导出（配置级修复，无新增算法）

- `expH_fusion_v2/`：fused control/filtered × {8M, 全量}（全量 filtered =
  66,808,378 点 / 956MB，control = 112,173,469 点 / 1.6GB；PLY 本地保留未入 LFS）
- `expI_easy_ref/`：**易窗参考版**（conf≥6 的 7 窗 = 000/006/017/018/019/037/038，
  126 帧，纯官方语义无链无滤，自身 P40 阈值 7.06，34.1M 有效 → 8M 导出）——
  融合路线在好窗上的质量天花板，与全窗版的差距 = 难窗代价
- viewer 三栏：`/tmp/ply_compare/k414.html`（对照 8M / 过滤 8M / 易窗参考 8M）；
  桌面：`全程414帧_融合过滤_全量66.8M.ply`、`易窗参考版_8M.ply`

### A4 早晨待决（升级部件 A 的三个候选，按侵入度排序）

1. conf 加权全局 log-LSQ + 高 conf 窗锚定（替换链式，~25 行）
2. 窗级质量门控 / capture 端 cell 策展回流窗口规划
3. conf 阈值分位升档（全局 P40 → 更高或分层阈值）

---

## 附录 B（v3→v7：部件 A 对抗式迭代记录，2026-06-11 下午）

调研定位（两轮 web 调研 + vendor 源码）：官方 pose-conditioned 无跨窗方案
（#159 官方答 da3_streaming 但它不吃外部 pose；#193/#132 零回应）；官方
scale+se3 的 scale 预估计（compute_chunk_scale_advanced）是 VGGT-Long 作者
为 DA3 专做；umeyama 在 #138 被官方确认"预测系为参考"=不可省；RANSAC 版
umeyama 我们一直在用（api 同款 ransac_view_thresh=10），±13% 是其残余。

三路并行（各带对照）+ 两次失败迭代：

| 版本 | 内容 | 残差 med/max | 锚窗\|a-1\| | keep | 裁决 |
|---|---|---|---|---|---|
| v3 | scale-only 锚定 log-LSQ | 1.98% / 8.99% | 0.1% | 44.9% | 基线 |
| v4 | 边估计换官方 auto 估计器 | 2.52% / 11.62% | — | 44.8% | **出局**（RANSAC 线性回归在系统性形变上 inlier 99% 仍选错） |
| KR | 难窗注锚帧（VDA 式） | 锚帧 9.45→2.1，原帧 1.44→1.00 | — | — | **出局**（污染反向流动；难区连续无好邻窗） |
| expL | LASER 层诊断 | 坏边层散布 10-16pp，单调于深度 | — | — | **半证实**：affine 形态（a+b/d），层图不必 |
| v5 | 联合 affine（坏 gauge） | 1.53% / 3.64% | **18.1%** | 34.7% | 残差好但绝对尺度坏：边项 O(d²·2万) 碾压锚权 400 |
| v6 | scale→shift 两步 | 1.97% / 8.81% | 0.1% | 44.8% | **数学无牙**：scale 吸掉中位后 shift 无可拟合 |
| **v7** | **联合 affine + 均值归一 gauge** | **1.61% / 4.12%** | **0.0%** | **45.3%（84.8M）** | **终态** |

部件 A 终态 = 锚定联合 affine（per-window a·d+b，法方程边块均值归一，
conf≥6 窗 identity 锚），`expJ_fusion_v3.py --correction affine`（修复后）。
最差边残差对半（8.99→4.12%），keep 全场最高。

KR 的方向性教训入档：cross-view attention 的污染是坏帧拖垮好帧（锚帧
9.45→2.1），不是好帧拉起坏帧——窗口规划应做"难帧隔离"（同质窗）而非
"好帧稀释"。
