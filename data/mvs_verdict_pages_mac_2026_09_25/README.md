# MVS 对照网页归档（Mac 本地 `pose_ablation_20260818`，2026-09-25）

这是 MVS / CasDiffMVS 研究线 09-01 → 09-20 在 Mac 本地的对照网页目录（`_host_experiments.nosync/pose_ablation_20260818/`，本地经 `127.0.0.1:8931` 查看）。Mac 数据盘写满，按「先推送、核对远端、再删」的规矩清理。

## 入库了什么

- `files/`：全部小文件（网页 `index.html`、`meta.json`、脚本、日志、文本，共 334 个 / 1.1 MB），保持原目录结构。本机用户目录路径已替换成 `~`。
- `MANIFEST.tsv`：原目录**每个文件**的路径、字节数、sha256 和处置状态（软链接记录指向）。状态有：
  - `已入库`：在 `files/` 里。
  - `第一档:可重生,待删|<权重>`：生成它的权重仍在本地（md5 已核），推理流程也在本仓库里，重新推理即可得到。这一批已从 Mac 删除。
  - `未入库:第二档,暂留本地待定`：权重已丢（AB 快档 ep3/ep5、MonoMVSNet 各版等），或者对应脚本在仓库里没找到。仍留在 Mac 上，是否删除由用户决定。
  - `未入库:拍摄原片/相机(本地保留)`：拍摄照片与相机文件，不入库。
- `dedup_symlinks.tsv`：同一份点云被整份复制到多个网页的，只留一份、其余换成软链接（sha256 相同，零损失，释放 2.06 GB）。

## 第一档怎么重新生成

- 推理：`quick_arm.sh` / `infer_arm.sh`（本仓库 `experiments/vast_mvs_fullscale_20260914/scripts/`，以及 `data/mvs_infinigen_session_archive_2026_09_24/box_toolchain/`），只换 `--loadckpt`；输入 = 同一组 132 张照片（本地保留，不入库）；融合门 thres=3。
- 点云转网页二进制：`ply2bins.py`；建页：`build_page_cli.py`。
- TSDF 过滤 / 网格版：`box_toolchain/tsdf_ep_mesh.py`。
- 权重（本地 md5）：`full_ep0` e71dc850、`full_ep1` d2225704、`full_ep2` 27ce2217、`full_ep3` f2bd4b74、`full_ep4` fd7642fd、`full_ep5` e0d79dc7、`full_ep6` e68754ad；AB 快档 ep0 cf1fa042、ep2 13de9afa、ep6 09aee44d、ep15 fcaab387；B 臂终点 1c95e17a。
- 注意：CasDiffMVS 是扩散式推理，每次运行有随机差，重跑结果不会逐位相同，只能验证落在「同机两次运行的随机差」之内。
