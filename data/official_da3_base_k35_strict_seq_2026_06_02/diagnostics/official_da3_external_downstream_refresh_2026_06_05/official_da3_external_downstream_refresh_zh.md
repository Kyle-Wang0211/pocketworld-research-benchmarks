# Official DA3 External Downstream Refresh

日期：2026-06-05

## 结论

- 官方仓库继续支持当前商用判断：`DA3-BASE` 和 `DA3-SMALL` 是 Apache-2.0；`DA3-LARGE/GIANT/NESTED` 是 CC BY-NC 4.0，不适合作为 PocketWorld 商用主线。
- 官方 `DA3-Streaming` README 把 streaming 定义为 chunked long-video / large-scene pipeline；它输出 `pcd/combined_pcd.ply`，并可选输出 `results_output/frame_*.npz` 再用 `npz_output_process.py` 融合。
- 这次本地源码和实测都显示：`results_output` 的 core-frame 选择主要是跨 chunk 去掉 overlap 帧，不是单 window 内的表面融合/去厚算法。
- 社区侧没有看到“DA3 官方普遍必然厚层”的强信号；更常见的是 3DGS/点云 downstream 对初始化点云、pose/depth consistency、crop/filter 很敏感。

## 外部信号

- 官方 DA3 主仓库说明 API 输出 `processed_images/depth/conf/extrinsics/intrinsics`，并支持 `glb/npz/ply/3DGS videos` 等导出格式。
  URL: https://github.com/ByteDance-Seed/Depth-Anything-3
- 官方模型表显示 `DA3-BASE` 为 Apache-2.0；`DA3-LARGE/GIANT/NESTED` 为 CC BY-NC 4.0。
  URL: https://github.com/ByteDance-Seed/Depth-Anything-3
- 官方 DA3-Streaming README 说明 `combined_pcd.ply` 是 all-frames point cloud；`results_output` 是额外保存的 frame NPZ，并可用 `npz_output_process.py` 验证融合。
  URL: https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/da3_streaming/README.md
- 3DGS 社区里有长期讨论：rendering 好不等于导出的 point cloud 适合点云任务；messy point cloud / background noise / featureless regions 是常见 downstream 风险。
  URL: https://github.com/graphdeco-inria/gaussian-splatting/issues/427
- Reddit/computervision 有用户把 DA3 用作手机视频到点云的快速原型，并指出 DA3 的一致性让它能从 monocular images 估 depth/camera positions 再 merge 成 point cloud；这支持“DA3 有实际 C 端/移动端兴趣”，但不是算法正确性证据。
  URL: https://www.reddit.com/r/computervision/comments/1pcp046/almost_instant_world_to_point_cloud_capture/

## 对 PocketWorld 的含义

- 产品主线继续锁 `DA3-BASE`，不要碰非商用 checkpoint。
- 不要把 `combined_pcd.ply` 当作“官方去厚结果”；它只是每个 chunk PLY 的合并。
- 不要把 `results_output + npz_output_process.py` 当作“单 window 表面去重”；它更像官方暴露的可复现 frame-level downstream。
- 现在的主问题仍是：在 K35 移动端约束下，官方 image-only cam_dec/preprocess 输出的 pose/depth consistency 能做到什么程度，以及产品最终该采用哪条官方 downstream 语义。
