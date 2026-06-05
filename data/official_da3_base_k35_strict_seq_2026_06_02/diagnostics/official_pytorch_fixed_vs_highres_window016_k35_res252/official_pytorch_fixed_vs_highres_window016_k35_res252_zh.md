# Official PyTorch fixed-input vs highres dynamic：window_016 K35 process_res=252

日期：2026-06-04

## 结论

低分辨率趋势检查里，官方 highres 动态预处理比 APP fixed `742x476` 输入略干净，但差异不是灾难级。

- fixed sampled-cloud bbox diag：`1.815001`
- highres sampled-cloud bbox diag：`1.699973`
- fixed/highres bbox diag ratio：`1.067664`
- fixed/highres depth median ratio：`1.016097`
- fixed/highres confidence median ratio：`1.231635`
- camera-center diag 两边相同：`1.364758`

这说明 `direct_stretch 742x476` 仍是移动端 parity 风险，但当前证据不像是“fixed 输入单独造成严重厚层”。更强线索仍是 K35 内多帧 DA3 上游 pose/depth/scale 几何一致性。

## 输入口径

- fixed：`photos_depth`，APP fixed `742x476` 输入缓存，官方 PyTorch 再走 `upper_bound_resize` 到 `35 x 168 x 252`。
- highres：`photos_highres` 原图，官方 PyTorch 自己走 `upper_bound_resize` 到 `35 x 140 x 252`。

## 限制

这不是同分辨率 hard parity。`process_res=742/476` 的 K35 PyTorch 在本机 MPS attention buffer 上失败，因此这条只作为 Gate B 的低分辨率趋势证据。
