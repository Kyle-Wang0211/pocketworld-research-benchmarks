# MVS / Infinigen 会话归档（2026-09-22 → 09-24，会话 ef47df10）

本目录是一个会话在 Mac scratch 里的**自有产物**，本地删除前先推到这里。第三方代码、论文和网页不在这里（见下文）。`MANIFEST.tsv` 逐个文件记录了原路径、sha256 和字节数。

## 目录

| 目录 | 内容 |
|---|---|
| `scratch_top/` | 本会话写的脚本（融合闸阶梯、动态一致性融合、自适应带宽、层尺、覆盖率、Infinigen 探针与对照、ARKit/GSO 普查、skyfix 回滚、调度脚本 v2/v3、复测、比较页生成等）和结果图（`cmp_full.jpg` / `cmp_fast.jpg` = 完整配方 vs fast_solve 随机 4 间，`wmg_sheet.jpg` = WMGStereo 室内样例，`ig*_cmp.png` / `sw_*.png` = Infinigen 分辨率/去噪/机位对照） |
| `box_toolchain/` | 旧训练箱（107.209.104.125）上的工具链快照。**这套工具链此前不在任何仓库里**（含 `ta2/tartanair_to_blend.py`、训练脚本、融合脚本、`colmap2mvsnet_np2.py`〔APD-MVS 版，HKUST 版权头原样保留，仅 `np.asscalar`→`.item()`〕） |
| `ak2/` | `arkit2blend_v2` 的批处理和验收脚本 |
| `box_taiwan/` | 台湾 16×5090 渲染箱（211.21.106.81）上的 Infinigen 官方流程脚本：`ig7_official.sh`（官方 `manage_jobs` 原命令 + 用户拍板的偏离，逐条写在脚本头）、3 小时超时看门狗、各轮收尾/续渲脚本、转换器 `infinigen_to_blend.py`、`infinigen_pr506_decorate.diff`（社区 PR #506 补丁，修 Infinigen 墙面材质 TypeError） |
| `gm_shots/` `dyn_shots/` `grid_shots/` `newep0_shots/` | 融合闸 thres=2/3、动态一致性、分辨率网格、新 ep0 的同机位对照截图 |

## 关键结论（详见本会话的记忆条目）

- **Infinigen 官方完整配方**（不带 fast_solve）在 384 核上 coarse 是 CPU 瓶颈：每间 20–120 分钟，约一半尝试失败（找不到机位 / libgomp 线程创建失败），实测约 1.5 间/小时。**fast_solve** 约 7–7.5 间/小时，但家具数中位 36 件，对比完整配方 91 件（小件求解 5 步 vs 50 步）。
- **单机模式下官方 `local_256GB.gin` 的坑**：`ground_truth/queue_render.gpus=0` 不分配卡，深度任务会占满全部 GPU 导致显存爆（已用官方开关 `gpus=1` 修好）；`--cleanup big_files` 会把渲染崩掉的场景也删掉 blend 文件；`--use_existing` 只续跑已有场景、不新建。
- **WMGStereo**（`princeton-vl/WMGStereo`，Infinigen 团队，CVPR 2026，**BSD-3**）：室内约 3,630 间，每间 20 个立体机位（40 张图，带 K/T），左目有视差（可换算深度），1280×720，房间里有刻意放置的浮空杂物。能否用于 MVS 训练待验证。

## 未入库、已从 Mac 删除（第三方，可重新获取）

`repos/`（MVSFormer、cascade-stereo、RAFT-Stereo、IterMVS、PatchmatchNet、PSMNet、SegFormer 等 git 克隆）、`mvsresearch/`（ACMMP、CVP-MVSNet、CasMVSNet_pl、D2HC-RMVSNet、MVSNet_pytorch 等源码包）、`mvs/` `sgm/` `lit/` `pdfs/` 和顶层 `*.pdf` / `*.txt` / `*.html`（论文、论文文字摘录、arXiv/知乎网页）、`conf/` `api/` `raw/` `misc/` `vfy/` `extra/` `iter/` `mvsx/` `cfnet/` `msn/` `col/` `gbi/` `ucm/` `cen/` `ton/`（各开源项目源码片段）、`mmsrc/` `mmdoc/` `mm.tar.gz`（MicMac）。

## 重文件（未入库）

| 文件 | 大小 | 去向 |
|---|---|---|
| `orb_thres.mp4`、`orb_2048.mp4` | 37 MB + 36 MB | 已从 Mac 删除。它们是 thres / 2048 分辨率对照的环绕视频，可在旧箱上用 `/root/orbit.py` / `/root/orbit2.py` 从对应点云重新生成（前提是那些点云还在旧箱上，删除前未逐个核对） |
| `ckpt_backup/`（full_ep0–6、sky_ep0、skyfix_ep0 的 model_000000） | 101 MB | **留在 Mac 本地，不删**（检查点备份，按规矩不动；md5 已与箱上核对过） |
