---
artifact_contract: "ce-handoff/v1"
created_at: "2026-09-03T04:57:25Z"
title: "PocketWorld MapAnything Apache 稠密点云重影与放射漂移全量交接"
summary: "记录 2026-09-01 至 2026-09-03 MapAnything 官方纯图像与 COLMAP 条件链的严格复刻、用户肉眼失败结论、全部关键哈希和本地/5090 断点。"
keywords: ["PocketWorld", "MapAnything", "Apache", "ghosting", "dense-point-cloud", "COLMAP", "CasDiffMVS", "RTX-5090"]
cwd: "/Users/kaidongwang/Documents/progecttwo"
resume_focus: "只基于官方或权威开源实现继续定位并消除 MapAnything 132 帧真彩稠密点云的重影/放射漂移，不降低 2000–3000 万点完整度。"
repository: "pocketworld"
repo_root_sha: "72f624e68324e2ee4bcbb5ce41b3fc633a3eee62"
branch: "codex/colmap-vulkan-dense-20260826"
head: "35c3046d9e661fbe6e828128e6064566227e6836"
worktree_path: "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/colmap-vulkan-dense-20260826"
---

# 接手提示：先读，不要自动跑

你正在接手 PocketWorld 的 MapAnything Apache 真彩稠密点云重影问题。
本文件是 2026-09-03 的耐久事实快照和继续工作提示词。它补充而不替代代码、
冻结输入、哈希、OpenSpec 和原始日志。

读完本文件后不要自动启动训练、全量推理、下载、手机安装或生产 App 更新。
先用只读命令验证当前文件和远端是否仍存在，向用户复述断点；只有当前用户明确
要求继续后才执行下一步。

事实优先级如下：

1. 冻结的上游源码、checkpoint、输入与产物哈希；
2. 运行日志、OpenSpec、代码和可重复命令；
3. 用户对具体网页的肉眼质量判决；
4. 本交接的归纳；
5. 聊天记忆和未经验证的推测。

用户明确规定：重影、双层和放射漂移是否消失，只能由用户肉眼验收。数值指标只
用于定位，不能替代用户的最终判断。

# 一、现在的结论，先说清楚

## 1. 最新两版都失败

2026-09-03 连续完成了两条严格官方 MapAnything Apache 链：

1. 生产级 COLMAP 相机条件版：24,681,123 点；用户看到非常严重的放射状/扇形
   漂移，判定失败。
2. 纯图像、恢复真实采集顺序版：24,376,233 点；没有向模型提供任何 COLMAP
   内参、位姿或稀疏点，但用户仍看到严重结构性/放射状漂移，判定失败。

所以，已经排除一个过度简化的解释：

> 放射漂移不可能只由“外部 COLMAP 位姿输入错误”造成，因为完全不输入 COLMAP
> 的官方纯图像链也会出现。

同样，恢复采集顺序没有带来质变。该实验不能继续包装成改进。

## 2. 为什么纯图像仍会漂移：已证事实与推论边界

没有输入 COLMAP 并不等于没有相机或位姿。官方纯图像脚本内部执行的是：

```text
132 张图像
→ MapAnything 同时预测每帧 depth_z / intrinsics / camera_poses
→ depthmap_to_world_frame 逐帧反投影到世界坐标
→ 对每一帧单独创建一个 mesh
→ 132 个独立 mesh 放进同一个 GLB scene
```

上游源码证据位于远端冻结仓库：

```text
/root/map-anything-official-exact-src-20260902/scripts/demo_images_only_inference.py
```

关键行：

- 172–180：官方 `model.infer`，`memory_efficient_inference=True`、
  `minibatch_size=1`、bf16 AMP、官方 mask 与 edge mask；
- 200–209：从每帧输出读取 `depth_z`、`intrinsics`、`camera_poses`，再调用
  `depthmap_to_world_frame`；
- 250–263：堆叠各帧 world points 后调用
  `predictions_to_glb(predictions, as_mesh=True)`。

导出器证据位于：

```text
/root/map-anything-official-exact-src-20260902/mapanything/utils/viz.py
```

关键行：

- 221–254：`as_mesh=True` 时明确循环每一帧，为每帧分别创建并加入一个
  `Trimesh`；
- 255–260：`as_mesh=False` 也只是把 mask 后的顶点放进一个 point cloud；
- 这段官方导出代码没有跨视图焊接、深度一致性融合、全局 BA、StereoFusion、
  TSDF 或“把 132 份观测收缩成唯一表面”的步骤。

由此可以确认：当前网页展示的是官方 raw per-view geometry 的集合，不是经过
多视图融合的唯一稠密表面。

可以合理推断但尚未证明的机制是：内部预测的 K、相机姿态或每像素深度只要存在
细小跨视图差异，同一真实表面就会被反投影为多层；深度错误沿相机光线展开时，
视觉上会形成扇形或放射溅射。

尚未证明的事项：

- 不能断言首先出错的一定是 K；
- 不能断言首先出错的一定是位姿；
- 不能断言首先出错的一定是深度；
- 不能断言只是网页相机角度造成；
- 不能断言 MapAnything 模型本身无法处理 132 帧；
- 不能把未经验证的自制 fusion/filter 当成根因修复。

下一阶段的任务正是用官方输出字段和重投影误差逐层定位：输入像素 → 预处理后的
像素/K → 模型预测 K/pose → `depth_z` → world points → GLB node transform。

## 3. 一个需要纠正的术语

2026-09-03 的“生产级 COLMAP 稀疏模型官方链”确实读取了
`cameras.bin / images.bin / points3D.bin`，但官方脚本只把 COLMAP 的 K 和
cam2world pose 放进 MapAnything 输入；`points3D.bin` 主要用于加载/报告，官方
推理调用明确设 `ignore_depth_inputs=True`，没有把 292,364 个稀疏点直接当作
稠密深度输入。

因此该失败版更准确的名字是“生产级 COLMAP K/位姿条件版”，不是“把稀疏点喂给
模型后的版本”。用户已经否决这条条件输入路线，后续不要再用含糊命名误导。

# 二、用户的目标和不可协商约束

以下是用户反复明确的要求，不是交接作者自行推断：

1. 最终要得到真彩稠密 PLY；用户肉眼看起来应接近真实物体。
2. 当前房间 132 帧必须维持约 2,000–3,000 万点；几十万、几百万或 1,000 多万
   都不能替代用户要的密度/完整度。
3. 唯一质量目标是：没有可见重影、双层表面、放射漂移，同时保持场景完整度。
4. 不允许通过降分辨率、降采样、裁切、减少帧数、严格筛掉大量正确点或把点数
   做小来伪装“干净”。
5. 不自研算法；优先完整复刻官方代码、官方 demo、维护者建议或权威学术团队的
   可商用开源实践。
6. 每个变更必须说明来源。没有官方/权威来源的灵光一现不能进入主线。
7. Apache 2.0 的 `facebook/map-anything-apache` 是当前 MapAnything 唯一允许的
   checkpoint；不能悄悄换成非商业权重。
8. 当前先把原生质量做好，不做 Sim(3) 世界坐标适配，不与其他电影/模型并排。
9. 用户不接受把 24 帧重叠窗口说成官方标准方案；若仅作诊断必须明确标注。
10. 用户不接受 confidence mask 后场景残缺的版本，也不接受 CasDiff 严格过滤后
    只剩约 626 万点的版本。
11. 5090 可用于远端研究推理，但最终产品路线不能依赖 NVIDIA 服务端。
12. Mac 只有 18GB 统一内存；重计算放远端，Mac 只保存/流式显示必要产物。
13. 不允许同时打开多个 2,400 万点网页导致浏览器 + Codex 把内存撑爆。
14. 生产 iPhone 包 `com.kyle.PocketWorld` 和 App Data Container 是不可替代数据；
    绝不能卸载、重装或用 `flutter drive` 破坏。
15. 当前交接任务没有授权任何手机安装、签名、生产 App 更新或数据变更。

# 三、冻结的官方身份

## 1. MapAnything 上游和脚本

远端干净上游：

```text
/root/map-anything-official-exact-src-20260902
```

冻结 commit：

```text
3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9
```

官方纯图像入口：

```text
scripts/demo_images_only_inference.py
SHA256 711662db9c95775fbf79e4884ac6d3d9113c93828c66d2bbb3186168b7e134e0
```

官方 COLMAP 入口：

```text
scripts/demo_inference_on_colmap_outputs.py
```

已审计的当前 main 与 v1.1.3 在本任务相关脚本/核心文件上哈希一致；不要因为
文件名不同就假设存在一个尚未复制的“隐藏新版算法”。仍需在远端复核 git 状态后
才能运行。

## 2. Apache checkpoint

模型：

```text
facebook/map-anything-apache
```

远端 snapshot：

```text
/workspace/.hf_home/hub/models--facebook--map-anything-apache/snapshots/00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a
```

revision：

```text
00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a
```

`model.safetensors` SHA256：

```text
fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201
```

## 3. 132 帧输入

官方 exact 2000x1500/upright 输入：

```text
/root/imgs132_up
132 files
ordered manifest SHA256 f21362f7d4ca445a1ac6900bbe98b96d8be530dc4ed45a0cb5b031787639cec8
```

冻结的 4032x3024 原始 JPEG：

```text
/root/repro_highest_20260901/frozen132/images
132 files
historical manifest SHA256 657c7357f8f63ca1d519d972090fe11d77e2c2078b77f5c0b3d41ce3bfab641f
```

原始 archive 的 `00000000.jpg ... 00000131.jpg` 文件名不是采集顺序。内容匹配到
`frame_000000.jpg ... frame_000131.jpg` 的映射已持久化于：

```text
openspec/changes/reproduce-mapanything-images-only-capture-order/capture_order_source_to_frame.json
remote-copy SHA256 59009ec833d51867818ce61993c9a3e7e0823bdfba12a6043ef7b098947a6194
```

映射证据：132 个唯一匹配；最小最佳相关系数 `0.9999771714`；最大第二名相关
系数 `0.9039216638`；最小 best-minus-second-best gap `0.0960682631`。

重要实验设计更正：最新 capture-order 版相对 2000x1500 exact baseline 同时改变了
输入来源/分辨率与顺序，因此它是严格官方纯图像候选，却不是只隔离“顺序”的
单变量因果实验。这个偏差已经写回 OpenSpec；不要再声称它单独证明顺序无效。

## 4. 生产级 COLMAP 模型身份

本地保存的真实 COLMAP 二进制模型：

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/gto_dense_20260818/work_GT16k/sparse/0
```

状态：132/132 注册、132 个 PINHOLE cameras、292,364 sparse points、
4032x3024 camera dimensions。

哈希：

```text
cameras.bin  2d611390149942e07bb5292d1166c19c8673c173eac964e19e8774f1b8e0ce1c
images.bin   d6b5f85af3db25dac8283e5fad0bbd24180ad7a30daa217beee86399d7d3816e
points3D.bin ef41835e5ccd20ebcc629c73276fe6e25a055fcf8bd3033f37954897cae1012d
```

该模型本身不是失败产物；用户的生产稀疏点云质量很好。失败的是 MapAnything 使用
这组 K/pose 条件后的稠密预测。

# 四、2026-09-01 至 2026-09-03 最近实验账本

下表中的“用户判决”优先于作者的数值猜测。`M` 表示百万顶点/点。

| 版本 | 实际变量 | 点数 | 结果/用户判决 | 关键产物 |
|---|---|---:|---|---|
| B 转正输入・demo 默认参数 | 历史 B；约 25.15M | 25.15M | 完整、细节好，但仍有轻微重影 | 本地历史 A/B 页面 |
| C 转正输入・官方全参 | 历史 C；约 23.33M | 23.33M | 与 B 肉眼接近，仍有轻微重影 | 同上 |
| 历史最后独立版 | 132 帧、COLMAP K/pose、官方 MV confidence/mask | 22.656M | 场景完整度明显下降；放射/重影仍在 | `mapanything_final_exact` |
| 官方 image-only exact | `/root/imgs132_up`，官方原脚本 | 25.123M | 比条件版稳定，但用户仍见轻微重影 | GLB SHA `678e9bbf...f46cc` |
| 官方 COLMAP native | 临时 COLMAP K/pose | 24.700M | 放射漂移/结构破坏 | `mapanything_official_colmap_native_20260901` |
| 官方 upright COLMAP | 像素/K/pose 同步转正 | 25.168M | 没有消除重影 | GLB SHA `6d9b23dd...ba6f` |
| 输入 pose lock | 锁定相对 pose 的诊断 | 25.168M | 与上一版几乎相同，重影未解 | GLB SHA `1384d985...ac50` |
| COLMAP K only | 只保留外部 K | 25.168M | 没有质变 | GLB SHA `f917bbdd...50f8` |
| COLMAP pose only | 只保留外部 pose | 25.155M | 没有质变 | GLB SHA `de33ff6b...cac3` |
| COLMAP undistorted | 官方 COLMAP 去畸变后条件链 | 25.183M | 仍有细微多层 | GLB SHA `cf34463a...a1c0` |
| image-only undistorted | 去畸变图像但不喂 K/pose | 25.144M | 用户认为轻微正收益但无质变 | GLB SHA `3bb84c3d...52d2b` |
| 官方 raw `pred[pts3d]` | 跳过再次深度反投影的诊断 | 25.168M | 与对应版几乎完全一样 | 页面截图/历史页面 |
| MapAnything → COLMAP StereoFusion bridge | 用官方 StereoFusion 收缩表面 | 0.509M | 数量完全不合格，且仍有轻微重影 | POSITION SHA `efd8289b...9e99` |
| 官方 multiview confidence | 132 帧一次性 + 官方 confidence mask | 22.656M | 清晰度接近，但完整度显著更差 | `mapanything_mvconf` 历史页 |
| MapAnything + CasDiff 严格融合 | >=3 views / <1 px / <1% depth error | 6.260M | 重影少，但场景被删得过残缺 | `mapanything_casdiff_fusion` 历史页 |
| 生产级 COLMAP K/pose 条件版 | 292,364 稀疏点模型的 K/pose | 24.681M | 严重放射/扇形漂移；失败 | GLB SHA `9bb37725...deda` |
| 纯图像真实采集顺序版 | 4032x3024 原图、恢复顺序、无相机输入 | 24.376M | 仍有严重结构性/放射漂移；失败 | GLB SHA `bf6cc8fa...312e` |

## 1. 官方 image-only exact 基线

远端：

```text
/root/mapanything_official_demo_images_only_exact_20260902
/root/mapanything_official_demo_images_only_exact_20260902/official_images_only.glb
/root/mapanything_official_demo_images_only_exact_20260902/run.log
```

运行：40.52 秒；peak host RSS 10,407,816 KiB；25,123,136 GLB vertices；
零降采样。

哈希：

```text
GLB      678e9bbf39cf040e6b981a6d9e0bf6428b3570114db19c1a1824afbf1d2f46cc
POSITION c567fc3039fbad718bc224984b58746aabbf85c168d3c2ede8b2c82af5850753
```

用户判决：比很多条件版更自然，但仍有轻微重影；不是最终通过版。

## 2. 官方 Gradio runtime 诊断

OpenSpec：

```text
openspec/changes/reproduce-mapanything-apache-gradio-runtime/proposal.md
```

目标是只把 dense head 从 CLI 的 `memory_efficient_inference=True` 切到官方
Gradio 的 `False`，判断执行路径是否改变几何。132 帧一次性 OOM，未生成可供用户
验收的完整候选。4 帧批处理诊断的 99% 几何差异约 `0.0019`，不足以解释当前
全局扇形爆炸。不要把它说成已成功的 132 帧版本，也不要重复 OOM 后偷偷改帧数。

## 3. 生产级 COLMAP K/pose 条件版（失败但证据完整）

远端根目录：

```text
/root/mapanything_apache_production_sparse_colmap_20260903
```

官方命令：

```text
HF_HOME=/workspace/.hf_home PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
/usr/bin/time -v /venv/main/bin/python \
scripts/demo_inference_on_colmap_outputs.py \
  --colmap_path /root/mapanything_apache_production_sparse_colmap_20260903/input \
  --apache --save_glb \
  --output_directory /root/mapanything_apache_production_sparse_colmap_20260903/output \
  --headless
```

运行：54.75 秒；peak host RSS 13,322,752 KiB；no swap。

产物：

```text
/root/mapanything_apache_production_sparse_colmap_20260903/output/output_mapanything_colmap_output.glb
size 973,265,300 bytes
SHA256 9bb377251d9dba48af06a4a22f8893c6dccdb86c2ac195d82bd2dba4e286deda
```

机械拆分：24,681,123 vertices。

```text
POSITION 35c7f4f239aa61a1d2dcaea777683e48bfd0209d4bc5eca6ec8dd4ab76665938
RGB      87c54249d3bd64e07cb8cacfaa4f18f5ccd52ccd31b6b9a1b0f87b3d9fd99746
```

用户判决：严重放射漂移，失败。停止作为主线。

## 4. 纯图像真实采集顺序版（最新失败版）

OpenSpec：

```text
openspec/changes/reproduce-mapanything-images-only-capture-order/proposal.md
openspec/changes/reproduce-mapanything-images-only-capture-order/specs/mapanything-reproduction/spec.md
```

`openspec validate reproduce-mapanything-images-only-capture-order --strict`
已通过。OpenSpec 已记录“同时改变原图来源/分辨率和顺序”的实验偏差与用户失败判决。

远端根目录：

```text
/root/mapanything_apache_images_only_capture_order_20260903
```

官方命令：

```text
HF_HOME=/workspace/.hf_home PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
/usr/bin/time -v /venv/main/bin/python \
scripts/demo_images_only_inference.py \
  --image_folder /root/mapanything_apache_images_only_capture_order_20260903/input_images \
  --apache --save_glb \
  --output_path /root/mapanything_apache_images_only_capture_order_20260903/output/official_images_only_capture_order.glb \
  --headless
```

运行：49.17 秒；peak host RSS 10,408,640 KiB；no swap。

产物：

```text
/root/mapanything_apache_images_only_capture_order_20260903/output/official_images_only_capture_order.glb
size 960,680,176 bytes
SHA256 bf6cc8fa6b43d65180e8dfe29749103ec798abfe7d92ae3236ed93e6a4db312e
```

机械拆分：24,376,233 vertices；零降采样。

```text
POSITION 275a8401b71541d5663b83a3b17e2c75ebfbf48b2e8ce4a7a64acc853edd30be
RGB      393a7444e9b039020ca9e95336d222f71d13332b2c8b280509fb1faaadf2e980
```

用户判决：即使完全没有 COLMAP 输入，仍有严重结构性/放射漂移；失败。

# 五、早期路线和已经得到的结论

更早的全量细节见：

```text
HANDOFF_DENSE_RECONSTRUCTION_2026-08-29.md
SHA256 dd661d6d2e0ec85136ccc03938d8b33f467cf36e0dd21c2d8174c51335c47337

HANDOFF_DENSE_ADDENDUM_2026-08-30.md
SHA256 4f343420661df0a12d0badaa5131291db092591670e67c86b5dc1e83827ec0f9
```

不要把 08-29 文档中的旧性能数字单独使用；08-30 addendum 明确纠正了其中若干
测量和 shader/bundle 一致性问题。

其他可用于追溯“重影、位姿、全分辨率 MVS、流式内存和四条并行战线”的长期文档：

```text
FULLRES_MVS_AND_FUSECUT_RESEARCH_REPORT_2026-07-21.md
SHA256 3461de8d474186eee95a607dc807846205ff191d10e86344fd5cb7bfd2862398

HANDOFF_20260822_A_REFINED_DENSE_STREAMING.md
SHA256 83773abd58eb80865f6e62c722442a1c1999c60745077c94f9254c9773cfb74a

HANDOFF_20260820_pose_quality_research.md
SHA256 91d83cbc7826274eb083be8f62ab9939bd4f9ad1ef003e24483604f526208380

HANDOFF_ghost_layer_and_retrain_2026-08-20.md
SHA256 4b2062d43daf432c132b68db9b33b6e1db50d612eee1014954a51d859c1186b0

HANDOFF_20260819_four_workstreams.md
SHA256 35152f76a7964f1ced1aa0a360a524ebc9f8d486fb235fbbd3161ffa403c5c87

FULLRES_MVS_AND_FUSECUT_RESEARCH_PROMPT.md
SHA256 567ac94bcd314398a49f09e3a23dd7b99f857e5d9627348edfbd3c195b46cd20
```

这些旧文档是历史证据，不覆盖本文件的最新用户判决、冻结身份或失败结论。

## A. CasDiffMVS + BlendedMVG

- 学习式多视图立体视觉；需要权重与训练数据。
- 当前商业可用历史基线名：`casdiffmvs_mvgZeroDTU.ckpt`。
- 零 DTU、纯 BlendedMVG、从头训练、32 轮。
- 优点：多视图几何稳定，几乎没有 MapAnything 这种重影。
- 缺点：低纹理白墙、天花板、亮面地板空洞更多，表面完整度和质感不如
  MapAnything。
- 用户的目标不是简单回退到 CasDiffMVS，而是保留 MapAnything 的高密表面质量
  同时消除重影。

## B. CasDiffMVS + BlendedMVG/TartanGround

- 在 RTX 5090 完成 10 轮 50/50 短程混合微调：每轮 1,774 TG + 1,774 MVG，
  887 steps/epoch，共 8,870 steps。
- 局部墙面洞变小，但出现新的错误连接；单场景没有证明整体优于基线。
- 本地：

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/tg_epoch10_b28_20260826.nosync
```

## C. LingBot-Map / 多数据集综合权重

- 调查过约 29 套数据的综合训练路线。
- 它不是 CasDiffMVS 的可直接替换权重。
- 之前商业许可审计结论为 `insufficient evidence`，不是“确认不可商用”。
- 不要在没有冻结代码、权重、数据谱系、NOTICE 和许可前接入产品。

## D. MapAnything 早期变体

早期依次尝试：官方 Apache 权重、官方 `preprocess_inputs`、官方 COLMAP demo、
`pred["pts3d"]`、Open3D 1% IQR 体素、纯图像、K/pose 条件、原生 COLMAP
二进制、metric/nonmetric 修复、multiview confidence、CasDiff 几何过滤。

代表点数/结论：

- 原始/修复高密版约 24.69–24.76M：表面质感好，用户曾认为是 MapAnything
  历史最好一档，但仍有重影；
- 1% IQR/体素类结果约 0.865M、1.199M、1.406M：点数和完整度不合格；
- multiview confidence 约 22.656M：完整度变差；
- MapAnything + CasDiff 严格过滤约 6.260M：过度删除；
- 24 帧窗口没有被证明是官方长序列标准方案，不能冒充官方答案。

## E. GLUEMAP

调查流程包括图像检索/共视邻接、重复场景排歧义、局部 star、tracks、旋转/内参/
Sim(3) 全局平均、global BA、SIFT 与增强 BA。它主要产生全局稀疏几何与相机图，
不会自动生成用户要的 2,000–3,000 万稠密点。生产稀疏 COLMAP 已经很好，因此
没有理由只为得到另一份稀疏点云而替换它。

## F. COLMAP PatchMatch MVS → StereoFusion

- 经典优化式 MVS，不需要训练权重或训练素材；能复用生产 COLMAP 相机。
- 官方 CUDA PatchMatch + StereoFusion 是语义 oracle，但手机需要跨端后端。
- 已做过 C++ 控制层 + Vulkan shader + MoltenVK 机械移植；全量曾输出
  17,052,272 点，但有放射飞点，且没有通过完整 CUDA parity。
- 08-30 addendum 记录了批处理、geometric/photometric 性能、逐字节验证、被否决
  的优化和当前 shader/bundle 风险。
- 这条路线是另一个工程战线，不应与当前 MapAnything raw output 混成一个
  “100% 官方 MapAnything”版本。

# 六、本地文件与网页索引

## 1. 主工作区

机器本地、长期目录：

```text
/Users/kaidongwang/Documents/progecttwo
```

注意：该顶层当前不是可用的 git root；不能用一个顶层 commit 代表全部内容。很多
大产物位于 `.nosync`，未被版本控制但在本机长期保留。不要清理、移动或覆盖。

## 2. 当前 MapAnything OpenSpec

```text
openspec/changes/reproduce-mapanything-official-images-only-exact/proposal.md
openspec/changes/reproduce-mapanything-apache-gradio-runtime/proposal.md
openspec/changes/bridge-colmap-sparse-mapanything-stereofusion/proposal.md
openspec/changes/reproduce-mapanything-production-sparse-colmap/proposal.md
openspec/changes/reproduce-mapanything-images-only-capture-order/proposal.md
```

其中：

- official-images-only-exact：严格官方纯图像基线；已完成，仍轻微重影；
- apache-gradio-runtime：完整 132 帧 OOM，未出候选；
- bridge-colmap-sparse-mapanything-stereofusion：只出 509,072 点，失败；
- production-sparse-colmap：24.681M，但严重放射漂移，失败；
- images-only-capture-order：24.376M，无 COLMAP 仍严重漂移，失败。

截至交接时的结构校验状态：

- `reproduce-mapanything-images-only-capture-order`：
  `openspec validate ... --strict` 通过；
- `reproduce-mapanything-production-sparse-colmap`、
  `reproduce-mapanything-apache-gradio-runtime`、
  `reproduce-mapanything-official-images-only-exact`、
  `bridge-colmap-sparse-mapanything-stereofusion`：严格校验会因缺少 specs delta 失败。

后一组文件仍可作为实验提案/状态记录读取，但不能说成已通过完整 OpenSpec 验收。
`bridge-colmap-sparse-mapanything-stereofusion` 明确是自定义桥接诊断，不是官方
MapAnything 原样复现。

## 3. 最新两个网页目录

生产 COLMAP K/pose 条件失败版：

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/pose_ablation_20260818/verdict_page/mapanything_production_sparse_colmap_20260903
```

纯图像采集顺序失败版：

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/pose_ablation_20260818/verdict_page/mapanything_official_images_only_capture_order_20260903
```

后者本地二进制：

```text
bin/official_colmap_native.pos  292,514,796 bytes
bin/official_colmap_native.col   73,128,699 bytes
bin/meta.json
```

网页地址（必须先启动 8931 server）：

```text
http://127.0.0.1:8931/mapanything_production_sparse_colmap_20260903/
http://127.0.0.1:8931/mapanything_official_images_only_capture_order_20260903/
```

2026-09-03 交接时端口 8931 没有监听。需要查看时，在 verdict page 根目录启动：

```text
cd /Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/pose_ablation_20260818/verdict_page
python3 -m http.server 8931 --bind 127.0.0.1
```

不要同时打开多个 350–720MB 的 MapAnything 页面。切换当前标签，让旧 WebGL
buffer 释放后再加载下一版。

## 4. 全部重要 MapAnything 网页目录

根目录：

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/pose_ablation_20260818/verdict_page
```

重要子目录：

```text
mapanything_apache_first_exact
mapanything_camera_locked
mapanything_compare
mapanything_final_exact
mapanything_fixed
mapanything_imageonly_lossless_ab
mapanything_official_colmap_k_only_20260902
mapanything_official_colmap_native_20260901
mapanything_official_colmap_pose_only_20260902
mapanything_official_colmap_undistorted_20260902
mapanything_official_image_only
mapanything_official_image_only_undistorted_20260902
mapanything_official_images_only_exact_20260902
mapanything_official_known_pose
mapanything_official_native_colmap
mapanything_official_upright_colmap_20260901
mapanything_official_upright_input_pose_lock_20260902
mapanything_original
mapanything_colmap_sparse_stereofusion_full132_v1_20260902
mapanything_production_sparse_colmap_20260903
mapanything_official_images_only_capture_order_20260903
```

它们是历史诊断资产，不是都能称为官方最终结果。读取各 `index.html` 标题和
`bin/meta.json` 后再描述，不能凭目录名猜算法语义。

## 5. 早期 MapAnything 实验目录

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_camera_locked_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_knownposes_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_native_colmap_official_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_nonmetric_fixed_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_official_image_only_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_official_known_pose_20260826.nosync
```

其中几份仍保有本地真彩 PLY，可在远端失效后用于追溯：

```text
mapanything_apache_b28_20260826.nosync
  24,394,262 vertices
  PLY 365,914,112 bytes
  run.json 记录 output SHA256 f699930...2b66
  full run 106.443 s；inference 30.141 s
  input manifest 657c735...ab641f

mapanything_apache_b28_camera_locked_20260826.nosync
  24,693,184 vertices
  PLY 370,397,942 bytes
  SHA256 fdc19e...9954

mapanything_apache_b28_knownposes_20260826.nosync
  24,763,526 vertices
  PLY 371,453,072 bytes
  SHA256 9e1aad...afd28

mapanything_apache_b28_nonmetric_fixed_20260826.nosync
  24,693,184 vertices
  PLY 370,397,942 bytes
  SHA256 79d398...e49a5
```

省略号表示这里只抄录了旧 run metadata 中的可辨识前后缀；需要把某一份提升为
新基准前，必须对实际 PLY 重新执行完整 `shasum -a 256`，不能用缩写作身份。

## 6. CasDiffMVS 历史产物

这些目录解释了为何用户记得 CasDiffMVS 几何更稳，也保留了官方/FP16/FP32/
reseed 等旧对照；它们不是当前 MapAnything 的自动后处理：

```text
/Users/kaidongwang/Documents/progecttwo/_artifacts.nosync/casdiffmvs_fixture97_20260817
  约 3.4G
  C_official.ply       332,974,627 bytes
  OLD413_official.ply  885,004,222 bytes
  ORT_CPU.ply          332,973,112 bytes

/Users/kaidongwang/Documents/progecttwo/_artifacts.nosync/casdiffmvs_fp16_recon_20260819
  约 917M
  FP16_ORIG            296,522,002 bytes
  FP32_ORIG            332,974,927 bytes
  FP32_RESEED          332,448,442 bytes

/Users/kaidongwang/Documents/progecttwo/_artifacts.nosync/casdiffmvs_scratch_ply_20260817
  约 770M
  包含 A/B/C/D/OFFICIAL PLY、fixed renders 与 viewer

/Users/kaidongwang/Documents/progecttwo/_artifacts.nosync/casdiffmvs_onnx_20260818
  约 18M
  三个 ONNX 变体
```

## 7. COLMAP/Vulkan 稠密战线

工作树：

```text
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/colmap-vulkan-dense-20260826
branch codex/colmap-vulkan-dense-20260826
HEAD 35c3046d9e661fbe6e828128e6064566227e6836
```

该工作树在交接时非常脏，包含自动取帧、VIO、Flutter、iOS、Android、ABI、
OpenSpec 与 dense 模块的许多修改/未跟踪文件。严禁 reset、clean、checkout-over、
批量 revert 或把当前 HEAD 当成完整本地产物身份。

冻结输入：

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_official2000_20260829/official_inputs
```

17.05M 全量输出：

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_xorwow_official2000_run_20260829/DenseProbeFrozenB28_full_scene
```

# 七、当前 5090 远端状态

## 1. 连接身份

截至 2026-09-03 12:57 中国时间附近，Vast 实例可连接：

```text
ssh -p 62030 root@171.227.33.18
hostname 8f8a34f09bed
GPU NVIDIA GeForce RTX 5090, 32607 MiB
```

不在本文保存任何私钥、口令或完整 SSH 公钥。连接端点是临时基础设施，可能随
实例释放而失效；不能把远端当唯一耐久存档。

每次新会话连接后，先完整阅读远端：

```text
/etc/vast-agents-guide.md
```

交接时：GPU memory used 0 MiB；没有 `demo_images_only`、
`demo_inference_on_colmap` 或 scp 进程；overlay 1.0T，使用约 50G，空闲约 975G。

## 2. 远端重要目录

```text
/root/map-anything-official-exact-src-20260902                    12M
/root/mapanything_official_demo_images_only_exact_20260902       1.3G
/root/mapanything_official_colmap_undistorted_20260902           1.9G
/root/mapanything_apache_production_sparse_colmap_20260903       1.4G
/root/mapanything_apache_images_only_capture_order_20260903      1.3G
/root/repro_highest_20260901                                     610M
/root/repro_official_colmap_native_20260901                      2.7G
/root/mapanything_official_upright_colmap_20260901               2.1G
/root/mapanything_official_colmap_k_only_20260902                1.3G
/root/mapanything_official_colmap_pose_only_20260902             1.3G
/root/mapanything_official_image_only_undistorted_20260902       1.3G
/root/mapanything_colmap_sparse_stereofusion_full132_v1_20260902 511M
```

远端还保存多组 `mapanything_geometry_boundary_audit_*` 小型诊断目录和 local-star
实验。不要清理；失败实验同样是证据。

## 3. 历史最好候选

历史自定义高密 PLY：

```text
/root/repro_highest_20260901/output/mapanything_highest_repro_truecolor.ply
24,693,184 points
historical runtime about 49.999 seconds
```

这版没有 fusion、multiview confidence 或 camera lock。用户历史上认为它是
MapAnything 较好的一版，但“历史最好”只能由用户重新肉眼确认，不能由文件名
或点数自动判定。

# 八、官方和社区证据账本

以下链接是公开、可重新验证的入口。接手者必须查看原始页面/源码，不要只引用
本交接摘要。

| 状态 | 事实 | 入口 | 限制 |
|---|---|---|---|
| confirmed | MapAnything 官方仓库与 demos | https://github.com/facebookresearch/map-anything | 当前远端冻结 commit 必须与公开页区分 |
| confirmed | Apache checkpoint 页面 | https://huggingface.co/facebook/map-anything-apache | 模型文件按上文 revision/hash 冻结 |
| supported | 官方维护者讨论 100–1000 views、输出 predicted poses、COLMAP non-metric/pose scale 处理 | https://github.com/facebookresearch/map-anything/issues/9 | 讨论不是对任意真实场景零重影的保证 |
| supported | 外部 pose scale 不匹配可产生附近重复表面；维护者建议忽略 pose 输入作诊断 | https://github.com/facebookresearch/map-anything/issues/93 | 解释外部 pose 条件版，不足以解释最新纯图像失败 |
| supported | 模型输入最长边约 518，预处理需要同步转换 K；盲目高分辨率可能恶化 calibration/rays | https://github.com/facebookresearch/map-anything/issues/38 | 需结合当前 commit 源码验证，不可只凭评论调参 |

已经确认的官方语义：

- 纯图像 demo 会预测 K/pose/depth；
- COLMAP demo 只在输入阶段使用外部 K/pose，`points3D.bin` 不成为 dense depth；
- COLMAP 被标为 non-metric，官方推理设置 `ignore_pose_scale_inputs=True`；
- 官方纯图像 GLB exporter 逐帧创建独立 mesh，不做 fusion/welding；
- `use_multiview_confidence` 主要影响 confidence/mask，不会自动把多层表面移动为
  唯一几何；
- raw GLB 顶点多并不等于已经得到全局一致的融合表面。

# 九、不要再重复的错误路线

1. 不要再把输入 COLMAP K/pose 当成必然改善；生产级模型条件版已经严重失败。
2. 不要再宣称只要不用 COLMAP 就一定没有放射；最新纯图像版已经否证。
3. 不要再把 `points3D.bin` 描述成已喂给 MapAnything dense head。
4. 不要再锁一个手调焦距百分比、K 缩放或 Sim(3) 后直接全量跑；先找官方依据。
5. 不要把每帧 raw world-points 的简单拼接称为多视图融合。
6. 不要用 1% IQR、体素、严苛 confidence、CasDiff hard gate 把正确点删掉后称为
   修复；点数/完整度已经多次失败。
7. 不要把 24 帧窗口说成官方标准长序列方案。
8. 不要重复 132 帧 Gradio dense-head OOM 后悄悄减少帧数并称同一结果。
9. 不要重新下载 checkpoint 或换模型 revision，除非用户授权新对照并冻结身份。
10. 不要在 Mac 上解码多个 1GB GLB 或并排开多个全量点页面。
11. 不要用 CUDA 质量作为手机产品已完成的证明；远端只负责研究/冻结 oracle。
12. 不要动生产 iPhone；本任务没有设备安装授权。
13. 不要删除失败产物；它们证明哪些假设已经失败。
14. 不要用“点数更多”“哈希不同”或数值代理自动选赢家；用户肉眼才是质量门。

# 十、未解决的真正问题

当前不是“继续随便调一个参数”，而是要回答三个严格问题：

## 问题 A：官方 raw demo 是不是被误当成最终融合产品？

源码已证明 raw image-only GLB 是 132 个独立 mesh 的 scene。需要联网查明官方论文、
supplementary、README、demo、maintainer issue 或权威使用者是否另有推荐的
cross-view fusion / consistency / reconstruction consumer。若存在，必须原样复刻；
若不存在，不能假装 raw demo 本来就保证唯一表面。

## 问题 B：哪一层第一次破坏几何一致性？

必须逐层保留并比较：

```text
原始 JPEG 像素与文件顺序
→ load_images/preprocess_inputs 后的 img_no_norm、shape、K 变换
→ 预测 intrinsics
→ 预测 camera_poses
→ 预测 depth_z
→ 官方 pred[pts3d]（若当前输出包含）
→ depthmap_to_world_frame 重算 points
→ GLB accessor + node matrix
→ 网页 model/mvp
```

每层要用同一组冻结输入、同一 checkpoint、同一 commit。重投影误差、相机中心轨迹、
相邻帧表面距离、正反向 depth consistency 可用于定位第一次突变，但不能替代用户
最终验收。

## 问题 C：为什么 2000x1500 exact baseline 比 4032x3024 capture-order 版肉眼更稳？

最新实验同时改变了 source pixel identity/resolution 与顺序，因此要补一个真正的
二乘二诊断，而不是继续猜：

```text
A: 2000x1500，既有 frame 顺序（已完成）
B: 2000x1500，重新映射顺序（如果原本已是 frame 顺序，应证明 B=A 并跳过）
C: 4032x3024，archive 数字顺序（历史 run 可复核）
D: 4032x3024，恢复 frame 顺序（最新失败版）
```

先哈希并证明 A/B 是否其实相同，再决定是否值得重新推理。不要为了填表重复相同
输入。

# 十一、推荐的后续推进方向

这些是顺序相关的工作，不是互斥的“随便选一个”。执行前仍需当前用户确认。

## Phase 0：保护现场并恢复可验证状态

1. 确认远端 endpoint 仍活着，阅读 `/etc/vast-agents-guide.md`。
2. 确认 GPU 空闲、磁盘足够，没有残留推理/scp。
3. 核对 upstream commit、git diff、脚本 hash、checkpoint hash、输入 manifest。
4. 不重跑最新两版；它们已有 GLB、POS/RGB、日志与用户判决。
5. 若只需查看，重启本地 8931 server，并只加载一个页面。

## Phase 1：联网找“官方最终表面链”，不是自己发明

1. 通读 MapAnything paper、supplementary、README、所有官方 demo 和 visualization
   helper，检索官方是否提供或明确推荐跨视图 fusion/point consolidation。
2. 搜官方 issues/discussions 中与 `ghosting`、`duplicate surfaces`、
   `multi-view consistency`、`reprojection`、`100 views`、`pts3d`、`fusion`、
   `COLMAP` 直接相关的维护者答复。
3. 搜权威学术团队/高质量开源产品使用 MapAnything 的完整下游链，冻结 exact
   revision、许可证、默认参数、输入输出契约。
4. 只有找到明确来源后才新增实验。不得把自制阈值或混搭命名为官方方案。

## Phase 2：用官方样例分离“环境/导出 bug”和“用户场景问题”

1. 在同一远端、同一 commit、同一 Apache checkpoint 跑官方仓库提供的最小
   multi-view sample。
2. 用官方 viewer/GLB 与当前机械 viewer 同时验证同一产物的 node transform。
3. 若官方 sample 在机械 viewer 也爆炸，优先查 GLB accessor/node matrix/WebGL；
   若 sample 干净而 132 房间爆炸，优先查输入 regime、预测相机/深度一致性。
4. 该 sample 只能做诊断，不能替代真实 132 帧产品验收。

## Phase 3：建立每一层的几何边界审计

1. 对同一批输入保存官方输出 K、pose、depth、mask、`pts3d` 和重算 world points。
2. 先比较官方 `pred[pts3d]` 与 `depthmap_to_world_frame(depth_z,K,pose)` 的差异；
   历史 direct-pts3d 视觉上相近，但缺完整逐帧证据账本。
3. 用相邻高共视帧计算双向重投影残差与 relative-depth residual，定位异常集中在
   pose、K、depth 还是遮挡/低纹理区域。
4. 把最坏帧索引投到网页或小型诊断，不先重跑 132 帧全量。
5. 任何 metric 阈值在看最终结果前预注册；只用于诊断，不能自动批准质量。

## Phase 4：复刻找到的权威融合链

如果 Phase 1 找到官方或权威开源 fusion：

1. 冻结仓库 revision、license、依赖、默认参数和样例；
2. 只把 MapAnything 官方预测通过其规定接口传入；
3. 不改变深度、K、pose、mask 或阈值语义；
4. 保存中间 depth/normal/confidence/consistency 与最终 PLY；
5. 必须保留 20–30M 的目标完整度；若官方 fusion 本身只剩几十万点，直接判定
   不满足本产品目标，不靠点复制扩充。

如果不存在任何官方/权威融合链，应明确向用户报告这一事实，并由用户决定是否
允许采用 COLMAP StereoFusion/OpenMVS 等权威外部 consumer。不能擅自把它混入
“纯 MapAnything 官方复刻”。

## Phase 5：真实 132 帧用户验收

1. 远端只跑一个候选；记录 wall time、RSS、VRAM、hash、点数。
2. GLB/PLY 机械导出，零降采样、零筛点、零坐标改造。
3. 下载到本地前先确认空间与内存；只开一个网页标签。
4. 页面明确写出算法链和是否用了外部 K/pose/fusion。
5. 用户从地板、白墙、行李箱、镜子/高反光区、长走廊方向肉眼检查。
6. 用户没有说通过，就只能标为候选或失败，不能说“修复完成”。

# 十二、接手后的首轮只读核验命令

以下命令只用于确认现场，不代表自动执行授权。

本地：

```text
cd /Users/kaidongwang/Documents/progecttwo
openspec validate reproduce-mapanything-images-only-capture-order --strict
shasum -a 256 \
  _host_experiments.nosync/pose_ablation_20260818/verdict_page/mapanything_official_images_only_capture_order_20260903/bin/official_colmap_native.pos \
  _host_experiments.nosync/pose_ablation_20260818/verdict_page/mapanything_official_images_only_capture_order_20260903/bin/official_colmap_native.col
lsof -nP -iTCP:8931 -sTCP:LISTEN
```

预期最新 POS/RGB 哈希：

```text
275a8401b71541d5663b83a3b17e2c75ebfbf48b2e8ce4a7a64acc853edd30be
393a7444e9b039020ca9e95336d222f71d13332b2c8b280509fb1faaadf2e980
```

远端：

```text
ssh -p 62030 root@171.227.33.18
cat /etc/vast-agents-guide.md
cd /root/map-anything-official-exact-src-20260902
git rev-parse HEAD
git status --short
sha256sum scripts/demo_images_only_inference.py
nvidia-smi
ps -eo pid,etime,%cpu,%mem,cmd | grep -E '(demo_images_only|demo_inference_on_colmap|scp)'
```

# 十三、当前状态快照与连续性风险

- 最新纯图像推理：完成；用户判定失败；没有后台推理进程。
- 最新两个远端 GLB：存在并已哈希。
- 最新两个本地 WebGL binary：存在并已哈希。
- 本地 8931 server：交接时未运行；页面文件仍在。
- 5090：交接时在线且空闲，但 Vast endpoint 是临时的。
- Mac：18GB；严禁多全量页面并行加载。
- 主目录顶层：不是当前 git root；本交接虽在长期 Documents 路径，但未自动纳入
  版本控制或云端备份。
- dense worktree：大量用户和其他任务改动；绝不能清理。
- 生产手机：没有本轮操作授权，也没有被本轮实验触碰。
- “历史最好”：没有机器可靠标签，必须由用户打开候选后肉眼认定。
- 最近这些 MapAnything OpenSpec/结果目录中没有找到 DVC、MLflow 或仓库级
  `uv.lock` 运行身份。现有 manifest/hash/log 能支撑当前交接，但尚未达到项目政策
  规定的完整实验账本；下一次新实验必须在运行前补齐，而不是事后猜配置。

# 十四、给下一位 agent 的工作口径

每次汇报必须直接回答：

1. 当前在做哪个具体步骤；
2. 这一步是官方原样、权威外部复刻、诊断，还是自制适配；
3. 已完成什么、是否有产物、点数和耗时；
4. 是否卡住，卡在哪个命令/文件/阶段；
5. 当前页面能否打开；
6. 下一步为什么能缩小根因，而不是又生成一个几乎相同版本；
7. 哪些结论已被用户肉眼否决；
8. 未证明的推断必须明确写“未证明”。

超过一分钟的工作要给简短、可核实进度。不要半小时只说“还在查”。下载无输出时
检查实际文件大小/进程，不要启动第二次重复下载。失败要直接说失败。

# 十五、接手确认模板

在用户明确要求继续时，先用简短中文确认以下断点，不要直接发散：

```text
我已接住断点：外部 COLMAP K/pose 条件版 24,681,123 点出现严重放射漂移；
完全纯图像的官方版 24,376,233 点仍然出现，所以根因不只在外部 COLMAP。
官方纯图像 demo 会自行预测 K/pose/depth，并把 132 帧分别导出为独立 mesh，
当前 raw GLB 没有跨视图融合。下一步先查官方/权威的最终融合使用链，并用官方
样例与逐层重投影审计定位第一次几何失真；不再盲调 K、Sim(3) 或过滤阈值，
不重跑已有失败版，不动生产 iPhone，也不让 18GB Mac 同时加载多个全量页面。
```

只有当前用户明确确认继续，才从 Phase 0 开始。
