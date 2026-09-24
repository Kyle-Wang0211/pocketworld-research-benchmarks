# Official DA3 forum / issue watch

日期：2026-06-04

## 目的

检查官方 GitHub issues / PR、Hugging Face discussions、公开 web 搜索中是否出现：

1. DA3-Streaming chunk 内或跨 chunk ghosting / 多重影 / double instances 的官方解释。
2. 官方 hidden downstream cleanup，例如 voxel、TSDF、surfel、per-surface dedupe、overlap pointcloud thinning。
3. 官方推荐的 mobile / laptop / tablet 可运行路径。
4. 官方对大显存 OOM 的解释，避免把本机 PyTorch/MPS memory gate 误读成产品硬件门槛。

## 数据源

### GitHub

Repo：<https://github.com/ByteDance-Seed/Depth-Anything-3>

刷新方式：

- GitHub Search API：`DA3-Streaming`
- GitHub Search API：`ghosting OR overlap OR chunk OR stitching`
- GitHub Search API：`pointcloud OR ply OR combined_pcd`
- GitHub Issues API：#254, #12, #132, #185, #204, #230, #198
- GitHub PR API：#256 files / metadata

### Hugging Face

模型讨论 API：

- <https://huggingface.co/depth-anything/DA3-BASE>
- <https://huggingface.co/depth-anything/DA3-SMALL>
- <https://huggingface.co/depth-anything/DA3-LARGE>
- <https://huggingface.co/depth-anything/DA3-LARGE-1.1>

### Web search

查询词：

- `Depth-Anything-3 DA3-Streaming ghosting chunk overlap`
- `Depth Anything 3 chunk stitching multiple instances point cloud`
- `DA3-Streaming point cloud overlap dedup`
- `site:huggingface.co/depth-anything/DA3-BASE discussions DA3 Streaming`

GitHub issue / PR 和 Hugging Face API 是本报告的主证据；web search 未发现比官方 GitHub/HF 更强的公开修复路径。

## GitHub findings

### Issue #254：DA3-Streaming 室内宽视角 ghosting

链接：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/254>

状态：

- open
- created / updated：2026-05-12
- comments：0

内容相关性：

- 该 issue 直接描述移动设备室内近距离视频、约 120 度对角视角、chunk 内多重影、跨 chunk 局部错位、完整 chunk append 放大 overlap 重复显示。
- 提问者也提出了与我们相同的判断：只导出 non-overlap 新帧可能更合理；整体 Sim3 无法解决局部不同方向偏差；confidence map 可能用于过滤重复近邻表面。

结论：

- 这是与 PocketWorld 当前问题最接近的公开 issue。
- 截至本次刷新，官方没有回复，也没有给出 hidden dedupe 或 mobile-safe 参数方案。

### Issue #12：DA3-Long / 长视频 / chunk 拼接多实例

链接：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/12>

状态：

- open
- created：2025-11-14
- updated：2025-12-06
- comments：4

内容相关性：

- 用户询问 DA3-Long 是否会发布，以及 24GB VRAM 是否不足以处理长视频。
- 官方回复：DA3-Long 在 release plan，可参考 VGGT-Long。
- 后续用户反馈：chunk 拼接时会出现 same object 的 double / multiple instances；较大 batch 可以缓解，但受 VRAM 限制。

结论：

- 官方方向更像“未来 DA3-Long / long-sequence 方法”，不是当前 da3_streaming downstream 里已有隐藏清理。
- 社区反馈支持：跨 chunk 拼接 ghosting 是真实痛点，不是 PocketWorld 特有集成错误。

### Issue #132：DA3-Long 社区 wrapper 与 loop 问题

链接：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/132>

状态：

- open
- updated：2025-12-08

内容相关性：

- 社区有人把 VGGT-Long wrapper 改到 DA3 API。
- 用户反馈 DA3 wrapper 在行走/转身序列中 pose 不正确，disable loop 后出现 doubling effect。
- wrapper 作者提到 DA3 不提供 VGGT-Long 那类 `world_points` / `world_points_conf`，所以直接套用高置信点对齐不一定适合。

结论：

- DA3 长序列/loop/拼接仍是未稳定区域。
- 当前没有社区共识方案能替代官方 baseline。

### Issue #185：小 batch / chunk size 建议

链接：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/185>

状态：

- open
- comments：2

官方回复要点：

- `chunk_size` 建议大于 60。
- `overlap` 建议设为 `chunk_size` 的一半，例如 60/30。

结论：

- 官方推荐方向是足够大的 chunk 和半 overlap。
- 这对手机/平板是压力点：产品必须在可承受内存/延迟下验证质量，而不能默认沿用完整桌面参数。

### Issue #204：700GB OOM / BF16 vs FP32

链接：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/204>

状态：

- closed
- created：2026-01-13
- updated：2026-02-10

内容相关性：

- 用户在 V100/32GB 上运行 da3_streaming，遇到 669GB 级别 CUDA OOM。
- 官方回复：DA3 使用 BF16 训练和评估；V100 不原生支持 BF16，FP32 会显著增加显存并导致 OOM。

结论：

- 大 OOM 数字会被后端、精度和 attention 实现放大。
- 这支持当前解释：本机 MPS 的 15.36 GiB / 89.01 GiB 是 PyTorch reference gate 的实现门槛，不等于 APP/CoreML 产品一定需要同等内存。

### Issue #230：环境修正后仍有对齐异常反馈

链接：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/230>

状态：

- open
- updated：2026-02-27

内容相关性：

- 用户修正 CUDA / PyTorch 版本匹配后，单房间结果较好，但 Matrix City dataset 和相邻房间场景 align result abnormal。

结论：

- 即使环境问题解决，DA3-Streaming 在更复杂/跨空间场景仍可能出现对齐异常。
- 这仍指向上游几何/对齐限制，而非缺一个 downstream PLY dedupe。

### Issue #198：项目页 demo 的硬件/实现细节

链接：<https://github.com/ByteDance-Seed/Depth-Anything-3/issues/198>

状态：

- open
- comments：0

内容相关性：

- 用户询问项目页 demo 是否实时、使用什么硬件、是否有额外 post-processing、是否是公开 da3_streaming 原样实现。

结论：

- 官方尚未公开 demo 的硬件/后处理细节。
- 不能把项目页 demo 质量当作移动端 CoreML K35 可直接达到的证据。

### PR #256：Real-time Streaming Support for DA3-Streaming

链接：<https://github.com/ByteDance-Seed/Depth-Anything-3/pull/256>

状态：

- open
- updated：2026-05-13
- commits：3
- changed files：3

变更文件：

- `da3_streaming/README.md`
- `da3_streaming/da3_live.py`
- `da3_streaming/setup_da3.sh`

结论：

- PR #256 是 live / realtime runner 方向。
- 它没有修改 `save_depth_conf_result`、`npz_output_process.py`、core-frame 保存策略或 PLY merge 语义。
- 没有新增 voxel / TSDF / surfel / dedupe / pointcloud thinning。
- 不能把 PR #256 当成官方 hidden cleanup 或 mobile-ready 算法。

## Hugging Face findings

### DA3-BASE / DA3-SMALL

链接：

- <https://huggingface.co/depth-anything/DA3-BASE/discussions>
- <https://huggingface.co/depth-anything/DA3-SMALL/discussions>

发现：

- 主要是 model card / pipeline tag / paper link 的元信息 PR。
- 未发现 DA3-Streaming ghosting / overlap / mobile memory 的讨论。

### DA3-LARGE

链接：<https://huggingface.co/depth-anything/DA3-LARGE/discussions>

发现：

- 有 license clarification 讨论。
- 未发现可用于解决 K35 thick layer 或 mobile runtime 的官方说明。

### DA3-LARGE-1.1

链接：<https://huggingface.co/depth-anything/DA3-LARGE-1.1/discussions>

发现：

- 2026-05-23 有 `LARGE-1.1 model license?` open discussion。
- 这进一步说明 LARGE-1.1 的商用许可仍需谨慎处理。

结论：

- HF 讨论没有提供 hidden downstream cleanup。
- HF 讨论没有提供手机/平板/笔记本可直接承载 full DA3 的证据。
- Product checkpoint 仍应锁定 DA3-BASE，直到许可证和产品 runtime 都关闭。

## Product interpretation

### 需要租 A100 吗？

不建议把 A100 当作产品路线。

A100 / H100 的合理用途只有一个：短时租用，用来关闭 full same-resolution PyTorch K35 reference gate。

也就是验证：

1. 官方 PyTorch DA3-BASE K35 same-resolution 是否也有同样厚层。
2. 如果官方 PyTorch 也厚，厚层就是 DA3/K35 上游几何限制，APP downstream 不应继续背锅。
3. 如果官方 PyTorch 不厚，而 CoreML 厚，就继续查 CoreML export / preprocess / confidence / pose-scale 对齐。

这是一块“判断题 GPU”，不是产品部署 GPU。

### 这条管线要在手机/平板/笔记本上跑，意味着什么？

产品可行性必须按设备端指标判断：

- model：DA3-BASE，不是 LARGE/GIANT/NESTED。
- runtime：CoreML / ANE / GPU / CPU fallback。
- window：K35 是当前官方复刻目标，但产品可能需要 K、resolution、stride、关键帧策略再降级。
- downstream：先保留官方 core-frame npz baseline；产品层清理只能在官方 parity 之后标注为 product adaptation。
- acceptance gate：目标设备峰值内存、单 window latency、streaming latency、点云厚层质量。

如果只有桌面大 GPU 才能得到可接受几何质量，而 CoreML DA3-BASE 在手机/平板/笔记本上无论怎么调都达不到门槛，那么 DA3 对 PocketWorld 产品线就应降级或抛弃。

但当前证据还没有到“直接抛弃”的程度，因为我们尚未关闭这两个判断：

1. 官方 PyTorch same-res K35 reference 是否也厚。
2. CoreML DA3-BASE 在真实目标设备上的 latency / memory / quality 是否过线。

### 现在最理性的决策

短期：

- 不把 89.01 GiB 解读为产品需求。
- 可以租 A100/H100 几小时关闭 reference gate，但不要把它写进产品架构。
- 继续让 APP 保持官方 `results_output/frame_*.npz + npz_output_process.py` core-frame downstream baseline。

中期：

- 做目标设备 benchmark：iPhone / iPad / MacBook 分别测 K、resolution、latency、peak memory、厚层质量。
- 如果 DA3-BASE/CoreML 在目标设备上过不了，停止继续围绕 DA3-Streaming 做产品押注。
- 如果能过，但质量厚层仍存在，再把 voxel/TSDF/surfel/normal cleaning 作为明确的 product layer，而不是官方复刻。

## Decision update

外部论坛/issue 证据支持当前矩阵结论：

- DA3-Streaming ghosting / multiple instances 是公开存在的痛点。
- 官方没有公开 hidden pointcloud dedupe。
- 官方建议偏向 BF16/FP16、合适 chunk_size/overlap、DA3-Streaming/DA3-Long 方向。
- A100/H100 只适合一次性 reference gate，不是 PocketWorld mobile product dependency。
- 如果移动端 CoreML DA3-BASE 无法达标，算法应作为产品候选被降级或淘汰，而不是强行把 full DA3 搬到手机上。
