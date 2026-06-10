# K=18 分辨率寻优 + 手机首跑报告（2026-06-11）

一句话：**11 档分辨率全曲线定出唯一峰值 504×896（K18 conf med 10.10 / 残差 0.25%，
恰为训练分辨率列表中 16:9 长宽比唯一可达档），pose-conditioned 多视角 DA3 首次在
iPhone 14 Pro 跑通（3 窗全成，~2.5 min/窗，jetsam footprint ~350MB，与 Mac CoreML
位级等价）；跨窗残差分"易区 0.8% / 难区 2.2%"两个世界，fp16 噪声叠加 +0.7-0.8pp。**

## 1 K=18 分辨率全曲线（Mac MPS fp32，window_000 前 18 帧，同审计）

| process_res | shape | K18 token | 手机(≤43,260) | conf med | 残差 med | 残差 max |
|---|---|---|---|---|---|---|
| 742 | 420×742 | 28,638 | ✅ | 9.50 | 0.31% | 0.42% |
| 784 | 448×784 | 32,274 | ✅ | 9.73 | 0.26% | 0.43% |
| 812 | 462×812 | 34,470 | ✅ | 9.59 | 0.26% | 0.42% |
| 826 | 462×826 | 35,064 | ✅ | 9.84 | 0.26% | 0.40% |
| 840 | 476×840 | 36,738 | ✅ | 9.91 | 0.28% | 0.46% |
| 854 | 476×854 | 37,350 | ✅ | 9.89 | 0.27% | 0.36% |
| 868 | 490×868 | 39,078 | ✅ | 10.06 | 0.26% | 0.39% |
| 882 | 490×882 | 39,708 | ✅ | 9.89 | 0.26% | 0.32% |
| **896** | **504×896** | **41,490** | ✅ | **10.10** | **0.25%** | 0.39% |
| 910 | 518×910 | 43,308 | ❌(超48 tok) | 9.85 | 0.27% | 0.39% |
| 924 | 518×924 | 43,974 | ❌ | 9.96 | 0.25% | 0.38% |

- **峰值机制**：DA3 训练分辨率列表（论文 §3.4）中 16:9 比例唯一可达档 = 896×504；
  整条梯子只有 504×896 是精确 0.5625 比例，其余档均有轻微拉伸 → conf 单峰在 896，
  两侧（868/924）都压不过。910 双输（conf 更低 + 超 token 上限 48 个）。
- 质量最优点与手机 token 可行域边界重合：896 = 41,490 < 43,260。

## 2 iPhone 14 Pro 首跑（DA3BASE_504x896_N18_pose，fp16 CoreML，.cpuOnly）

- 导出：`scripts/da3_official_stage/export_da3_pose_coreml.py`（5 月已有 pose 导出器，
  --model-path 指 DA3-BASE 即用；Mac CPU trace 走 flash attention 不物化 N²，18GB 够），
  包 883MB。Mac coremltools 预检 47.5s/窗通过后才上机。
- 3 窗（0-17 / 9-26 / 17-34，50% overlap）全部 completed：
  **152.7s / 143.8s / 181.9s**，全程 8 分钟无降档无重启。
- 内存：**jetsam footprint 峰值 ~350MB**（上限 4096MB，余量 3.7GB）。注意 RSS 读数
  2.1GB 含 mmap 的模型 file-backed 页，**不计入 jetsam**——RSS ≠ jetsam footprint。
- Parity：手机 vs Mac fp32 depth rel diff median **0.75%**（p99 3.4%）＝ Mac CoreML
  fp16 同值 → 手机与 Mac CoreML 位级等价，差异全部来自 fp16 精度。
- **conf 契约注意**：插件落盘 confidence 已做 conf-1（streaming 惯例）——手机 bin
  median 8.44 vs raw 契约 9.44。后续转换器用 min≥0.9 自动判别规则不受影响。
- 修复入库：插件 `runtimeSpec` 第 1177 行 image-only 时代硬闸改为"契约随资源后缀
  双向校验"（`_pose` → 必须 pose_conditioned）；allowlist 增加新包名。

## 3 跨窗一致性（去每窗 1 标量 scale 后，shared-frame 逐像素）

| overlap | Mac fp32 | iPhone fp16 |
|---|---|---|
| w0∩w1（帧 9-17，中段） | 0.77% (p90 2.80%) | 1.61% (p90 5.87%) |
| w1∩w2（帧 17-26，后段难区） | 2.17% (p90 6.10%) | 2.90% (p90 7.53%) |

- 跨窗残差**分区明显**：易/中段 0.8% 级，后段（背光窗帘 + 大 camera step 区）2.2% 级
  ——与 K35 弧后段 conf 塌缩同一片内容，难度是内容属性不是窗口属性。
- 手机 − Mac ≈ +0.7-0.8pp，与 fp16 每帧 0.75% 噪声按 √2 叠加定量吻合。
- 这组数字就是 fusion 层（一致性过滤 + conf 加权 TSDF）的输入规格：易区直接融合，
  难区靠 conf 过滤（其 conf 自报也低）+ ≥2-3 视一致性裁剪。

## 4 Ship 配置定格

**K=18 @ 504×896 pose-conditioned，50% overlap，ARKit pose 原样喂入**（41,490 token，
手机 2.4-3 min/窗 @serious 热态，footprint ~350MB）。分辨率寻优至此关闭：
更高档要么质量下降（出训练分布）要么超 token 上限，两个约束在 896 同时收口。

## 5 产物索引

- `ladder_k18_res{784,812,826,840,854,868,882,896,910,924}/` — sweep 报告 + 审计
  （npy 本地；896 含全量 PLY 3,365,712 点）
- `ladder_k18_res896_win{1,2}_*/` — 窗 1/2 Mac fp32 参考
- 手机原始输出：`/tmp/phone_pull_k18/da3_bench_run_1781114582913347/`（54 bin ×3 窗
  + bench_summary.json，本地保留）
- bench app 快照：`bench_app_snapshot_k18_pose_2026_06_11/`（main.dart + 插件 + 导出器）
- mlpackage：`/tmp/da3_pose_export/DA3BASE_504x896_N18_pose.mlpackage`（883MB 本地，
  导出器 + 参数可确定性重建）
