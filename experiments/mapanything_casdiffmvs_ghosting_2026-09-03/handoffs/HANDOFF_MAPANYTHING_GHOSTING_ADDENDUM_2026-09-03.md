---
artifact_contract: "ce-handoff/v1"
created_at: "2026-09-03T06:40:00Z"
title: "PocketWorld MapAnything 重影根因逐层归因补遗"
summary: "补充 HANDOFF_MAPANYTHING_GHOSTING_2026-09-03.md：官方/权威融合链查证结果、逐层替换归因数字、校准跟随探针、问题 C 的真正变量（朝向）。"
supersedes_sections: ["十、未解决的真正问题", "十一、推荐的后续推进方向 Phase 1-3"]
parent: "HANDOFF_MAPANYTHING_GHOSTING_2026-09-03.md sha256 15f15ec1a9059b0f4d4cc405f541a81ad30afea0a66677ad11c0c7acfe1d15a1"
---

# 本补遗只回答三个问题

主交接第十节提出的问题 A / B / C 在 2026-09-03 当天全部有了可核实的答案。
本文件不替代主交接，只覆盖其 Phase 1–3 的结论。事实优先级与主交接相同：
冻结产物与日志 > 本文归纳 > 推测。所有数字都可在下列 JSON 中逐字核对。

# 问题 A：官方是否存在「预测 → 唯一融合表面」链

**无记载。** 三个只读调研（全部打到源头 URL / 文件行号）一致：

- 冻结 commit 全树无 TSDF / 深度一致性融合 / StereoFusion / 网格合并代码。
  唯一"合并"是 `mapanything/utils/colmap_export.py` L466–473 的 concat +
  Open3D 体素降采样（默认体素 = 2×IQR×1%），降采样不是融合。
- 维护者 Nik-V9 在 issue #76（2025-11-16）口头推荐 "TSDFusion … very
  effective"，无脚本、无参数。issue #147 承认跨视图重投影一致性差是
  "lack of correspondence objective in our training"。issue #16 对 OOD 场景
  建议减少视图，或改走 COLMAP 位姿 + MVS。issue #10/#150：输入 K/pose 不保证
  透传，"model follows the inputs closely"。
- 论文 arXiv 2509.13414 Fig. S.5 说明文字自认 "100 input images show
  duplication of 3D structure"；评测口径是 view-0 坐标系下逐视图逐像素误差，
  不评表面（`benchmarking/dense_n_view/benchmark.py` L445–467）。
- HF `facebook/map-anything-apache` 当前 main = `00f9c245…`（2026-02-04），
  与我们冻结的 revision 相同；最后一次权重推送 2026-01-20（V1.1）。
  **没有更新的官方权重可试。**
- 下游：不存在可商用、权威、且保持 2000 万点量级的 MapAnything→唯一表面链。
  最接近的是 Open3D `ScalableTSDFVolume`（MIT）与 Depth Anything 3 评测用
  TSDF 代码（Apache；输入契约 depth+K+pose 与 MapAnything 输出吻合），
  点数由体素决定而非保留原点。AliceVision 网格默认封顶 500 万顶点；
  OpenMVS 为 AGPL；VGGT-Long 为 Meta VGGT 许可；GLUEMAP（COLMAP 组织，BSD）
  消费 MapAnything 但只出稀疏。

# 问题 B：哪一层第一次破坏几何一致性

## 方法

1. 用官方 demo 的 `model.infer` 原参数复放 `/root/imgs132_up`（132 帧，
   1500×2000 竖图，模型分辨率 392×518），把**每一个**逐视图输出张量原样落盘：
   `/root/mapanything_layer_audit_A_imgs132_up_20260903/`（1.5 GB，
   `SHA256SUMS.npy.txt`）。推理 17.97 s，峰值显存 17.31 GB，官方导出口径顶点
   25,150,854（冻结 exact GLB 25,123,136，差 0.11%，bf16 复放噪声）。
2. 参考相机 = 生产 COLMAP 稀疏模型（三个 .bin 哈希与主交接一致，132 个
   PINHOLE，4032×3024，fx 中位 2861.97 px）。用官方 `rotate_pinhole_90degcw`
   与前一位 agent 自测过的 `rotate_world_to_camera` 转正，再经官方
   `preprocess_inputs` 缩到 392×518。主点核对：预测 cx/cy = 195.7/258.5，
   参考 195.5/259.5，说明参考 K 的朝向与裁剪没有错。
3. 固定预测深度，替换 K / 位姿，用官方 `compute_multiview_depth_confidence`
   （默认 2%/2%）度量跨视图一致性。

脚本与结果本地副本：`_host_experiments.nosync/mapanything_layer_audit_20260903/`
（`layer_attribution.json` sha256 `36f6efea…b237`；`report.json`
sha256 `caf2c888…5367`）。OpenSpec：`openspec/changes/audit-mapanything-layer-attribution/`。

## 数字（132 帧）

| 层 | 指标 | 值 |
|---|---|---|
| K | 预测 fx / 参考 fx（逐帧） | p50 **0.768**（p05 0.755，p95 0.783） |
| K | 射线角误差逐帧中位 | p50 **6.42°** |
| pose | Sim(3) 尺度 model/COLMAP | 0.2533 |
| pose | 相机中心残差 / 轨迹对角线 | p50 1.9%，p95 3.3% |
| pose | 旋转误差（全局对齐后） | p50 **3.59°**，p95 5.48° |
| depth | 逐帧深度尺度 / Sim(3) 尺度（对 COLMAP 稀疏点） | p50 0.946，p95/p05 = **1.079**，极值 0.832–1.051 |
| depth | 残差随像面半径 | 中心 1.022 → 边缘 0.980 |

官方多视图一致性，逐帧「置信度 < 0.5 像素占比」p50（p95）：

| 变体 | 深度 | K | 位姿 | 不一致占比 |
|---|---|---|---|---|
| V1 官方原样 | 预测 | 预测 | 预测 | **0.291**（0.657） |
| V2 | 预测 | COLMAP | 预测 | 0.886（0.991） |
| V3 | 预测 | 预测 | COLMAP | 0.812（0.949） |
| V4 | 预测 | COLMAP | COLMAP | 0.629（0.905） |
| V5 | 逐帧重缩放 | COLMAP | COLMAP | 0.601（0.839） |

换成真 K、真位姿、或再校正逐帧尺度，一致性**全部变差**：预测深度只在模型
自己那套失真相机模型里自洽。

## 校准跟随探针（8 帧）

| 运行 | fx 比值 | 射线误差 | 备注 |
|---|---|---|---|
| R1 纯图像竖图 | 0.772 | 6.31° | 不一致占比 0.138 |
| R2 喂 K | 0.787 | 5.80° | 只被轻微拉动 |
| R3 喂 K+pose（非米制） | 0.787 | 5.76° | 位姿被跟随：相对旋转 0.29° |
| R4 单视图竖图 | 0.774 | 6.23° | 单帧就错 |
| R5 单视图侧躺 | **0.599** | 13.2° | 侧躺翻倍 |
| R6 8 帧侧躺 | 0.589 | 13.6° | 不一致占比 0.309 |

## 判决

第一次破坏几何的层是**模型自身预测的射线方向 / 内参**：焦距系统性短 23%，
单视图即出现，视图数不改变，喂正确 K 不被跟随（位姿则被跟随）。深度与位姿
是围绕这套错误相机模型共适应的，剩下的跨视图不一致（V1 的 29%）就是用户
肉眼看到的重影/多层。这不是输入顺序、分辨率、COLMAP 条件、导出器或网页
造成的。

未证明的事项（保持诚实）：为什么这个场景/这类 iPhone 竖图会让模型的
校准先验偏宽，没有出处；官方论文与 issue 均无记载。

## 朝向复核（用户质疑后补做）

- 肉眼看过 `imgs132_up/frame_000000` 与 `frame_000060` 缩略图：背包、行李箱、
  地板在下，`imgs132_up` 的转正是正确的，180° 歧义排除。
- `/root/rotation_fov_probe.py`（结果
  `_host_experiments.nosync/mapanything_layer_audit_20260903/root/mapanything_rotation_fov_probe_20260903.json`）：
  5 帧 × 4 个旋转角单视图预测长边视场。真值 70.3°。转正（0°）5 帧全部
  84.1–85.2°（比值 1.20，极稳定）；90°/180°/270° 在 63–101° 之间乱跳。
  结论：23% 焦距误差是模型对本场景稳定的场景级误判，不是输入朝向问题。
- 顺带观察（推测，未验证）：转正时预测的**短边**视场 68.7–69.8° 与真实
  **长边**视场 70.3° 几乎相同，像是把"手机横向 ~70°"的先验套在了图像宽度上；
  仅记录，不作为结论。

# 问题 C：为什么 2000×1500 exact 比 4032×3024 capture-order 版更稳

不用重跑：`imgs132_up/frame_000000.jpg` 与源图 `00000016.jpg` 相关系数 1.0，
与生产 COLMAP 输入的符号链接映射一致，说明 exact 基线**本来就是采集顺序**
（A = B）。失败的 D 版喂的是无 EXIF、存成横向的 4032×3024 原图，实际是
**侧躺的**；exact 基线是转正后的竖图。R5/R6 显示侧躺让焦距误差从 23% 变成
41%。D 的严重放射漂移变量是朝向，不是顺序。

## 校准跟随合成实验（用户改口"任何方法都行"之后补做）

`/root/k_follow_synthetic.py`（结果本地
`_host_experiments.nosync/mapanything_layer_audit_20260903/root/mapanything_k_follow_synthetic_20260903.json`），
4 帧转正图，喂进去的焦距 = 真值 × {0.5, 0.77, 1.0, 1.3, 1.6}，输出焦距/真值
分别为 0.64 / 0.77 / 0.79 / 0.79 / 0.80；直接喂射线、加位姿、`is_metric_scale`
True/False 都是 0.79。`inference.py` L217–276 已核对：intrinsics → ray_directions_cam
的转换正常发生。结论：**射线头对本场景基本不响应输入标定**，"校准+位姿 ⇒ 对齐"
在本数据上是死路，且不是管线丢输入。

# 用户改口后的第一个候选：模型自身坐标系内的 TSDF 融合

用户 2026-09-03 表示"不在乎方法，只要肉眼无重影、正常"。依据：维护者 #76
推荐 TSDF；逐层归因证明预测 depth 只在预测 K/位姿下自洽，所以融合必须在
模型自身坐标系做，不能引入 COLMAP 相机。实现 Open3D（MIT），参数照 DA3
Apache 评测代码。OpenSpec：`openspec/changes/fuse-mapanything-tsdf-ownframe/`。

| 档 | 后端 | 体素 | 截断 | 点数 | 用途 |
|---|---|---|---|---|---|
| 参照 | ScalableTSDFVolume CPU | 7.8 mm | 40 mm | 2,968,480 | 定性看 TSDF 能否去重影 |
| 密度 | VoxelBlockGrid CUDA | 3 mm | 40 mm | 19,569,198 | 主候选，落在 2000–3000 万带内 |
| 更密 | VoxelBlockGrid CUDA | 2 mm | 40 mm | 43,199,189 | 只留远端（2.2 GB），超带 |

远端 `/root/mapanything_tsdf_fusion_20260903/`；本地网页
`verdict_page/mapanything_tsdf_fusion_ownframe_20260903/`（7.8 mm）与
`verdict_page/mapanything_tsdf_gpu_3mm_ownframe_20260903/`（3 mm）。
输入 = 逐层审计落盘的官方张量（同一批），官方 mask 原样，无置信度筛点、
无降采样；TSDF 是唯一新增步骤。深度按 0.2 mm 量化为 uint16（CUDA 核要求）。
坑：`ulimit -v` 会让 CUDA 初始化报 out of memory；legacy CPU 体素在 3 mm
下 23 GB 爆内存。

**用户判决：待定。** 没有用户肉眼通过之前只能叫候选。

# 用户后续指令与两个新候选（09-03 晚）

用户先后说明：(1) TSDF 不是他要的——他要"完美的稠密点云"，逐像素原生点、零重影；
(2) DA3 稠密阶段也有重影，且 DA3-LARGE-1.1 无商用许可（README 表为 CC BY-NC，
HF 标签写 apache-2.0，两处矛盾，按不可商用处理），**不要再碰其它算法，专心
MapAnything**；(3) 可以试 **CasDiffMVS 原本的官方算法**（不加后来的训练数据），
他之前不用它只因墙面有轻微重影；(4) 问"尺度对齐 + 共识深度"是不是前一位 agent
做过——**没做过**（远端目录与账本逐条核对：全是过滤/桥接/体素/条件输入/只读审计）。

我顺手起过一个 3DGS（gsplat）训练来验证"单一场景表示"路线，用户明确要求专注
MapAnything 后**已立刻停掉**，未产生任何候选。

## 候选 1：MapAnything 自身共识深度（不删点）

OpenSpec `refine-mapanything-consensus-depth`。逐帧尺度 p05–p95 1.013–1.051；
99.8% 像素有一致伙伴（中位 49 个）；官方不一致占比 **0.291 → 0.193**；点数不变
25,150,854；68.7 s。页面 `verdict_page/mapanything_consensus_depth_20260903/`。
预期（跑前写下）：2% 容差内的薄双层会压回一层，更大的错位留着。**判决待定。**

## 候选 2：CasDiffMVS 官方原版

OpenSpec `reproduce-casdiffmvs-official-blendmvg-nv10`。上游 cd10d5c 干净克隆
（研究仓 vendored 的 models/filter.py 带本地提速补丁，未用），官方 blendmvg 权重，
生产 COLMAP 相机 + 官方 10 视图 pair，768×576，官方 filter.py 融合。3 分钟，
**36,845,039 点**。页面 `verdict_page/casdiffmvs_official_blendmvg_20260903/`。
dtu 官方权重已放远端未跑。**判决待定。** 许可：官方权重含 DTU 血统，只做质量
测试，不能出货（与 08-16 结论一致）。

## 本次新增远端目录

`/root/mapanything_consensus_20260903`、`/root/casdiffmvs_official_20260903`
（含 `diffmvs_upstream`、两个官方 ckpt、`mvs_P16k` 输入、`out_blendmvg_768x576_nv10`）、
`/root/da3_setup_20260903`（仅安装，未推理）、`/root/gsplat_setup_20260903` 与
`/root/gsplat_train_production132_20260903`（已停，无产物）。

# 用户判决（09-03 晚）与结合方案

- **CasDiffMVS 官方原版：用户肉眼"没有任何重影"**，唯一缺陷 = 白墙粘到行李箱和书包
  上（无纹理墙深度被拉向前景）。这是他一直说的老问题（鬼墙战役的"第二面墙跟旅行箱
  粘连"）。共识深度版用户未评。
- 用户指令："看看如何把 CasDiffMVS 和 MapAnything 结合起来"。
- 结合原则（依据鬼墙战役 E2–E13"根治只在出生前"）：几何一致性归 CasDiffMVS，
  无纹理区形状先验归 MapAnything，在深度估计时注入，不做事后过滤。
- 第一个结合候选 `combine-casdiffmvs-mapanything-prior-init`：MapAnything 每帧深度
  经逐视图仿射对齐到 COLMAP 尺度（a≈3.75，与 MVS 有纹理处残差中位 1.1%，覆盖 93%），
  替换 CasDiffMVS 粗阶段输出作为扩散精化起点；其余全同官方。存活率中位 0.649
  （官方 0.671）。页面 `verdict_page/casdiffmvs_blendmvg_mapanything_prior_20260903/`。
  **判决待定。** 下一变体：只在粗阶段置信度低（无纹理）处注入；或 stage 2 也注入。
- 输入映射铁律：`mvs_P16k/{s}.jpg` 是**源序号**，MapAnything 帧 = `capture_order_source_to_frame[s]`
  （相关 1.0 验过）；upright→landscape = `np.rot90(U, +1)`。

# 已排除、不要再做的

1. 再换输入顺序、分辨率、去畸变、K-only / pose-only 条件：预测 K 都是 0.76–0.79。
2. 等官方新权重：Hub 上没有比 `00f9c245` 更新的 revision。
3. 手调 K / Sim(3) / 阈值：主交接已禁；且 V2–V5 证明外部真值反而更差。
4. 侧躺原图直接喂模型（D 版路线）。

# 需要用户拍板的事（不是建议自动执行）

官方 MapAnything 的可用杠杆已经穷尽；重影的来源在模型内部。余下的路都在
"纯官方 MapAnything 复刻"之外，按主交接第十一节 Phase 4 末段，必须由用户决定：

- 接受权威外部 consumer 做表面融合：Open3D TSDF（MIT）或 DA3 的 Apache TSDF
  评测代码；代价是「点」变成「体素/网格采样」，2000–3000 万的语义要重新定义。
- 官方模型输入侧的另一种条件（issue #18/#98 维护者建议）：喂 COLMAP 稀疏深度
  或单目深度作 `depth_z` 输入并 `ignore_depth_scale_inputs=True`。这是官方
  支持的输入模态，但用户已否决 COLMAP 条件路线，不应擅自重开。
- 换模型族或回到 COLMAP 位姿 + MVS（维护者 #16 的建议）。

# 现场

- 远端 5090 空闲，无残留进程；新增目录只有
  `/root/mapanything_layer_audit_A_imgs132_up_20260903`、
  `/root/mapanything_calib_follow_probe_20260903` 与三个脚本；未删除任何
  历史产物；未产生任何候选 GLB / 网页；未触碰生产手机；本地 8931 仍未启动。
- 本机磁盘剩 18 GB，只拉回了脚本 / JSON / 日志（约 200 KB），未拉回张量。
