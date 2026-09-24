# K=90 iPhone 部署 + 分辨率边界 + image-only 终局报告（2026-06-10）

一句话：**K=90 image-only 在 iPhone 14 Pro 上全链路打通（R1 真机推理 → R2-R5 Mac → PLY），
BNNSGraph 边界摸清（predict 上限 43,260~44,460 token），但 image-only 的点云在物体级
dome 场景是雾——根因是 predicted pose 精度天花板，与 CoreML/fp16/分辨率/K 无关。
6/5 冻结的外部 pose 稳定版仍是视觉最好参考，路线应回归 external pose。**

---

## 1 BNNSGraph 边界（9 个 probe 全 grounded，iPhone 14 Pro iOS 26.3.1, .cpuOnly fp16）

Token = K × ((H/14)·(W/14) + 1 camera token)

| Token | 配置 | process_res | compile | predict | 9 窗全程 |
|---|---|---|---|---|---|
| 36,540 | 210×378 @K90 | 378 | ✅ | ✅ | 3 窗 probe ✅ |
| 40,410 | 224×392 @K90 | 392 | ✅ | ✅ | ✅ 1:00:03 |
| 41,850 | **224×406 @K90** | 406 | ✅ | ✅ | ✅ 1:07:15 |
| 43,260 | 280×504 @K60 | 504 | ✅ | ✅ | （历史 ship 配置） |
| 44,460 | 238×406 @K90 | 410 | ✅ | ❌ E5RT(11) | — |
| 45,990 | 238×420 @K90 | 420 | ✅ | ❌ E5RT(11) | — |
| 47,520 | 238×434 @K90 | 434 | ✅ | ❌ E5RT(11) | — |
| 51,930 | 252×448 @K90 | 448 | ✅ | ❌ E5RT(11) | — |
| 56,520 | 266×462 @K90 | 462 | ❌ compile fail | — | — |
| 57,680 | 280×504 @K80 | 504 | ❌ compile -4 | — | — |
| 64,890 | 280×504 @K90 | 504 | ✅ | ❌ E5RT(11) | — |

**结论**：
- predict 上限钉死在 **43,260 < limit ≤ 44,460**（约 1,200 token 的缝）
- compile 上限独立存在（~56,520 起拒绝，且与具体 shape 有关：64,890 反而 compile 过）
- K=90 官方 preprocess 可达梯子上的最高合规档 = **224×406**（41,850）
- 此边界对 pose-conditioned 模型同样适用（同一 BNNSGraph 执行器）

GPU 路径（.cpuAndGPU）已证不可用：MPSGraph 会 materialize attention score 矩阵
（K=60 都需 4GB+，K=90 需 8.4GB），叠加 GPU watchdog progress timeout。

放弃的旁路（全部 grounded 失败）：W8 量化（runtime 解压回 fp16 无效）、4-bit
palettization（同）、increased-memory-limit entitlement（4096MB 也不够 GPU 路径）、
Q-only chunked attention（BNNSGraph 限制在 K/V 长度不在 Q）、fp32 re-trace（compile -14）。

## 2 K=90 分辨率质量研究（R1 + R2-R5 双层对比）

### R1 层（overlap 帧深度自洽 + conf，同 pairs 0-1/1-2，全凉机段）

| 指标 | 224×392 | 224×406 | 210×378 |
|---|---|---|---|
| 同 pair 平均深度 RMS | 0.0796 | 0.0781 | 0.0693 |
| scale 偏离 1（两对） | 3% / 6.6% | 0.2% / 15% | 12% / 17% |
| conf median | 0.0381 | 0.0195 | 0.0020 |
| 深度像素/帧 | 87,808 | 90,944 | 79,380 |

210×378 的 RMS"更好"是**模糊更自洽假象**（细节少自然一致），其 scale 漂移最大、
conf 雪崩（-95%）、信息量最少 → 排除。

### R2-R5 层（两份完整 414 帧 fusion PLY）

| 指标 | 224×392 | 224×406 |
|---|---|---|
| fusion 点数 | 225,131 | 211,800 |
| bbox | **1.15×1.23×1.29 m** | 1.66×1.94×1.77 m（外扩 40-60% = 漂移） |
| Sim3 \|log-scale\| mean | 0.291 | 0.272 |
| 轨迹平滑度 accel RMS | **0.111** | 0.131 |
| 回环 | 5 对（两边完全一致） | 同 |

**Ship 裁决：224×392**（bbox 紧凑 + 轨迹平滑 + R1 RMS 优；406 仅 scale spread 单项略优）。

### 热行为（grounded）

- 第一个 window 永远 ~70-80s：SoC junction 温度在 build/install 间隙快速回落，
  thermalState 从 fair 起步；窗 1 起全程 serious，serious 内连续降频至 450-650s/窗
- 9 窗全程 RSS 120-450MB（4GB 预算 <12%），thermal 只影响速度不影响数值

## 3 重影根因（本日最重要结论）

**证据链**：
1. K=90 fusion 雾 → 单窗口（无跨窗对齐）也雾 → **R1 自身问题**
2. 6/5 的 K=35 **纯 PyTorch Mac 跑的基准同样雾**（当时正交缩略图掩盖了严重性）
   → 与 CoreML/fp16/降分辨率/K 值全部无关
3. 帧序空间连续性正常（相邻帧角距 median 3.5°，93%<20°）→ 不是帧序问题
4. 我们的 overlap 深度不一致 7-9% ≈ 官方 TUM benchmark 的误差率量级（ATE
   0.087m/3-5m 场景 ≈ 2-3%）——**误差率与官方一致，物体级 1.2m 场景把它放大成雾**
5. 外部 pose 版本（ARKit extrinsics/intrinsics）视觉好：pose-conditioned conf
   阈值 8.7 仍保留 60% 点 vs image-only conf median 0.02-0.04，**置信度差 200 倍**

**结论**：image-only 的 predicted pose 精度天花板，在物体级 dome 近距场景
（深度 0.4-1.7m）不可避免地表现为雾。官方 SALAD+Sim3 补偿的是轨迹级漂移
（我们的回环/轨迹/bbox 都正常），从不承诺 fusion 级逐像素对齐。字节论文
demo 好看的原因：场景级尺度 + GLB 导出默认 conf 过滤 top 60%。

## 4 路线建议

- image-only 复刻使命完成（6/5 NEW_SESSION_PROMPT 设定的目标）：官方语义全链路
  打通 + 边界摸清 + 天花板 grounded
- **production 回归 external pose 路线**（6/5 冻结版
  `handoff_2026_06_05_image_only_official_repro/02_external_pose_stable_frozen/`，
  K=5@476×742 + ARKit extrinsics/intrinsics，视觉最好）
- 今日所有成果直接迁移：BNNSGraph 边界约束 pose-conditioned 模型同样适用
  （K=5@476×742 = 9,015 token，远低于 43,260 上限，iPhone 轻松跑）；
  bench app / tensor 桥 / devicectl 流程 / 转换器全部复用
- 待讨论：K 与分辨率的重要性权衡（external pose 下 K 的边际价值 vs 分辨率），
  external pose 版本的剩余缺陷清单

## 5 产物索引

### 工具（已入库）
- `tools/python/da3_iphone_plugin_windows_to_oracle_chunks.py` — Plugin per-frame 输出 → oracle chunk npy（conf contract 自动检测）
- `tools/python/da3_k90_r1_resolution_compare.py` — R1 层跨分辨率质量对比
- `tools/python/da3base_official_streaming_oracle_resume.py` — 新增 `--clamp-last-chunk`（iPhone 静态 shape 最后窗对齐）+ `--loop-process-res`（loop 推理分辨率 pin）
- `tools/python/da3_iphone_window_outputs_to_oracle_chunks.py`、`run_k90_iphone_oracle.sh`（前一日版本）

### 数据（本目录 + 兄弟目录）
- `da3base_iphone_k90_224x392_oracle_2026_06_10/` — 392 完整 R2-R5 输出（pcd/*.ply、logs、loop_closures、camera_poses）
- `da3base_iphone_k90_224x406_oracle_2026_06_10/` — 406 同上
- `iphone_k90_raw_runs_2026_06_10/` — 三次 iPhone 原始输出（392 全程 / 406 全程 / 210 probe，1.3GB，gitignore 本地保存）
- `k90_resolution_study_2026_06_10/` — 对比 JSON、viewer html、bench app 源码快照、本报告

### Bench app（本地工程，源码快照已入库）
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_da3_bench/` — 独立 Flutter bench app
  （verbatim Da3DepthPlugin + 预算 tensor 直喂 + MAX_WINDOWS probe 模式 + increased-memory entitlement）

### mlpackage（本地，未入库）
- `/tmp/N90_*.tgz` 系列 + A100 `/root/output/`（**A100 instance 待删，仍计费**）
- iPhone 上已装：DA3BASE_210x378_N90（最后一次 build）
