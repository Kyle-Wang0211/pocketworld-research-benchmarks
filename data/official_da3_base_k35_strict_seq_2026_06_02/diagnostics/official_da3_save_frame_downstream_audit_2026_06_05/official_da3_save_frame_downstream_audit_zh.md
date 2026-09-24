# Official DA3 save-frame downstream audit

日期：2026-06-05

## 结论

- status: `official_save_frame_downstream_aligned`
- goal complete: `False`

Dart refreshed da3_k_windows.json now carries officialSaveFrameIDs/downstreamFrameIDs, and the corrected official postprocess depth_index for window_016 keeps 17 official downstream frames instead of all 35 CoreML slots.

Re-run thickness attribution on the corrected official-save depth_index and adjacent window_017 ownership; do not treat full-chunk tail slots as window_016 downstream evidence.

## 大白话

- 官方 CoreML/PyTorch chunk 可以算 35 帧，但官方 results_output 不把 35 帧全都交给 downstream。
- window_016 的官方 downstream 只有前 17 帧：cap-1346 到 cap-1448；cap-1453 之后是 withheld overlap。
- cap-1396 是 window_016 官方 downstream 帧，所以它仍然是 window_016 厚层/几何一致性嫌疑。
- cap-1514/cap-1529 不是 window_016 官方 downstream；它们属于 window_016 full-chunk tail，并在 window_017 被官方 downstream 接收。
- 因此之前 full 35-slot 厚层分析不是废掉，而是要改口径：它说明模型在一个 K35 输入内会产生 tail inconsistency；产品/官方 downstream 应按 save-frame ownership 归因。

## Window 016

- full CoreML slots: `35`
- official downstream frames: `17`
- withheld overlap frames: `18`
- old full-chunk depth_index frames: `35`
- new official-save depth_index frames: `17`

## Suspect Frame Ownership

| frame | windows / local slots |
|---|---|
| `cap-1396` | window_015[slot=27, downstream=False, withheld=True, bridge=False, core=True]; window_016[slot=10, downstream=True, withheld=False, bridge=True, core=False] |
| `cap-1459` | window_016[slot=20, downstream=False, withheld=True, bridge=False, core=True]; window_017[slot=3, downstream=True, withheld=False, bridge=True, core=False] |
| `cap-1488` | window_016[slot=21, downstream=False, withheld=True, bridge=False, core=True]; window_017[slot=4, downstream=True, withheld=False, bridge=True, core=False] |
| `cap-1514` | window_016[slot=24, downstream=False, withheld=True, bridge=False, core=True]; window_017[slot=7, downstream=True, withheld=False, bridge=True, core=False] |
| `cap-1529` | window_016[slot=28, downstream=False, withheld=True, bridge=False, core=True]; window_017[slot=11, downstream=True, withheld=False, bridge=True, core=False] |
| `cap-1555` | window_016[slot=34, downstream=False, withheld=True, bridge=False, core=True]; window_017[slot=17, downstream=False, withheld=True, bridge=True, core=False]; window_018[slot=0, downstream=True, withheld=False, bridge=True, core=False] |
