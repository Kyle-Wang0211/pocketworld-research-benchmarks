# 会话临时产物归档（2026-09-24 至 09-25）

来源：Claude 会话 `2359d42b` 的 scratchpad。归档后，本地原目录已删除。

- 逐文件原路径、大小、sha256 见 `MANIFEST.tsv`。
- 大于 2 MB 的文本文件压成 `.gz` 存放，sha256 按压缩前的原文件计算。

## 目录

| 目录 | 内容 |
|---|---|
| `benchfull/` | 完整重建链（168 基线 / 168+修复包）并入台架的构建核验、适配记录 |
| `fixbuild/`、`fixC/` | 触闸修复包的构建与核对。fixC 源码快照未入库：修订号见 `fixC/AETHER3D_REVISION`、`POCKETWORLD_SHIM_REVISION`，补丁在分支 `data/rootcause-fixes-20260924` |
| `step1/`、`step2/` | 触闸根因排查的中间结果 |
| `scaleS2/`、`scaleS4/` | XRSLAM 尺度根因排查（官方规则、配置对照）的回放轨迹与日志 |
| `gtdata/` | 公开数据集上的评估：只存我们的运行结果，数据集本体和上游工具源码未入库 |
| `dip13f/` | 13f5 场尺度下沉排查（td 曝光中点）的反事实回放 |
| `expmid/`、`expmid_dart_test/` | 台架默认开曝光中点的构建核验、Dart 测试源码 |
| `g4/` | LiDAR 米尺 G4 对齐闸排查 |
| `lidarbench/`、`lidarrun/` | LiDAR 米尺台架与试跑配置 |
| `rec30/` | 30 Hz 录制器写入吞吐自测（原始传感器流 `.pwvi` 未入库） |
| `unified/` | 三个台架 App 合一的核验 |
| `xrhires/` | 跟踪分辨率实验。引擎改动在 xrslam fork 分支 `exp/hires-20260924` |

## 未入库，可重新生成或重新下载

以下文件逐个列在 `MANIFEST.tsv` 的 `REGEN` 行里：

- **编译产物**：dylib、Mach-O、Dart 编译缓存。
- **编译日志**：带签名身份和邮箱，含个人信息。
- **来自拍摄的图像和缩略图**，以及 `xr_shared/` 的 EuRoC 格式转换帧。后者可用 `~/Developer/arloopbench/tools/pwvi_to_euroc.py` 从录制重新生成。
- **公开数据集真值副本和上游工具源码**：ADVIO、EuRoC、zju eval-vislam。
- **论文 PDF**。

代码都已在远端：

- 台架：pocketworld 的 `bench/*` 分支。
- 引擎：xrslam fork 的 `feat/official-ios-rules`、`exp/hires-20260924`。
