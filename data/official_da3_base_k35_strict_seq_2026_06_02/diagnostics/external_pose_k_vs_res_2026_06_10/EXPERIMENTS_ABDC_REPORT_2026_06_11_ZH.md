# ABDC 四实验报告：K35 退化根因裁决 + production 窗口架构定案（2026-06-11）

一句话：**四个实验互相咬合成完整证据链——K=35 的 conf 塌缩与地板分层的一阶根因是
"窗长超出训练分布（≤18 views）"，不是 ARKit pose（D2 换 COLMAP pose 零变化）；
K=18@742 满血恢复且手机可跑；窗间拼接代价只是每窗 1 个标量 scale。
production 架构定案：多窗 K=10~18 @742 + ARKit pose 原样 + 窗间 overlap
中值比 scale 对齐 + 一致性过滤 + conf 加权 TSDF。**

前置上下文：本目录 `EXTERNAL_POSE_K_VS_RES_REPORT_2026_06_10_ZH.md`（2×2 矩阵）与
当日调研（DA3 论文训练视角 [2,18]@504²、官方 streaming 消融只测 ATE、官方从未验证
VIO 级 pose）。所有推理 = `official_pytorch_k_sweep_mps_chunked.py`（chunked SDPA
shim，等价性已证 rel 9.2e-4）；所有审计 = 老管线
`official_pytorch_image_only_geometry_consistency_audit.py`（跨帧重投影残差）。

---

## A：K=18@742（训练分布边界）——满血恢复 ✅

28,638 token（<43,260 手机上限），forward 23.1s（Mac MPS），umeyama 0.5761。

| | K=5@742 | **K=18@742** | K=35@742 |
|---|---|---|---|
| conf median | 9.66 | **9.50** | 4.34 |
| 同帧对照（前18帧 conf） | — | **9.50** | 5.91 |
| 残差 overall-med | 0.26% | **0.31%** | 0.45% |
| 残差最差 slot | 0.29% | **0.42%** | 3.30% |

逐帧 conf 10.8→8.6 缓降无塌缩（K35 同段帧只有 4.8-5.7，后段塌到 3.0）。
**结论：窗长回到训练分布内，一切恢复；K 5→18 的覆盖度（3.6×）几乎免费。**

## B：逐帧 scale 校正打 K35@742——吃掉最差残差 42%，但不是全部 ✅(部分)

标准原语（中值比 + log 空间最小二乘，几何全 import 自 audit 脚本，零新几何）：
`expB_per_frame_scale_correction.py`，band=3，iters=2。

发现低频结构：**scale 误差在 slot 23 处翻转**（0-22 帧 +1.1~2.7%，23-34 帧
-0.5~-6.1%，翻转点 = conf 塌缩点），|mean| 2.24%，max 6.1%。

| | 校正前 | 校正后 |
|---|---|---|
| 残差 mean | 0.77% | 0.59%（-23%） |
| 最差 slot | 3.30% | **1.93%（-42%）** |
| 后段 slot19-34 med | 1.20% | **0.82%（-32%）** |

**结论：分层一部分是单标量可修的低频 scale（原语值得入管线），但修完仍距
K18 的 0.31% 很远——剩余是 scale 修不掉的形变，根因仍是窗长 OOD。**

## D：COLMAP 定标 + 喂回——pose 无罪释放 ✅

D1（COLMAP 3.13，35 张 4224×2376，全部注册；`expD_colmap_vs_arkit_pose_audit.py`，
对齐方向注意 `align_poses_umeyama(ext_ref, ext_est)` 第一参是参考系）：

- ARKit vs COLMAP：中心误差 median **2.3mm** / mean 3.4 / max **15.1mm**；
  旋转 median **0.56°** / max 0.79°（含疑似系统性轴差成分）
- 量级换算：5mm@1.4m ≈ 0.36% 深度不一致，15mm ≈ 1.1%——与 B 校正后残留同量级，
  但 K18 覆盖段内也有 13mm 尖峰（slot 13）而残差仍 ≤0.42% → 短窗下 pose 不致命

D2（同 K=35@742，把 manifest extrinsics 换成 Sim3 对齐进 ARKit 度量系的 COLMAP pose，
ARKit intrinsics 不动，单变量隔离）：

| | ARKit pose | COLMAP pose |
|---|---|---|
| conf median | 4.34 | 4.33 |
| conf 后10帧 | 3.07 | 3.06 |
| 残差 overall-med | 0.45% | 0.39% |
| 最差 slot | 3.30% | 3.38% |
| 后段 med | 1.20% | 1.17% |

**结论：COLMAP 级 pose 在 K=35 下零恢复 → 退化不是 pose 造成的；
反向推论：ARKit pose 质量（2-15mm/0.56°）已经够用，端上不需要 COLMAP/
pose-graph/BA 任何 pose 优化工程。**

## C：双 K=5 窗（帧 0-4 vs 帧 2-6，共享帧 2/3/4）——窗间错位 = 1 个标量 ✅

两窗独立推理、独立 umeyama 归一（0.5673 vs 0.5568，窗间整体 scale 差 1.85%）：

| 共享帧 | 原始窗间差 med | 去单个 scale 后 med |
|---|---|---|
| 2 | 0.99% | **0.23%** |
| 3 | 0.90% | **0.31%** |
| 4 | 1.02% | **0.33%** |

**结论：窗间不一致几乎全是每窗一个标量的整体 scale 偏移（umeyama 在 5 个相机
中心上估 scale 的噪声）；用 overlap 深度中值比对齐（B 同款原语，每窗 1 个数）
后，窗间质量 = 窗内质量（0.23-0.33% ≈ 0.26%）。ARKit 全局 pose 下无需 Sim3/
回环/SALAD。**

---

## 总裁决

1. **根因排序**：窗长 OOD（一阶，A+D2 双向锁死）＞ 逐帧低频 scale（二阶，B 可修一半）
   ＞ ARKit pose 漂移（三阶，2-15mm，短窗下无害）＞ 高光带（局部，交给一致性过滤）。
2. **production 窗口架构**（全部部件有据可依，无自创）：
   - 窗口：**K=10~18 @ 420×742，50% overlap**（官方 overlap 约定），ARKit pose 原样
   - 窗间：overlap 深度中值比 → 每窗 1 标量 scale 对齐（C 证明充分）
   - 帧级（可选增强）：B 的逐帧 scale 校正（窗内 band 邻接，20 行）
   - 融合前：COLMAP 式跨视角一致性过滤（≤1% 相对深度差 + ≥2-3 视一致，兼任
     specular 滤波）
   - 融合：conf × max(0,n·v) × ramp 加权 TSDF（已锁定方案不变）
   - **不做**：COLMAP/BA/pose-graph 端上工程（D2 证伪收益）、finetune、非刚性校正
3. **手机可行性**：K=18@742 = 28,638 token < 43,260 predict 上限（A 用 Mac 跑，
   CoreML 真机待 spike；K=60@504=43,260 历史已过，token 更少的 K18@742 无新风险面）。
4. **复盘 6/10 报告的修正**：当时说"742 下 K 5→35 增益直接可测"——现在答案明确：
   K>18 是减益；K 的最优区间是 [10,18]。

## 产物索引（本目录）

- `expA_k18_res742/` — K18 sweep 报告 + npy(本地) + 全量 PLY（3,365,712 点，conf_thr 8.36）
- `expB_k35_res742_scale_corrected/` — 校正后深度 + scale 报告 + 全量 PLY（6,544,440 点）
- `expD_colmap_pose/` — D1 审计 JSON + COLMAP sparse TXT 存档 + COLMAP-pose manifest
- `expD2_k35_res742_colmap_pose/` — D2 sweep 报告 + npy(本地)
- `expC_k05_windowB_frames2_6/` — 窗 B sweep 报告 + npy(本地)
- `geometry_consistency/expA_*|expB_*|expD2_*` — 三份新审计
- 工具新增：`expB_per_frame_scale_correction.py`、`expD_colmap_vs_arkit_pose_audit.py`
- viewer：`/tmp/ply_compare/expB.html`（B 前后目检）、`k18_742_full.ply`；
  桌面 `外部pose_K18_742_ship候选.ply`
