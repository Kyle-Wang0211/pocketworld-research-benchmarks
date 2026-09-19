# TartanGround → CasDiffMVS 训练格式转换 + TG 白墙微调弹药包(2026-08-24/25)

2026-09-19 从本机 `~/Developer/tartanground_b_line/`(14 GB)抢救出的**全部非数据产物**
(116 个文件 / 1.9 MB)。数据部分当天删除,见文末。

**本目录此前从未推过。** 仓里只有 `experiments/vast_mvs_fullscale_20260914/scripts/tartanground2mvsnet.py`
这一个文件与本线有关;`finetune_pack/` 的 26 个文件、`REPORT.md`、`smoke_test.py`、
`step0/` 的脚本一个都不在。

## 这条线是什么

`REPORT.md`(08-24)的结论:**TartanGround 转成 CasDiffMVS 官方 BlendedMVS 训练格式可行。**
真实下载的 TG 子集(Office / P0000 / lcam_front,678 帧,~388 MB)跑通完整链路
—— 官方字段核查 → 转换 → 官方 `datasets/blend.py::MVSDataset` 真实 `__getitem__`
→ `casdiffmvs_mvgZeroDTU.ckpt` 真实前向:**0 missing / 0 unexpected 权重键,6 个 stage 输出
100% finite**,深度值范围与 cam.txt 的 depth_min/max 同数量级。共视分数逐字复刻官方公式,无自研。

`finetune_pack/`(08-25)是据此备的**租用机弹药包**:23 个 scan / 1776 帧 / 3.1 GB,
官方 dataloader 建表 1774 个训练样本(trainviews=9),分辨率唯一 576×768,
stage4 mask 有效占比中位 97.3% / 最低 93.2%。实验设计(用户拍板)= **只有一臂 B**
(TG 20% 混合微调),对照用现成 `mvgZeroDTU.ckpt` 零成本;臂 A 是条件臂,臂 C 不做。

## 必读三份(都在本目录)

| 文件 | 是什么 |
|---|---|
| `finetune_pack/RENTED_MACHINE_RUNBOOK.md` | 租用机执行手册,逐步命令 + 每步预期产物 |
| `finetune_pack/PROGRESS.md` | 制备过程增量记录:实测数字、判断、踩到的坑 |
| `finetune_pack/MANIFEST.md` | 弹药包清单 + 自检命令 |
| `REPORT.md` | 08-24 转换可行性报告(官方字段出处逐条) |

🔴 `PROGRESS.md` 末尾记着三个**未闭合缺口**,其中一条在 2026-09-19 救了一次盘:
`ethd3d_a_line/region_metric_20260824/cache/gt_labels_altwall.npy` **没有生成脚本,
必须整份拷贝不能重建** —— 清盘时据此把 `ethd3d_a_line` 整个排除在外。

## 已删除与如何再生(2026-09-19)

| 删掉的 | 大小 | 怎么再生 |
|---|---:|---|
| `finetune_pack/{raw,unz,tg_mvs}` | 6.9 G | `download_tg.py` + `convert_all.sh` |
| `step0/{raw,unzipped}` | 4.4 G | 同上 |
| `raw_download/` | 743 M | `download_tg.py` |
| `converted/` | 282 M | `convert_all.sh` |
| `tartanairpy/` `tartanair_tools/` | 146 M | 上游浅克隆 |

## 🔴 保留未删

`step0/phone_multi/` **1.1 G 保留**。`phone_sessions.json` 记的 8 个 `cap_*` 会话原件
仍在 `~/Documents/progecttwo/.device_backups.nosync/`(逐一核过 8/8 在),但第 9 项
**`b28_hotel/` 是那 132 张标准素材在本机唯一实体化的副本**:
`00000000.jpg` md5 前十位 `496a526547`,与租用机 `/root/mvs_P16k/images/00000000.jpg` 相同;
而本机 `_host_experiments.nosync/pose_ablation_20260818/b28_named/` 那份是 **0 字节的
iCloud 占位符**。租用机一销毁、隧道重下 80–180 KB/s ⇒ 按「绝不删采集数据」保留。

相关记忆:`project_pocketworld_ghost_wall_and_zerodtu_retrain`、
`feedback_derived_build_dirs_are_the_safe_reclaim`。
