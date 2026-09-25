# VIO 会话归档(2026-09-25 第二批,b)

会话 2359d42b 在 2026-09-25 已完成工作的分析产物。原始位置是本机 scratchpad 和 `~/Developer/arloopbench_builds`,归档后本地副本已删除。
逐文件的原路径、大小和 sha256 见 `MANIFEST.tsv`(第一列是判定,见下文)。大于 2 MB 的文本已压成 `.gz`,sha256 记的是压缩前的原文件。

## 目录

| 目录 | 内容 | 文件数 | 体积 |
|---|---|---|---|
| `scratchpad/offline_sfm/` | 离线 SfM 臂对照:summary / quality / sweep 汇总,tools,feeds 的 selection json,各 run 的 metrics.json、run.log、err.log、cmd.txt、delivered_poses.txt、official_finalize_segments.json | 6327 | 48 MB |
| `scratchpad/preint/` | IMU 预积分改 OKVIS2 离散:tools、stats、cfg、ruler/ruler3 报告、回放日志、编译日志,诊断补丁 `diag_patches/`(见下) | 1493 | 22 MB |
| `scratchpad/ruler_audit/` | LiDAR 米尺 v2 审计:脚本、报告、v2runs 与 v2runs_intersection 的报告和日志、tums、合成录制的报告与 manifest | 209 | 8 MB |
| `scratchpad/wobble/` | 分段尺度摆动:tools、stats、cfg、runs 的轨迹(tum)、逐帧日志(jsonl,已压缩)和回放日志 | 429 | 31 MB |
| `scratchpad/bkpose/` | 后端位姿出口:日志、ruler 报告、runs 日志与评估 json、tools、cfg | 110 | 1 MB |
| `scratchpad/xrchain/` | XRSLAM → SfM 重建链:日志、VERIFY 草稿、提交说明、runs 日志与链路表(tsv/ref)、tools(含 `xr_propagate2.cc`) | 77 | 4 MB |
| `scratchpad/photo_size_survey/` | 照片尺寸调研:只收我们自己写的 3 份 notes*.md | 3 | <0.1 MB |
| `arloopbench_builds/unified_official_xrslam_rec30_expmid_backendpose_okvis2preint_20260925/mac_verify/` | 台架包 Mac 回放核验:stats、tools、selftest,rootcause 与 scale_and_accel 的结果、日志和逐帧 CSV,runs/runs_sweep 只收日志 | 1967 | 170 MB |
| `arloopbench_builds/*any43*/verify_build.txt` | 两个已被取代台架包的构建核验记录(VERIFY 正文已在 pocketworld `bench/entry-any-4x3` 里) | 2 | <0.1 MB |

## 对应的代码(都已推送)

- pocketworld(`Kyle-Wang0211/pocketworld`):`bench/backend-pose-recon@81f52bb`、`bench/okvis2-preint@3acfa75`、`bench/entry-any-4x3@36b6b33`、`bench/xr-recon-chain@fb3b587`、`bench/lidar-ruler-v2@979c967`。
- xrslam fork(`Kyle-Wang0211/xrslam`):`feat/backend-pose-output@8ebac9a`、`feat/okvis2-preint@4e8dda2`、`feat/xr-recon-chain@cd3469c`。
- `scratchpad/preint/diag_patches/xrslam-diag_on_4e8dda2.diff`:游离诊断工作树 `preint/xrslam-diag` 的全部未提交改动(含未跟踪的 `pw_diag_mix.h`),已验证可在 `4e8dda2` 上 `git apply --check` 干净套用。工作树随后移除。

## MANIFEST 判定

- `ARCHIVE`:已收入本目录。
- `REGEN`:可重生成或可重下载,未入库,本地已删。包括回放中间文件(hex、每帧 csv、tum、map)、编译产物和二进制、帧图像、点云、合成录制帧数组、下载的第三方文档和网页。
- `PRUNE_DIR`:整目录可重生成(编译目录、已推送的 git 克隆和工作树、App 包),只记一行汇总。
- `DELETED_REGEN`:磁盘紧张时在归档前先删掉的可重生成目录(帧 JPEG、编译目录、点云、SfM tracks 导出、LiDAR 中间数组、下载的论文),逐项记录路径、大小和理由。
- `INUSE`:另一个 agent 正在读取的文件(`offline_sfm/build/`、`feeds/13f5_p0_A.jsonl`、`runs/13f5_p0_A_r*`),本地保留,不入库。

## 重生成

- 回放:按各目录 `tools/run.sh`、`tools/build_mac.sh` 与 `cfg/*.yaml`,用上面的引擎提交和本机录制(`~/Developer/viobench-recordings/run-13f53d2f…`、`run-6d187dff…`、`run-73538ad6…`,录制原片不入库)重跑。`*.cmd` 记着每次运行的完整参数。
- 离线 SfM:`offline_sfm/tools/` 从录制生成 feed,再用 pocketworld 分支里的 SfM 核重跑。
- LiDAR 米尺中间数组 `pts_*.npz`:`ruler_audit/lidar_extract.py` 从录制重新导出。

## 入库前的检查

逐文件扫描了密钥、邮箱、签名身份、法律/专利关键词和 IP 地址,全部零命中(`KEEP_LOCAL` 0 个,需要剔除签名身份的 0 个)。
部分构建日志里有 `TeamIdentifier=26AH7V448L`。这个团队号早已公开在 pocketworld 的 `ios/Runner.xcodeproj/project.pbxproj` 里,日志里没有姓名或邮箱。
