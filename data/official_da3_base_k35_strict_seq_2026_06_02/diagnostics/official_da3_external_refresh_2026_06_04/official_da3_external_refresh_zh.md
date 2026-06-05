# Official DA3 external refresh

日期：2026-06-04

## 范围

本报告刷新官方 DA3 外部状态，用于 PocketWorld DA3 official-parity / commercial-safety 决策。

来源：

- Official repo：<https://github.com/ByteDance-Seed/Depth-Anything-3>
- Official PR #256：<https://github.com/ByteDance-Seed/Depth-Anything-3/pull/256>
- Official issue #254：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/254>
- Official issue #12：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/12>
- Hugging Face model cards / API：`depth-anything/*`

## GitHub 状态

`git ls-remote`：

- `HEAD` / `main`：`41736238f5bced4debf3f2a12375d2466874866d`
- `refs/pull/256/head`：`641a8b7ef86dbdbcbe165299296f6687a201f4c0`

GitHub API：

- PR #256 `Real-time Streaming Support for DA3-Streaming`
  - state：open
  - base：`main` / `41736238f5bced4debf3f2a12375d2466874866d`
  - head：`641a8b7ef86dbdbcbe165299296f6687a201f4c0`
  - commits：3
  - changed files：3
  - additions/deletions：`831 / 0`
- Issue #254 `DA3-Streaming 在室内近距离宽视角视频中出现 chunk 内/跨 chunk 多重影和局部错位...`
  - state：open
  - comments：0
  - created/updated：2026-05-12
- Issue #12 `DA3-long`
  - state：open
  - comments：4

## PR #256 diff 复核

Changed files：

- `da3_streaming/README.md`
- `da3_streaming/da3_live.py`
- `da3_streaming/setup_da3.sh`

关键词复核：

- `save_depth_conf_result`：0
- `npz_output_process`：0
- `save_confident_pointcloud_batch`：present
- `merge_ply_files`：present
- `combined_pcd`：present
- `overlap`：present
- `voxel`：0
- `dedup`：0

结论：

PR #256 仍然是实时入口 / live runner 更新，不是官方 downstream 去重、voxel、TSDF、surfel 或 memory-efficient attention 更新。它不改变 PocketWorld 当前应复刻 `results_output/frame_*.npz + npz_output_process.py` core-frame downstream 的判断。

## 许可证刷新

Official README model table 当前包含 `-1.1` refreshed checkpoints，并说明原始 `DA3NESTED-GIANT-LARGE`、`DA3-GIANT`、`DA3-LARGE` 已 deprecated。

### GitHub README 口径

- `DA3-BASE`：Apache 2.0
- `DA3-SMALL`：Apache 2.0
- `DA3-LARGE`：CC BY-NC 4.0
- `DA3-LARGE-1.1`：CC BY-NC 4.0
- `DA3-GIANT` / `DA3-GIANT-1.1`：CC BY-NC 4.0
- `DA3NESTED-GIANT-LARGE` / `DA3NESTED-GIANT-LARGE-1.1`：CC BY-NC 4.0
- `DA3METRIC-LARGE`：Apache 2.0
- `DA3MONO-LARGE`：Apache 2.0

Official repo `pyproject.toml` package license remains `Apache-2.0`, but model checkpoint policy must follow the model table / model-card license, not only the package license.

### Hugging Face card/API 口径

- `depth-anything/DA3-BASE`：Apache 2.0
- `depth-anything/DA3-SMALL`：Apache 2.0
- `depth-anything/DA3-LARGE`：CC BY-NC 4.0
- `depth-anything/DA3-LARGE-1.1`：Apache 2.0 on HF card/API
- `depth-anything/DA3-GIANT-1.1`：CC BY-NC 4.0
- `depth-anything/DA3NESTED-GIANT-LARGE-1.1`：CC BY-NC 4.0
- `depth-anything/DA3METRIC-LARGE`：Apache 2.0
- `depth-anything/DA3MONO-LARGE`：Apache 2.0

### Commercial decision

`DA3-LARGE-1.1` currently has a license mismatch: GitHub README table says CC BY-NC 4.0, while the HF card/API says Apache 2.0. For PocketWorld commercial use, treat this as unresolved and do not adopt `DA3-LARGE-1.1` until the upstream license is clarified.

Commercial-safe DA3-Streaming pose/depth baseline remains:

- `DA3-BASE` as current PocketWorld default.
- `DA3-SMALL` is also Apache 2.0, but it is not the current parity target.

`DA3METRIC-LARGE` and `DA3MONO-LARGE` are Apache 2.0 according to current official/HF metadata, but they are task-specific depth models and should not be treated as direct replacements for the current DA3-Streaming pose/depth baseline without a separate parity study.

## 对当前研究结论的影响

没有发现新的官方 downstream 去重或单 window surface thinning 方案。

当前判断保持：

- APP official baseline 继续走 `results_output/frame_*.npz + npz_output_process.py`。
- `pcd/combined_pcd.ply` / PR #256 live final PLY 仍是 full chunk merge 语义，不是更干净的 core-frame downstream baseline。
- K35 单 window 厚层仍优先归因到 upstream depth/pose/scale consistency gate。
- 商用路径继续锁 `DA3-BASE`，不要因为 `DA3-LARGE-1.1` HF card 当前显示 Apache 就改变产品 checkpoint。
