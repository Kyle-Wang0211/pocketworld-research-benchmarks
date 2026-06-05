# Official DA3 external light refresh

日期：2026-06-04

## 结论

- 官方 GitHub main 没有出现能改变当前判断的新提交；repo `pushed_at` 仍是 `2026-03-21T07:14:45Z`。
- Issue #254 仍然 open，且 comments 仍为 `0`。官方还没有在这个室内近距离/宽视角/重影 issue 下给出处理建议或 hidden cleanup 路径。
- PR #256 `Real-time Streaming Support for DA3-Streaming` 仍然 open，状态 clean；它仍应被看作实时入口/streaming 支持，而不是已合入的单 window 点云去厚方案。
- 论坛/社区方向没有改变前面的判断：没有看到“DA3 室内近距离普遍不可用”的一致信号；更常见的是点云/GLB/PLY/Blender/ComfyUI/坐标 convention/资源门槛等工程层问题。

## API snapshot

### Official repo

- URL: https://github.com/ByteDance-Seed/Depth-Anything-3
- default branch: `main`
- pushed_at: `2026-03-21T07:14:45Z`
- updated_at: `2026-06-04T14:49:43Z`

### Issue #254

- URL: https://github.com/ByteDance-Seed/Depth-Anything-3/issues/254
- title: `DA3-Streaming 在室内近距离宽视角视频中出现 chunk 内/跨 chunk 多重影和局部错位，请教推荐配置与处理方式`
- state: `open`
- comments: `0`
- updated_at: `2026-05-12T14:48:54Z`

### PR #256

- URL: https://github.com/ByteDance-Seed/Depth-Anything-3/pull/256
- title: `Real-time Streaming Support for DA3-Streaming`
- state: `open`
- mergeable_state: `clean`
- updated_at: `2026-05-13T18:11:00Z`

## 对当前工程判断的影响

- 继续锁官方 image-only baseline，不回退 AR/VIO。
- 继续把 `_pose` CoreML 视为 compatibility/reference，不把它的厚层结果直接归因给官方 DA3-Streaming。
- 继续把 `results_output/frame_*.npz + npz_output_process.py` 作为 official downstream baseline；没有新证据表明官方 downstream 有隐藏的单 window surface fusion。
- 当前最高优先级仍是取得 `DA3BASE_476x742_N35_image_only.mlpackage/.mlmodelc`，再跑 readiness、Mac export、overlap regression gates。
