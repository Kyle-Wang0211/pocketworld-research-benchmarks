# Official PR #256 real-time streaming audit

日期：2026-06-04

## 范围

审计官方 PR：

- URL：<https://github.com/ByteDance-Seed/Depth-Anything-3/pull/256>
- 标题：`Real-time Streaming Support for DA3-Streaming`
- 状态：open
- base：`main` / `41736238f5bced4debf3f2a12375d2466874866d`
- head：`641a8b7ef86dbdbcbe165299296f6687a201f4c0`
- commits：3
- changed files：3

变更文件：

- `da3_streaming/README.md`
- `da3_streaming/da3_live.py`
- `da3_streaming/setup_da3.sh`

## 结论

PR #256 没有修改官方 `save_depth_conf_result`、`npz_output_process.py`、`save_confident_pointcloud_batch` 的 core-frame downstream 语义，也没有新增 voxel/TSDF/surfel/per-surface dedupe。

它主要新增一个实时/视频/webcam 入口 `da3_live.py`，让 DA3-Streaming 能 chunk-by-chunk 处理视频，并输出 preview/final PLY。它不是一个新的官方“重叠点云消除算法”。

## Diff 关键词检查

PR diff 统计：

- `save_depth_conf_result`：0
- `npz_output_process`：0
- `save_confident_pointcloud_batch`：3
- `merge_ply_files`：2
- `combined_pcd`：6
- `overlap`：37
- `voxel`：0
- `dedup`：0
- `pointcloud`：10

含义：

- PR 没动官方 core-frame npz downstream 脚本。
- PR 仍引用 `save_confident_pointcloud_batch` 和 `merge_ply_files`。
- 没有出现 voxel/dedup 类关键词。

## `da3_live.py` 关键行为

### 1. 仍做 official confidence offset

`_infer_chunk` 中：

```python
predictions.conf -= 1.0
```

这和 DA3-Streaming 现有语义一致。

### 2. preview PCD 是累加显示，不是去重

`_accumulate_preview_pcd` 中：

- depth → point cloud
- confidence threshold = `mean(conf) * conf_threshold_coef`
- mask 后构建 Open3D point cloud
- `self.combined_pcd += chunk_pcd`

这是 preview 叠加，不是 per-surface dedupe。

### 3. final PLY 仍是 chunk PLY + merge

`_save_final_plys` 中：

- 读取每个 unaligned chunk `.npy`
- 应用累计 Sim3
- 调用 `save_confident_pointcloud_batch`
- 写入 `pcd/{chunk_idx}_pcd.ply`

CLI 结尾：

```python
merge_ply_files(os.path.join(save_dir, "pcd"),
                os.path.join(save_dir, "pcd/combined_pcd.ply"))
```

这仍是 full chunk PLY merge path，不是 core-frame `results_output/frame_*.npz + npz_output_process.py`。

### 4. `remove_duplicates` 不是点云去重

`remove_duplicates(data_list)` 只在 loop closure candidate list 上使用：

- 输入来自 `process_loop_list`
- 用于去掉重复 loop item
- 不处理点云 vertex，也不处理同一 surface 的多帧投影

## 对 PocketWorld 的影响

PR #256 不改变当前判断：

- APP official baseline 仍应走 `results_output/frame_*.npz + npz_output_process.py` core-frame downstream。
- `pcd/combined_pcd.ply` / live final PLY 仍不是最适合 APP 官方 baseline 的路径，因为它保留 full chunk PLY merge 语义。
- K35 单 window 内厚层仍应优先看 upstream depth/pose/scale 几何一致性，而不是等待 PR #256 提供 downstream 去重。

## Plain-language answer

PR #256 是“实时跑起来”的入口，不是“把重叠点云清薄”的入口。

它可以帮助长视频/实时 webcam 内存 bounded 地 chunk 处理，但它没有给我们一个官方认可的 voxel/TSDF/surfel 去重步骤。对 APP 来说，它加强的是“官方 live 也还是 chunk + Sim3 + threshold + PLY merge”的认知，而不是推翻现在的 core-frame downstream 选择。
