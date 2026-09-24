# 外部 ARKit pose 下 K × 分辨率 2×2 因子矩阵（2026-06-10）

一句话：**用 oracle 同款 chunked SDPA 在 18GB Mac 上首次跑出 K=35@742（历史死于
89GiB MPS 单 buffer，分块后进程峰值仅 1.68GB），补全 2×2 矩阵后结论是：外部 pose
模式下四个格点的跨帧重投影残差中位全部 <1%，K 和分辨率都是二阶项，pose 质量才是
一阶项；同时证伪了 6/6 那份历史 @504 数据（实验变体，非本管线代表作）。**

## 1 方法与管线同一性

- 推理 driver：`tools/python/official_pytorch_k_sweep.py`（6/5 原版，零改动），由
  `tools/python/official_pytorch_k_sweep_mps_chunked.py` shim 启动——shim 只做一件事：
  把 `da3base_official_streaming_oracle.install_mps_chunked_sdpa`（oracle K=35 已验证的
  query-chunked 精确 SDPA）装到 `F.scaled_dot_product_attention` 上，再原样调 sweep main。
- 输入同 6/5 冻结版：`strict_window_000_highres_official_manifest.json` 前 K 帧 +
  ARKit `cameraExtrinsic4x4`/`cameraIntrinsicFxFyCxCy`，`saddle_balanced` +
  `upper_bound_resize`，MPS fp32，umeyama pose_scale 归一。
- 跨帧几何审计：`tools/python/official_pytorch_image_only_geometry_consistency_audit.py`
  （6/5 老管线工具，零改动）——高 conf 像素 backproject → 投影到 prev/prefix 帧 →
  z 与目标帧深度的相对残差。

### chunked SDPA 数学等价性（grounded）

| 对照 | depth max\|Δ\| | conf max\|Δ\| | 结论 |
|---|---|---|---|
| control（patch 装上但不触发）vs 今晨无 patch 复现 | 4.77e-7 | 0 | MPS 确定性地板 |
| chunked（触发）vs 无 chunking | 2.49e-3（rel 9.2e-4） | 3.9e-2（rel 1.7e-3） | 全部归因 fp 重排（fp32 softmax + 分块 matmul 顺序），extrinsics/intrinsics 位级一致 |

K=35@742 的全局 cross-view attention score buffer 估算 **138.62 GiB**（这就是历史
"Invalid buffer size: 89.01 GiB" 同族死法）；query_chunk=256 分块后整进程 RSS 1.68GB。

## 2 2×2 矩阵（全部 2026-06-10 同日同管线，conf 为 raw 1+exp 契约）

| 格点 | token | forward | umeyama | conf med/p95 | 跨帧残差 med（overall/mean/max slot） | iPhone（predict 上限 43,260~44,460） |
|---|---|---|---|---|---|---|
| K=5 @ 420×742 | 7,955 | 3.0s | 0.5672 | 9.66 / 20.2 | 0.26% / 0.25% / 0.29% | ✅ 轻松 |
| K=5 @ 280×504 | 3,610 | 1.5s | 0.5947 | 6.66 / 13.6 | 0.27% / — / 0.49% | ✅ 轻松 |
| **K=35 @ 420×742（新格点）** | **55,685** | 73.7s | 0.6138 | 4.34 / 8.94 | 0.45% / 0.77% / 3.3% | ❌ 超上限 ~25% |
| K=35 @ 280×504 | 25,235 | 15.5s | 0.6206 | 3.83 / 8.31 | 0.52% / 1.10% / 3.9% | ✅ 上限内 |

- K=5@742 残差/conf 来自今晨复现 npy（与 6/5 冻结版 depth max|Δ|=4.77e-7 验证同一）。
- 同帧对照（slot1-4，同照片同 742）：K5 = [0.18, 0.27, 0.26, 0.29]%，
  K35 = [0.40, 0.28, 0.27, 0.43]% —— K 增大仅带来同量级内的轻微变差。
- K5 vs K35 共享前 5 帧逐像素深度差：RMS rel ≈3%，median ≈2.3-2.5%
 （两套各自自洽解之间的系统差，非噪声）。

## 3 6/6 历史 @504 数据取消格点资格

`external_pose_k35_window000_504_black_shadow_compare_2026_06_06/` 与今日 fresh @504：

| 指标 | 6/6 历史 | 今日 fresh |
|---|---|---|
| depth 互差 | median rel 11.3% / p95 24.2% | — |
| conf median | 1.005（conf-1 ≈ 0.005，崩塌） | 3.83 |
| 跨帧残差 overall-med / max | 11.5% / **125%** | 0.52% / 3.9% |

其 report 的 mode 字段本就自标 `diagnostic_only_pose_conditioned_not_product_path`
（暗影实验变体）。**以后引用外部 pose @504 一律以今日 fresh 为准。**

## 4 结论（回答"K 和分辨率谁重要"）

1. **外部 pose 下两者都不是一阶项**：四格点残差中位全部 0.26-0.52%，而 image-only
   同指标 7-9%（差 15-30 倍）。重影的一阶根因是 pose 质量，再次 grounded。
2. **K 轴买的是单窗覆盖度**：K=35 一次融合 35 视角（有效点 6.5M vs K5 的 0.93M），
   代价是 conf 降 ~2 倍、最差 slot 残差升到 3-4%（大 camera step 处）、计算量平方涨。
3. **分辨率轴买的是细节密度**：504→742 像素 ×2.17、conf +13-45%，残差几乎不动。
4. **产品含义**：iPhone BNNSGraph 把 K=35@742 钉死（55,685 token）；手机可跑的
   pose-conditioned 最优格点是 **K=35@504（25,235 token）或 K=5@742（7,955 token）**。
   后续真正的决策变量是 coverage 策略：多窗 K=5@742 拼接 vs 单窗 K=35@504，
   以及外部 pose 模式残余的 0.3-0.5%（中位）/ 3-4%（最差处）跨帧不一致如何在
   fusion 层处理。

## 5 产物索引

- `k35_res742_chunked/`、`k35_res504_fresh/`、`k05_res504_fresh/`、
  `k05_res742_chunked_smoke/`、`k05_res742_nochunk_control/` —— sweep 报告 +
  官方 GLB 同款过滤 PLY/PNG（npy 本地保留未入库，可由已入库代码 + manifest +
  照片确定性重生成，等价性已证到 4.77e-7）
- `geometry_consistency/` —— 五份跨帧重投影审计 JSON/MD（含 6/6 历史版的证伪记录）
- `matrix_viewer.html` —— 2×2 联动点云 viewer（`python3 -m http.server` 后打开）
- 工具新入库：`official_pytorch_k_sweep_mps_chunked.py`（shim）、
  `single_case_official_filter_pointcloud_export.py`（单 case 官方过滤导出 driver）、
  `da3base_official_streaming_oracle.py`（补录：oracle 本体此前一直未入库）
