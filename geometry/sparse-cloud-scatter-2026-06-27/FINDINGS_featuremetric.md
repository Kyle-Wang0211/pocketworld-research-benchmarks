# featuremetric 精修(PixSfM 自研进 COLMAP 4.0.4)负结果 + SfM 极限定论 (2026-06-28)

承接 `FINDINGS.md`(稀疏球壳 ~0.5%span 是 bas-relief 深度歧义地板)。本次实测最后一个 SOTA 稀疏精度杠杆 —— **featuremetric 精修(PixSfM 的算法)**,确认它也压不动球壳。

## 为什么自研而非装 PixSfM
- **PixSfM 死于 2023**,pin 死 `pycolmap@v0.4.0`(COLMAP ~3.8),**无任何版本支持 COLMAP 4.x**;ducha-aiki M1-macos fork 也是旧 COLMAP。
- 用户硬约束 = 必须配生产线的 **COLMAP 4.0.4**。所以在 macOS 系统 python3.11(已有 torch 2.12 + **pycolmap 4.0.4** + kornia,`KMP_DUPLICATE_LIB_OK=TRUE` 解 libomp 冲突)上**自研重写** PixSfM 的 featuremetric 算法:pycolmap 4.0.4 读 242k 重建 → 稠密特征(DISK / 自实现 S2DNet 加载官方权重)→ torch autograd 批量投影+bilinear采样+Cauchy(0.25) featuremetric 优化点(及联合位姿)。

## 三次实测(地球仪点,球壳 std/R 0.08R 带)
| 配置 | 网络 | 位姿 | 球壳 前→后 | loss 地板 |
|---|---|---|---|---|
| 768/1.5k点/40it | DISK | 固定 | 4.44→4.44% | 0.0766 |
| 1600/15k点/120it | DISK | 固定 | 4.48→4.49% | 0.0766 |
| **1600/15k点/200it(完整PixSfM配方)** | **S2DNet** | **联合** | **4.48→4.49%** | **0.0683** |

完整配方(S2DNet 原生 featuremetric 网 + 联合位姿):**位姿仅动 0.017°、点仅动 0.23%R、球壳不变**。

## loss 地板成因解剖(关键)
loss 地板 ~0.068 = 优化后同一 3D 点各视图特征仍残留的方差。实测分解:
- **非位姿问题**:联合优化后位姿几乎不动(0.017°)、地板不降、球壳不变 → 位姿本来就最优。
- **非主要网络问题**:DISK(0.0766)→ S2DNet 一致性训练网(0.0683)只降 18%,仍高。
- **= 视角相关外观方差(根本性)**:同一表面点各视角本就长得不同,连一致性训练的 S2DNet 都做不到描述子相同。414 帧压不平因为这是系统性每视图外观,非随机噪声。
- 地板高 = featuremetric 信号弱 = 没有"一致目标"把点拉准 = 治不动球壳。

## SfM 极限最终定论
**手持 iPhone 环绕采集,稀疏 SfM 球壳(~4.5%球半径 / ~0.5%span)不可破。穷举证明:** K/分辨率/互检/宽基线/全局BA/迭代BA+retri/位姿先验/每帧相机/畸变模型/点过滤(tri/track/reproj)/稀疏图→稠密图78210/**featuremetric(DISK固定 + S2DNet联合,完整PixSfM配方)** —— 全部不动球壳。两个不可约根因 = bas-relief 几何深度歧义 + 视角相关外观方差。**稀疏 SfM 已达极限;登峰造极的薄表面是 dense MVS(CasDiffMVS)的活;稀疏云任务(准位姿+结构,242k/track6.87/0漂移)已完成。**

## 复现
脚本:`scripts/s2dnet_mod.py`(S2DNet standalone 重实现 + 加载官方权重),`scripts/fm_spike_s2d.py`(featuremetric 点+联合位姿精修 spike,pycolmap 4.0.4 + S2DNet + torch autograd)。环境:macOS python3.11 + `KMP_DUPLICATE_LIB_OK=TRUE`,torch/pycolmap-4.0.4/kornia,S2DNet 权重 dropbox `hnv51iwu4hn82rj`。
