# Official DA3 external light refresh

日期：2026-06-05

## 结论

- 官方 GitHub issue #254 与当前问题高度同类：室内近距离、宽视角视频、chunk 内多重影、跨 chunk 局部错位、完整 chunk append 放大 overlap ghosting。
- 外部信号没有证明 DA3 官方已经内置“单 window 表面融合去厚”。
- 外部信号支持我们当前修正：产品/Research 不能把 full 35-slot chunk 全量当 official downstream；必须按 `save_depth_conf_result/results_output/frame_*.npz` 的 official save-frame ownership 做归因。

## Sources

- GitHub issue #254: https://github.com/ByteDance-Seed/Depth-Anything-3/issues/254
- GitHub issue list snapshot: https://github.com/ByteDance-Seed/Depth-Anything-3/issues
- GitHub issue #244: https://github.com/ByteDance-Seed/Depth-Anything-3/issues/244
- DA3 API docs: https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/docs/API.md
- r/GaussianSplatting DA3 discussion: https://www.reddit.com/r/GaussianSplatting/comments/1p70u57/depth_anything_3_is_super_fast/

## Readout

GitHub #254 describes DA3-Streaming on indoor close-range mobile-style video. The issue reports that one chunk can already produce multiple nearby surfaces when texture, reflection, transparency, or occlusion make local visual constraints weak. It also separates this from cross-chunk Sim3 alignment limitations and from downstream viewer behavior that appends full chunks including overlap frames.

That is the same distinction our local corrected diagnostics now enforce:

- `window_016` full CoreML slots: 35
- `window_016` official downstream save frames: 17
- `window_016` withheld overlap frames: 18
- `cap-1514/cap-1529` are full-chunk tail risk in `window_016`, but official downstream ownership moves to `window_017`
- `cap-1396` remains in `window_016` official downstream and remains the strongest local geometry-consistency suspect

The Reddit/3DGS signals are useful only as loose product-context evidence: DA3 is being explored as fast point-cloud / 3DGS input, but those threads do not establish a hidden official DA3 dedup/fusion step.

## Product Implication

For the official-replication path, do not add voxel/TSDF/surfel thinning and call it DA3 parity. Those are later product adaptations. The immediate official-parity work is:

1. Keep Dart-owned `officialSaveFrameIDs/downstreamFrameIDs`.
2. Re-run attribution on official downstream ownership, not full-chunk merge.
3. Inspect `window_016` official downstream around `cap-1396`.
4. Run adjacent `window_017` attribution for `cap-1514/cap-1529`.
