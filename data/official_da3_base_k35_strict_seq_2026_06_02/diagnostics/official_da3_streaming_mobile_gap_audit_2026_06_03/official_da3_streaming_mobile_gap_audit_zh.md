# Official DA3 Streaming vs Mobile K35 差异核对

日期：2026-06-03

## 结论

当前不是 100% 官方复刻。我们已经把核心方向从旧 graph patch 拉回了官方路线：顺序窗口、官方后处理、官方 GLB/NPZ-style filter、dense Sim3 诊断、SelaVPR++ loop 检索诊断。但完整移动端生产路径和官方 DA3-Streaming 仍有差异。

最大的硬差异是窗口大小和运行时：官方默认 `chunk_size=120 / overlap=60 / loop_enable=True`，本路线因手机/平板/普通电脑约束固定为 `chunk_size=35 / overlap=18`，并使用 CoreML sealed `DA3BASE_476x742_N35_pose.mlpackage`。这不是简单参数偏差，而是计算图容量和输入契约的差异。

最大的可改进差异不是换算法，而是把剩余环节继续按官方语义落地：非重叠输出保存规则、adjacent dense Sim3 应用、loop/Sim3 优化路径、固定输入与官方动态宽高比的对照、以及 frame order 的稳定化。

## 官方默认是什么

本地官方代码：`tools/vendor/official_da3_streaming`。

- `configs/base_config.yaml`
  - `chunk_size: 120`
  - `overlap: 60`
  - `loop_chunk_size: 20`
  - `loop_enable: True`
  - `align_lib: triton`
  - `align_method: sim3`
  - `align_type: dense`
  - `ref_view_strategy: saddle_balanced`
  - `ref_view_strategy_loop: saddle_balanced`
  - `depth_threshold: 15.0`
  - `Pointcloud_Save.sample_ratio: 0.015`
  - `Pointcloud_Save.conf_threshold_coef: 0.75`
  - `Loop.SALAD.image_size: [336, 336]`
  - `Loop.SALAD.similarity_threshold: 0.85`
  - `Loop.SALAD.top_k: 5`
  - `Loop.SALAD.nms_threshold: 25`

官方 414 张按 `120/60` 切分是 6 个 chunk：`(0,120) ... (300,414)`。移动 K35/18 是 24 个 window：`(0,35) ... (391,414)`。

## 已经贴合官方的部分

- 顺序输入：已从旧 graph patch 改成按真实 timestamp 顺序的 sequential windows。
- 窗口策略：K35/18 是按官方 sliding-window 公式缩放，而不是自研选帧。
- 后处理：CoreML raw 输出已补齐官方 PyTorch 语义里的 Umeyama align、`pose_scale`、depth scale、intrinsics/extrinsics 回填。
- 点云诊断：micro audit 的 PLY/PNG 已按官方 GLB-style 和 NPZ streaming-style filter 导出。
- 相邻对齐诊断：已经做了 full 414 adjacent dense Sim3 诊断和最差边 PLY。
- loop 检索方向：生产约束下用 MIT 的 SelaVPR++ 替代官方 SALAD，且保留官方阈值诊断。

## 仍然不同的部分

| 类别 | 官方 DA3-Streaming | 当前移动 K35 路线 | 影响 |
|---|---|---|---|
| 窗口容量 | 120 帧 | 35 帧 | 官方单 chunk 看到更长局部上下文；移动端受内存/CPU 限制不能照搬。 |
| 重叠 | 60 帧，step 60 | 18 帧，step 17 | 重叠比例接近 50%，但绝对 overlap 少，dense Sim3 的约束点来自更短时间段。 |
| chunk 数 | 414 张约 6 个 chunk | 414 张 24 个 window | 移动端需要更多相邻拼接，累计 Sim3 误差风险更高。 |
| 模型运行时 | PyTorch `DepthAnything3` + safetensors | CoreML sealed `DA3BASE_476x742_N35_pose` | 不能假设逐输出完全等价；small-K parity 已做，但 K35 full parity 因内存未完成。 |
| 输入尺寸 | 官方 API 动态预处理，highres `upper_bound_resize` | 固定 742x476 direct_stretch 输入 | 这是结构性差异。已知 highres 4224x2376 若官方 `upper_bound_resize@742`，形状约 742x420，不是 742x476。 |
| 宽高比 | 官方保留原图比例并按 patch multiple 调整 | 移动端固定模型宽高比 | 边缘厚层、物体形状和 intrinsics 缩放都可能受影响，需要 A/B 证据。 |
| ref view | 官方 base/tum 默认 `saddle_balanced` | CoreML sealed model 的 ref view 等价性未逐输出证明 | 这是未证明 gap。不能说已经 100% 一致。 |
| confidence | 官方 streaming 中 `predictions.conf -= 1.0` | CoreML confidence 语义已做对照，但尺度仍有差异 | 官方 filter 能拉近 valid fraction，但数值尺度不是完全同分布。 |
| 相邻 Sim3 | 官方对相邻 chunk overlap 点云估计 Sim3，并累积应用 | 已做 adjacent diagnostics；完整生产级应用仍需严格复刻保存/应用流程 | 这会影响多 window 是否压到同一个表面。 |
| loop | 官方 SALAD + FAISS + NMS + loop Sim3 optimizer | SelaVPR++ MIT；官方阈值下当前没有 loop，0.80 仅诊断 | 换 VPR 不是厚层的直接证据；只有真实 loop pair 才能进入 Sim3 optimizer。 |
| loop optimizer | 官方 `Sim3LoopOptimizer`，默认 C++ | 当前只做过诊断/准备，未成为最终 CoreML full 414 输出 | 完整闭环约束还没证明对当前序列有效。 |
| 输出保存 | 官方 `save_depth_conf_result` 只保存每 chunk 非重叠核心帧，避免重复 overlap | micro audit 故意导出全窗口；最终 full 414 需要确认只保存 core frames | 重复 overlap 帧会让同一表面被多次写入，可能加厚。 |
| 点云采样 | 官方 `npz_output_process.py` CLI 默认 `sample_ratio=0.015`、`conf_threshold=mean(conf)*0.5`；DA3-Streaming full-chunk PLY config 使用 `0.75` | APP official core-frame baseline 已切到 `0.5`；历史诊断仍保留 `0.75` sensitivity/streaming-config 对照 | 需要继续区分 core-frame npz baseline 与 `pcd/combined_pcd.ply` full-chunk PLY 口径。 |
| 图像排序 | 官方直接 `sorted(glob(...))` | 我们用 timestamp 顺序 | 如果喂官方代码，必须先稳定重命名；否则 `cap-10`/`cap-2` 这类字典序会错。 |
| 平台依赖 | 官方 PyTorch/CUDA/triton/FAISS/SALAD | 目标是手机、平板、笔记本、苹果/安卓/鸿蒙 | 官方 Python 运行栈不能直接成为产品路径，只能作为 reference。 |
| 商业许可 | 官方 loop 默认 SALAD | 产品路径用 DA3-BASE Apache-2.0 + SelaVPR++ MIT | SALAD 只能做本地研究参考，不能默认进商业路径。 |

## 新诊断对 K35 厚层的指向

`window_016` 的 first10 -> first35 audit 显示，厚层是在单个 K35 window 内部已经出现的，不需要等跨 window loop 才产生。

- GLB-style：bbox 增长首次超过 1.10 在 `k=12`，first35/first10 bbox growth 约 `1.287`。
- NPZ-style：minor PCA 增长首次超过 1.35 在 `k=17`，first35/first10 minor growth 约 `1.474`。
- pose span：first35/first10 约 `4.595x`。
- depth p95：first35/first10 约 `1.074x`。
- confidence threshold / valid fraction 与厚层增长相关性弱。

读法：K35 厚层的直接制造者更像是单 window 内更大视角跨度下的 pose/scale/point-map 展开，而不是 loop。loop 可能帮全局闭环，但它不是 first35 厚层的直接来源。

## 能继续改进但不自研的方向

1. 先把最终 full 414 输出严格改成官方 `save_depth_conf_result` 语义：每个 window 只输出非重叠 core frames，overlap 只用于对齐，不重复写进最终点云。
2. 把 adjacent dense Sim3 从“诊断结果”升级成“生产输出应用流程”：按官方 `accumulate_sim3_transforms` 思路逐 window 应用到后续点云和 camera poses。
3. 对固定 742x476 做只读 A/B：不改手机模型，继续用 highres PyTorch reference 证明宽高比差异对地板厚层和地球仪形状的影响到底有多大。
4. 保持 DA3-BASE K35 sealed model 不变，但准备一个官方宽高比 CoreML export 候选作为研究对照；只有它明显改善且手机能承载，才考虑替换。
5. loop 先不降阈值硬造。生产路径保持 SelaVPR++ 商业安全；只有当官方阈值产生可信 loop pair，再进入官方 Sim3 loop optimizer。
6. 对 `window_016` 继续做官方一致性微审计：把 k=10、12、17、35 的 pose span、camera centers、depth p95、平面厚度和点云 PLY 放在一起看。
7. 严格锁定 frame order：如果用官方 runner 或 VPR 目录，先生成零填充顺序文件名，避免官方 `sorted(glob())` 把真实时序打乱。
8. 对 mesh/GLB 不要提前上 Poisson/清理算法。可以把 CloudCompare/MeshLab 作为离线观察工具，但产品算法先把官方输出链路对齐。

## 当前优先级

最高优先级不是找新 VPR，也不是自研清理点云，而是把移动端可承载的 K35/18 路线补齐到官方 streaming 输出语义：

1. K35 CoreML 官方后处理。
2. 官方非重叠 core-frame 保存。
3. 官方 adjacent dense Sim3 累积应用。
4. 商业安全 VPR 只在有可信 loop 时进入官方 Sim3 loop optimizer。
5. 再看 full 414 PLY 是否把 K35 thick layer 压回单表面。
