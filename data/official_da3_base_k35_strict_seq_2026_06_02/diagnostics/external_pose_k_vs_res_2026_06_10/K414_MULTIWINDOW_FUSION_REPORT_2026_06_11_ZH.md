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
