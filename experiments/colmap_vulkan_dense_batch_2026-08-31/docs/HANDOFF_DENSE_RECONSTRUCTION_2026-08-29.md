# 交接提示词：PocketWorld 稠密点云路线全量交接（2026-08-25 ～ 2026-08-29）

> 使用方法：把本文件从“你是接手者”开始完整交给下一位 agent。它是当前工作的事实快照、约束清单、实验历史和续作入口。任何聊天记忆若与代码、测试、冻结清单、产物哈希冲突，以后者为准。

---

## 你是接手者

你的任务不是重新发散调研，也不是重新发明一套稠密重建算法。你的任务是接手 PocketWorld 的“手机本地、跨端、真彩稠密点云”工程，在严格保护用户生产 App 和已有数据的前提下，继续复刻经过验证的官方算法，并最终得到用户肉眼认可的真彩 PLY。

当前工作已经按用户要求暂停。不要在阅读本交接后自动启动全量重建、训练、远端 5090、手机安装或生产 App 更新。先核对状态，再向用户报告你理解的断点；只有用户明确要求继续后，才执行后续实验。

---

# 一、唯一目标与最终验收标准

## 1. 产品目标

最终要在 PocketWorld 手机 App 本地完成：

1. 复用现有 COLMAP 稀疏重建结果；
2. 继续执行高质量稠密重建；
3. 输出真彩、稠密、几何稳定的 PLY；
4. 未来以同一套 C++ 控制层、同一套 Vulkan Compute/SPIR-V shader、同一组参数和输出格式覆盖 iOS、Android、鸿蒙；
5. Apple 端可通过 MoltenVK 承载 Vulkan，但算法主体不能变成 Apple 专属实现；
6. 新增稠密模块不依赖 Swift 算法代码。极薄的系统宿主层可按平台存在，但不能维护三套算法。

## 2. 当前阶段目标

当前先在 Mac 上把官方级稠密点云质量完整显现出来，再谈手机部署和速度。用户随后增加了硬速度门槛：

- 同一组 132 帧真实场景；
- 全分辨率 2000×1500；
- 10 个官方选出的 source views；
- 官方 PatchMatch 参数、顺序、默认值和 StereoFusion；
- 真彩 PLY；
- Mac M3 Pro、18GB 统一内存；
- 全流程最好不超过 30 分钟；
- 不能用降低分辨率、减少视图、减少样本、减少迭代、关闭几何一致性等方式“提速”；
- 用户希望点数达到数千万级，并且没有明显放射状飞点、重影、双层表面；
- 用户肉眼观察网页中的真彩 PLY 是最终产品判断。

这个 30 分钟目标目前没有实现，也不能承诺一定可实现。必须先证明现有 Vulkan 端仍有数量级的移植低效；如果机械、无损优化后仍无法达到，应诚实报告硬件与目标的冲突，不能伪造结果或偷偷降质。

## 3. 方法边界

用户反复强调：

- 不要自研算法；
- 不要凭感觉混搭；
- 不明白就先查官方代码、官方文档、维护者提交、权威学术实现；
- 能机械复刻就机械复刻；
- 所有改动必须说明它来自哪个官方实现或维护者证据；
- 不能把自制适配版说成“100% 官方”；
- 任何降质换速度的参数都必须拒绝；
- 不需要在此阶段为了与旧模型并排展示而做 Sim(3)、TSDF 或世界坐标适配；先看算法原生输出；
- 不要用 CUDA 作为产品路线。CUDA 可以作为官方语义参考或冻结 oracle，但当前用户要求 Mac/Vulkan 肉眼验收，不希望再花时间跑一个不能上手机的 CUDA 产品版本。

---

# 二、最高优先级安全规则

## 1. 生产 iPhone 和 App 数据绝对不能破坏

生产包：`com.kyle.PocketWorld`

绝对禁止：

- 卸载、重装、删除或替换生产包作为测试捷径；
- 对生产包执行 `flutter drive`；
- 未经用户当次明确授权就安装、签名、启动测试或更新生产 App；
- 用历史 Runner.app、旧 commit、旧 Dart AOT 或不完整快照承载新 native 模块；
- 把保留 App Data Container 误当成“应用代码也未被替换”；
- 任何会让用户重新登录或丢失本地项目的操作。

如未来需要生产 App 原位更新，必须遵循仓库 `AGENTS.md` 的完整备份、哈希验证、同源 control/candidate、字节一致 Dart AOT、签名与 `devicectl device install app` 流程。当前用户已要求暂停，所以不要动手机。

## 2. 18GB 内存上限

Mac 是 Apple M3 Pro，18GB 统一内存。当前单个 reference 的资源规划约 3.31GB。禁止同时启动多个完整 reference workspace、禁止无门槛跑 132 帧全量、禁止让浏览器同时加载多个超大 PLY 导致内存爆炸。

## 3. 脏工作树保护

当前工作树包含大量与稠密模块无关的用户/其他任务改动。绝对不要：

- `git reset --hard`
- `git clean`
- `git checkout --` 覆盖用户改动
- 批量 revert
- 为了“干净”而丢弃未跟踪文件

只允许在明确的稠密模块范围内做最小改动。先冻结内容清单；如需隔离，复制完整本地产品树或使用经过核对的独立工作树，不要假设 commit 能代表当前产品。

---

# 三、项目、仓库、版本和硬件身份

## 1. 当前稠密工作树

```text
/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/colmap-vulkan-dense-20260826
```

分支：

```text
codex/colmap-vulkan-dense-20260826
```

当前 HEAD：

```text
35c3046d9e661fbe6e828128e6064566227e6836
```

## 2. 主项目目录

```text
/Users/kaidongwang/Documents/progecttwo
```

## 3. 上游 COLMAP 冻结版本

```text
a0d785fba74b2664f31edc4a29026a8b27c00f67
```

对应 COLMAP 4.1.1。续作前必须再次从 manifest、vendor source 或脚本核对，不能只相信本提示词。

## 4. 当前构建目录

```text
/Users/kaidongwang/.codex/builds/pw-dense-xorwow-2000-20260829
```

## 5. 冻结输入

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_official2000_20260829/official_inputs
```

这是 132 帧真实场景及相机/稀疏几何的冻结输入入口。不要重新排序、重新抽帧或替换图像后仍称同一实验。

## 6. 已有 COLMAP/Vulkan 全量输出

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_xorwow_official2000_run_20260829/DenseProbeFrozenB28_full_scene
```

该批次最终融合点云约 17,052,272 点，已通过网页展示，但存在放射状飞点，用户认为点数仍明显不足。

## 7. 本地网页

已展示过的当前 COLMAP/Vulkan 页面：

```text
http://127.0.0.1:8931/colmap_vulkan_official_fused/
```

暂停时未发现重建/训练进程；只看到一个长期运行的本地 `python -m http.server`，端口是 8642。不要因为端口不同就擅自杀掉，先确认它是否仍为用户查看产物所需。

---

# 四、整个算法路线的演变和每条路线的结论

## A. CasDiffMVS + BlendedMVG：原始商业可用基线

### A1. 算法类型

CasDiffMVS 是学习式多视图立体视觉模型。它需要训练权重；训练素材决定泛化能力。它与 COLMAP PatchMatch MVS 不同：前者通过神经网络预测深度/概率体，后者是经典 PatchMatch 优化，不需要学习权重。

### A2. 为什么没有继续使用 DTU

DTU 的商用许可不满足当前产品需求，所以没有把 DTU 作为最终商用训练素材。团队此前已经从零训练完成纯 BlendedMVG 权重。

### A3. 当前基线权重

历史名称：

```text
casdiffmvs_mvgZeroDTU.ckpt
```

它是：

- 零 DTU；
- 纯 BlendedMVG；
- 从头训练；
- 32 轮；
- 完成日期约 2026-08-23。

### A4. 早期 ETH3D 指标

原始交接记录的办公室场景 F1：

| 权重 | F1@1cm | F1@2cm | F1@5cm | F1@10cm |
|---|---:|---:|---:|---:|
| 官方/历史 blendmvg | 0.4378 | 0.5366 | 0.6251 | 0.6910 |
| 旧 C 配置 | 0.3679 | 0.4699 | 0.5760 | 0.6464 |
| 新 mvgZeroDTU | 0.4300 | 0.5338 | 0.6287 | 0.6995 |

白墙 completeness：

| 权重 | @1cm | @2cm | @5cm |
|---|---:|---:|---:|
| blendmvg | 0.1942 | 0.2410 | 0.3034 |
| C | 0.1745 | 0.2230 | 0.2911 |
| mvgZeroDTU | 0.2089 | 0.2527 | 0.3081 |

当时 MPS 评测有约 2 个百分点非确定性噪声，因此小变化不能被夸大。

### A5. 结论

纯 BlendedMVG 基线总体几何稳定、几乎没有 MapAnything 那种重影，但白墙、天花板、亮面地板等低纹理区域空洞较多。用户的目标是提高墙面完整度，而不是只追求有纹理物体精度。

---

## B. CasDiffMVS + BlendedMVG/TartanGround：白墙微调试验

### B1. 为什么引入 TG

TartanGround（对话中简称 TG）含大量低纹理墙面/室内素材，许可记录为 CC BY 4.0。初始想法是用 TG 补白墙完整性，同时用 BlendedMVG 防止模型遗忘普通场景。

### B2. 最终实际执行方案

用户认可的“第一枪”不是 4 轮，而是 10 轮短程混合微调：

- 每轮 1,774 条 TG；
- 每轮 1,774 条 BlendedMVG；
- BlendedMVG 每轮轮换子集；
- 总清单 3,548 条；
- batch=4；
- 官方 shuffle；
- 887 step/epoch；
- 10 epochs；
- 总计 8,870 steps；
- 不自定义“每批固定 2+2”的 batch sampler，不改官方数据管线。

### B3. 训练结果

10 轮训练已经在 RTX 5090 上完成。随后使用与 BlendedMVG 基线完全相同的真实 132 帧 b28 场景运行，导出了真彩稠密 PLY，并做了 TSDF 清理后的网页比较。

历史页面：

```text
http://127.0.0.1:8931/tsdf_tg10/
```

截图中 TSDF 后三角面统计：

- 基线 CasDiffMVS + BlendedMVG（32 轮）：22,635 面，删除 11.26%；
- 新版 BlendedMVG + TG（第 10 轮）：23,713 面，删除 12.44%。

### B4. 用户肉眼结论

- 新版在部分小墙面上保留了更多小平面；
- 一些空洞变小；
- 行李箱与墙之间的“蜘蛛网”连接有所减少；
- 但右侧出现一整块错误连接；
- 两版各有优缺点，没有证明混合版绝对更好；
- 用户担心 MVG 与 TG 梯度相互干扰或“嵌合”；
- 单场景无法判定完整 TG、50/50、多数据集混合谁最好。

### B5. 当前状态

这条 10 轮微调已完成，不需要继续占用 5090。没有进行完整纯 TG 从零重训，也没有完成几十数据集的综合重训。不要把“TG 只适合补白墙”当作已证事实；用户明确指出完整 TG 也可能整体更强。

历史实验目录：

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/tg_epoch10_b28_20260826.nosync
```

---

## C. LingBot-Map：多数据集综合权重调查

### C1. 为什么调查

LingBot-Map 被提及为用约 29 套数据按比例训练的综合模型，说明多数据集配比训练是成熟路线，单纯只用 MVG 或 MVG+TG 可能过窄。

### C2. 与 CasDiffMVS 的关系

它不是 CasDiffMVS 的一个简单权重分支，而是独立模型/系统。不能把 LingBot-Map 权重直接塞进 CasDiffMVS 推理代码。

### C3. 商业许可调查结论

此前调查发现其训练谱系中包含约 0.9% Waymo 数据，综合权重的代码、权重、训练数据和再分发/商用链条没有形成足够明确的证据闭环。当时结论是：

```text
许可证证据不足 / insufficient evidence
```

不是说“确定不能商用”，而是不能在证据不足时批准商用集成。用户随后认为剔除 Waymo 后自行重训 28 套数据过于麻烦，因此没有继续租 5090 跑 LingBot-Map。

### C4. 必须保留的谨慎措辞

以上是之前联网调查结论，不是法律意见。若未来重新启用 LingBot-Map，必须冻结精确仓库 revision、权重 revision、训练清单、每个数据集许可、NOTICE、模型条款和依赖条款，再做完整商业使用审计。不能只凭“Apache 仓库”推导权重和数据也可商用。

---

## D. 其他学习式 SOTA 调研

### D1. VGGT

用户认为 VGGT 太重，不适合手机本地生产，因此没有进入主线。

### D2. 多数据集训练的总体认识

从 LingBot-Map 等项目得到的方向性认识是：多套数据按比例联合训练是一种成熟方案，可能比只用 MVG/TG 更有泛化性。但这只是路线认识，不代表已有一套许可证干净、手机可部署、质量已验证的综合权重。

---

## E. MapAnything Apache：高密度、高表面质量，但严重重影

### E1. 为什么尝试

用户记得研究仓库曾调查 MapAnything，且它使用 Apache 许可。它的目标是直接从多视图图像预测场景几何、相机等，能够产生非常稠密的点云。

### E2. 执行过的官方链和变体

先后尝试过：

1. 官方 Apache 权重；
2. 官方 `preprocess_inputs`；
3. 官方 `demo_colmap.py`；
4. 官方 `demo_inference_on_colmap_outputs.py`；
5. 官方 `pred["pts3d"]`；
6. 官方 Open3D 1% IQR 体素导出；
7. 只输入图像的官方链；
8. 输入官方 K/位姿的条件链；
9. 直接读取原生 COLMAP `cameras.bin/images.bin/points3D.bin` 的链；
10. 修复错误 metric/nonmetric 位姿标志后的链；
11. 132 帧一次性推理 + 官方 `use_multiview_confidence=True` + confidence mask；
12. MapAnything 深度加 CasDiffMVS 严格多视图几何一致性过滤。

### E3. 代表性产物和点数

- 初始原始输出：约 24,763,526 点，几何漂移/重影明显；
- 修复 metric/nonmetric 位姿标志后的 b28 真彩稠密版：约 24,693,184 点；这是用户认为最好的 MapAnything 版本，但仍有重影；
- 100% 官方纯图片链 + 1% IQR 体素：约 864,738 点；
- 官方 K/位姿条件链：约 1,199,148 点；
- 原生 COLMAP 直通官方链：约 1,405,572 点；
- 132 帧官方 multiview confidence/mask：约 22,655,698 点，完整度明显下降；
- MapAnything + CasDiffMVS 严格几何融合：约 6,260,068 点，场景被过滤得过残缺。

### E4. 用户肉眼结论

- MapAnything 单帧/局部表面、纹理和密度很好；
- 但多帧之间存在重影、双层表面或漂移；
- CasDiffMVS 基本没有重影，但表面完整度/质感不及 MapAnything；
- 用户不接受把 MapAnything 的低完整度过滤版作为产品结果；
- 24 帧重叠窗口不是已确认的官方标准方案，因此用户不接受把它冒充官方做法；
- confidence mask 会减少重影，但完整度损失太大；
- CasDiffMVS 过滤证明“几何一致性筛选”可去掉错误，但当前阈值把大量正确点也删掉。

### E5. 本地实验目录

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_camera_locked_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_knownposes_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_native_colmap_official_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_nonmetric_fixed_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_official_image_only_20260826.nosync
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/mapanything_apache_b28_official_known_pose_20260826.nosync
```

历史网页名称包括：

```text
/mapanything_compare/
/mapanything_original/
/mapanything_fixed/
/mapanything_official_image_only/
/mapanything_official_native_colmap/
/mapanything_mvconf/
```

### E6. 当前结论

MapAnything 不是当前主线。它证明了用户想要的“表面密度级别”是可能的，但当前完整官方链在这组 132 帧真实输入上没有达到无重影、全局一致的产品结果。

---

## F. GLUEMAP / 全局稀疏几何调查

曾调查并讨论了类似以下流程：

```text
图像检索与共视邻接
→ 重复场景排歧义
→ 最多约 25 张的局部 star
→ tracks
→ 旋转/内参/Sim(3) 全局平均
→ global BA
→ SIFT 与增强 BA
```

这个流程主要解决全局相机和稀疏几何一致性，最终核心产物是稀疏点云/相机图，不会自动产生用户需要的稠密点云。它可以作为稠密阶段的几何基础，但用户当前生产稀疏点云已经很好，所以没有理由为得到“另一个稀疏点云”替换现有管线。

---

## G. COLMAP PatchMatch MVS：当前主线

### G1. 为什么切换

用户生产端的稀疏点云已经使用 COLMAP。继续使用 COLMAP 的 PatchMatch MVS + StereoFusion 有以下优势：

- 复用现有相机内参、位姿、共视图和稀疏模型；
- 不需要神经网络训练或训练素材；
- 同一生态的数据格式最顺滑；
- 官方长期维护；
- PatchMatch 有明确的多视图光度和几何一致性；
- StereoFusion 是官方稠密融合器；
- 从产品工程角度比继续训练若干 MVS 网络更可控。

### G2. 与 CasDiffMVS 的区别

| 项目 | CasDiffMVS | COLMAP PatchMatch MVS |
|---|---|---|
| 类型 | 学习式 MVS | 经典优化式 MVS |
| 是否需要权重 | 需要 | 不需要 |
| 是否需要训练素材 | 需要 | 不需要 |
| 核心 | 神经深度/概率体 | 随机初始化、传播、扰动、光度代价、几何一致性 |
| 融合 | 自己的数据导出/过滤链 | 官方 StereoFusion |
| 手机难点 | 模型大小与推理后端 | 官方 CUDA kernel 需要跨端 GPU 承载 |

### G3. COLMAP 许可注意

- COLMAP 主体代码为 BSD-3-Clause，可用于商业软件，但仍需保留相应许可/NOTICE；
- GPU SIFT 历史上涉及 SiftGPU 许可问题；当前产品稀疏管线需要单独核对是否走 CPU SIFT 或其他许可干净实现；
- 用户表示可以公开源码，因此 AGPL 组件不是绝对阻碍，但必须逐项审计实际链接和分发方式；
- 不能把 COLMAP 主体许可自动扩展到 CUDA、第三方 SIFT、数据、模型或其他依赖。

---

# 五、跨端 COLMAP/Vulkan 复刻已经完成了什么

## 1. 架构方向

当前工程目标：

```text
现有 COLMAP 稀疏结果
→ C++ 控制层
→ Vulkan Compute / SPIR-V PatchMatch
→ iOS 通过 MoltenVK
→ Android/鸿蒙原生 Vulkan
→ 官方深度/法线/一致性图格式
→ 官方 StereoFusion
→ 真彩 PLY
```

不是三套算法，只允许平台宿主薄层不同。

## 2. 已建立的模块

主要目录：

```text
vendor/official_dense/
lib/official_dense/
test/official_dense_*.dart
```

已建立或实现的部分包括：

- C ABI；
- Dart FFI 接口骨架；
- CMake 构建契约；
- 上游 COLMAP revision/manifest 契约；
- PatchMatch controller；
- workspace I/O；
- 资源 arena 规划；
- Vulkan host、runtime、batch executor、launcher；
- 冻结 SPIR-V shader bundle；
- MoltenVK artifact/build gate；
- iOS 独立测试 Bundle 能力探针；
- 文件事务与输出发布；
- 官方 StereoFusion bridge；
- 深度/法线/一致性诊断导出；
- 多个语义和 ABI contract tests。

## 3. 已机械翻译/实现的 shader 步骤

- 初始光度代价；
- reference filtering；
- 法线初始化；
- 深度初始化；
- RNG 初始化；
- FP32 map rotation；
- U32 RNG state rotation；
- transpose/flip；
- PatchMatch full sweep；
- 光度 pass；
- 几何 pass；
- 最终读回与官方格式写出。

## 4. RNG

早期讨论过 OpenMVS 官方 PCG 替换路线。当前运行主线后来机械实现了 CUDA cuRAND XORWOW 的状态、seed 和 uniform 语义。注意：源文件仍叫：

```text
sweep_full_openmvs_pcg.comp
```

这个文件名具有历史误导性，不能据此断言当前仍使用 PCG。要以 include 和 runtime 实际代码为准。

## 5. 当前保留的官方参数

- 分辨率：2000×1500；
- source views：10；
- window radius：5；
- window step：1；
- num samples：15；
- iterations：5；
- 每轮 4 个 sweep；
- FP32；
- 官方阈值与步骤顺序；
- photometric 后 geometric consistency；
- 官方 StereoFusion。

## 6. 完整输出

已完成一次 132 帧全量 photometric + geometric + StereoFusion，最终：

```text
17,052,272 points
```

网页上场景总体深度轮廓基本对，但存在明显放射状飞点；用户认为数千万点才符合“稠密”，1,705 万仍太少。

## 7. 当前认证状态

代码仍明确输出：

```json
"not_cuda_parity": true
```

因此任何接手者都不能说“已经 100% 官方复刻完成”。目前应称：

```text
按 COLMAP 4.1.1 语义进行中的 Vulkan 机械移植，已能端到端输出，但尚未通过完整 parity/质量认证。
```

---

# 六、为什么稀疏点云很好，稠密仍会放射

这不是已定案的单一原因，但需要理解两阶段的差别：

1. 稀疏点云只保留高置信特征匹配和 BA 后的几何点，数量少、筛选严格；
2. 稠密 PatchMatch 为几乎每个像素估计深度和法线；低纹理、反光、遮挡、边界或错误代价会产生大量错误候选；
3. 如果深度、法线、相机矩阵、纹理坐标、插值、RNG 顺序、旋转缓冲、几何一致性图或 StereoFusion 输入中任一处移植不完全，错误深度会沿相机光线表现为放射状飞点；
4. 稀疏相机正确不等于稠密 shader 正确；稀疏阶段的相机可以复用，但不能替代每像素 PatchMatch 和融合一致性；
5. 当前放射状飞点更像需要继续定位的移植/过滤/融合问题，不能简单归咎于 COLMAP 官方算法。

用户的立场是：官方 COLMAP 不应在正常正确链上出现这种低级错误，因此优先假设移植仍有遗漏，继续逐项比对，而不是发明一个事后飞点滤波器掩盖问题。

---

# 七、性能实测和已经做过的优化

## 1. 原始灾难性慢点

最早单个 reference 约 355 秒。原因不是 PatchMatch 理论本身，而是 U32 RNG map rotation 使用了逐像素 `VkBufferCopy`：

- photometric 约 4.20 亿个 copy regions；
- geometric 约 4.50 亿个 copy regions；
- 临时 vectors 数百 MB；
- CPU 提交和内存管理极其糟糕。

## 2. 已保留的优化

### 2.1 精确 U32 rotate compute shader

把逐像素 copy 机械替换为计算 shader，保持 U32 数据语义：

```text
约 355s → 64.5s
```

约 5.5 倍提升。

### 2.2 拆分/减少相机常量加载

拆分 K/R/T 与 P/invP 加载，并把常量归一化移出内层：

```text
63.842s → 58.571s
```

### 2.3 subgroup-aware barrier

在保持当前测试可过的情况下缩窄部分同步：

```text
58.571s → 57.590s
```

57.590 秒是最近明确保留并测过的单 photo_ref0 稳定基线。

## 3. 已测试但变慢、已撤回的优化

### 3.1 `spirv-opt` 安全内联/标量替换

```text
58.571s → 60.464s
```

变慢，撤回。

### 3.2 每行缓存 121 个 bilateral weights 到 threadgroup memory

```text
57.590s → 67.999s
```

推测增加 threadgroup memory、降低 occupancy，撤回。

## 4. MoltenVK 正式性能追踪

开启官方 `MVK_CONFIG_PERFORMANCE_TRACKING=1` 的一次运行约 66.140 秒，统计：

- 23 次 queue submit；
- command encoding 平均约 0.155ms，总计仅数毫秒；
- shader compile 也是毫秒级；
- Metal command buffer GPU execution 平均约 2873.481ms × 23，覆盖了大部分总时间。

结论：当前瓶颈主要在 GPU sweep kernel，不在 CPU 命令录制、pipeline compile 或提交次数。只做 pipeline cache、descriptor cache 不可能带来目标所需的约 10 倍提升。

## 5. 目标速度换算

132 references × photometric/geometric 两阶段 = 264 个主要阶段。若总时间要小于 30 分钟，扣除 I/O 和 StereoFusion 后，每阶段大致需要 5～6 秒。当前约 57.6 秒，仍差约一个数量级。

---

# 八、暂停时最重要的代码断点：当前源码、SPIR-V 和构建不完全一致

这是接手时最容易踩坑的地方。

## 1. COLMAP 维护者 WIP PR #4124 实验

找到一个 2026 年关闭的维护者 WIP PR：PatchMatch CUDA performance improvements。它不是已合并官方版本，也没有 reviewer approval。里面包含：

- circular `LocalRefImage` buffer；
- `__syncwarp`；
- cost caching；
- `sincosf`；
- `__expf`。

其中 `__expf` 明确牺牲精度，约只有 3～4 位有效小数/约 13 ULP，违反用户“无损”要求，不能使用。

## 2. 已做的 ring buffer 实验

只机械实现了 commit `112da5e` 中 circular reference window 思路，没有启用 `__expf`。

ring-only 构建：

- contract test 通过；
- 12/12 CTest 通过；
- 单 photo_ref0：61.943 秒；
- 比 57.590 秒稳定基线更慢。

因此 ring-only 不应该作为保留优化。

## 3. 用户要求暂停前最后一次未完成修改

在 ring-only 变慢后，刚把 active sweep shader 的两个同步点改为无条件 `barrier()`，意图更机械地对应 COLMAP 4.1.1 的 `__syncthreads()` 并检查 MoltenVK MSL barrier 范围。

但这次修改还没有：

- 编译；
- 重新生成 SPIR-V；
- 更新 frozen manifest/hash；
- 运行测试；
- 运行单 reference benchmark。

所以当前存在不一致：

- `vendor/official_dense/cost_ops/cost_ops.glsl`：含 circular buffer；
- `vendor/official_dense/sweep/sweep_full_openmvs_pcg.comp`：含尚未打包的无条件 `barrier()` 源码修改；
- frozen bundle / runtime / executable：ring-only SPIR-V，仍是旧 barrier 版本；
- 已测 executable：61.943 秒的 ring-only 构建。

禁止直接拿当前源码或当前 executable 宣称新结果。

## 4. 暂停时哈希

当前源码/资产只读核对得到：

```text
cost_ops.glsl
95e6080f5836543e821f3d5283eec20462d82546f5602c5af0414e8e9541bf6e

sweep_full_openmvs_pcg.comp（含未打包 barrier 源改）
1413d6829de127adc7a15935ac9d0d173dbebbff922e2caf666e34fe729f4bdf

当前冻结 sweep SPIR-V（ring-only、旧 barrier）
500ac0e2f7b4b6d826e9897c96e6cd031c1527ce770bfea550c8c8d9087836f5

frozen_manifest.json
1ea72ebe35b84d701cd2aaf9fe50d7b3006c95b9962e4c8ddd66e1d0aded2ff1
```

最近稳定 57.590 秒基线曾记录：

```text
sweep source
5e5e7566273f3b928f94f803c3af9583e1068b93822e9983938a0ea6055e4992

sweep SPIR-V
54241b23e5fed8b98d7ec13475c76cffe21c8fb454176dc49c0797a652ea9555

word count
22994
```

不要盲目按哈希回退整个工作树。必须只处理这次稠密实验涉及的文件，并保护其他人/用户改动。安全做法是先保存当前内容与 diff，再决定：

1. 完成 ring+barrier 的打包和单 ref 试验；或
2. 只把 ring/barrier 实验恢复到已证实的 57.590 秒稳定稠密基线。

从现有证据看，优先恢复稳定基线更合理，因为 ring-only 已经变慢；但必须先确认用户是否允许继续。

---

# 九、当前资源规划和内存风险

当前单 reference 计划内存：

```text
3,312,173,760 bytes ≈ 3.31GB
```

大致包含：

- device local：约 2.826GB；
- host upload：约 162MB；
- readback：约 168MB；
- host values：约 156MB。

MoltenVK 报告可用 GPU memory 约 13,639MB，但这是统一内存环境，不能按独立显存理解。生产 App、浏览器、系统、PLY viewer 同时占内存。

只读审计发现：

- 当前 arena 为不少 map 保留了 4 个 rotation 版本；
- 官方 peak 更接近 current + destination 两缓冲；
- photometric 阶段可能分配了不必要的 source-depth/mask/readback/graph/U32 gray 资源；
- persistent backend/pipeline/descriptor 可减少冷启动和重复分配；
- 这些优化优先降低内存和冷开销，但未必解决 10 倍 GPU kernel 性能差距；
- 不要启用当前代码里未完成的 “partitioned” path，它可能重复全高度工作，既慢又可能语义错误。

---

# 十、联网得到的官方/权威信息

以下是已查到并应继续核对的主要来源。

## 1. COLMAP 官方 FAQ

```text
https://github.com/colmap/colmap/blob/master/doc/faq.rst
```

官方可提速手段包括：

- 多 GPU 并行独立 references；
- 更多 RAM / cache；
- 恢复/跳过已完成视图；
- 降低 image size；
- 减少 source images；
- 减少 samples/iterations；
- window step=2；
- 缩小 window radius；
- 关闭 geometric consistency；
- CMVS 分区/裁剪。

对当前用户而言，只有不改输出质量的资源与并行优化可直接采用。降低分辨率、减少 source/sample/iteration、关闭 geometry、CMVS 裁剪都可能降低质量，不能偷偷使用。

## 2. COLMAP PR #4154

```text
https://github.com/colmap/colmap/pull/4154
```

该 PR 合并了并行输入读取/resize 和新的 `num_threads`。它能改善 I/O，但当前性能追踪表明主要瓶颈在 GPU sweep，不足以解决 10 倍差距。

## 3. COLMAP WIP PR #4124

```text
https://github.com/colmap/colmap/pull/4124
```

维护者的性能实验，已关闭、未合并。可作为研究证据，但不能称官方稳定实现。尤其不能使用牺牲精度的 `__expf`。

## 4. COLMAP main PatchMatch CUDA

```text
https://github.com/colmap/colmap/blob/main/src/colmap/mvs/patch_match_cuda.cu
```

观察：

- sweep block 固定 32 threads，与 local window layout 有关；
- 最新 main 有 Blackwell 编译规避；
- AMD gfx9 有手动双线性纹理仿真；
- 这些说明 texture sampling 和硬件语义是移植重点。

## 5. MoltenVK 官方配置

```text
https://github.com/KhronosGroup/MoltenVK/blob/main/Docs/MoltenVK_Configuration_Parameters.md
```

重要信息：

- `MVK_CONFIG_FAST_MATH_ENABLED` 默认 2；可能大幅提速，但可能偏离 IEEE754，不能在无损要求下盲目打开；
- `PREFILL_METAL_COMMAND_BUFFERS=0` 通常最快但内存最大，当前本来就是默认；
- command pooling 默认开启；
- Metal argument buffers 默认开启，日志确认已经生效；
- 可以用 performance tracking 获取队列编码、GPU command buffer 等统计。

## 6. MoltenVK private performance API

```text
https://github.com/KhronosGroup/MoltenVK/blob/main/MoltenVK/MoltenVK/API/mvk_private_api.h
```

`vkGetPerformanceStatisticsMVK` 可观察 shader compile、queue encoding、GPU execution、memory 等。当前运行已经用官方日志证明 GPU kernel 占主导。

## 7. Apple GPU counters / occupancy

```text
https://developer.apple.com/videos/play/wwdc2020/10603/
https://developer.apple.com/documentation/xcode/finding-your-metal-apps-gpu-occupancy
```

Apple 官方提示：

- thread/threadgroup memory 会限制 occupancy；
- 太宽的 barrier 会让流水线停顿；
- 寄存器压力和 spill 会显著拖慢；
- 太小的 grid 或不合适的 threadgroup 也会降低吞吐；
- 当前 121 weights cache 变慢与 occupancy 降低高度一致。

## 8. Khronos Vulkan 通用建议

官方建议减少 queue submit、缓存 descriptor/pipeline/command buffer、精确设置 barriers。但当前记录中 CPU 编码只有毫秒级，所以这些建议是必要工程卫生，不是 10 倍加速答案。

---

# 十一、已完成的代码/性能审计结论

## 1. CPU / submit 审计

- 旧 U32 rotation 是主要 CPU 灾难，现已修复；
- 当前每阶段约 23 个 submit/wait：初始化、initial cost、20 sweep、readback；
- backend/pipeline/descriptors 每 reference 仍会重建；
- persistent reuse 有价值，但当前 GPU execution 才是主瓶颈。

## 2. 官方 runtime 结构审计

- 四旋转缓冲可能超额；
- photometric 存在不必要资源；
- 可做 two-buffer arena 和 persistent runtime；
- 先保证 output parity，再做内存缩减；
- 不要启用未完成 partitioned path。

## 3. shader 热点审计

MoltenVK 导出的 MSL：

```text
/private/tmp/pw-mvk-shader-dump.BF1dc7/shader-cs-6727d555bfa59cb6.metal
```

SHA-256：

```text
750e0ccef21483b651fe633fa9c3f493978fff2c2d4adfcd8e790c600b7180a7
```

审计发现：

- 74 处 `spvUnsafeArray`；
- 约 558 个函数作用域变量；
- K/R/T/H/P 等小数组被大量复制；
- 可能导致寄存器 spill 和 occupancy 崩溃；
- subgroup barrier 被翻成 `simdgroup_barrier(mem_device|mem_threadgroup|mem_texture)`，范围可能过宽；
- source image normalized coordinate sampling 在每样本执行除法；
- 官方 CUDA 使用未归一化像素坐标；
- Vulkan unnormalized sampler 不能直接使用 2D array view，若机械匹配可能需要 descriptor array of 2D views；
- 下一条最有依据的无损方向是：保持表达式顺序的机械标量化，而不是改公式。

## 4. 数值一致性现实

CUDA 与 Metal/Vulkan 的纹理插值、FMA、`exp/sqrt` 等细节未必能做到 bitwise identity。最终应预注册容差并冻结逐图深度、法线、一致性图的比较规则，而不是在看到结果后随意改阈值。但用户当前产品判断仍以网页肉眼为最终标准。

---

# 十二、已经遇到的主要问题

1. **质量问题**：17M PLY 有放射状飞点；点数和完整度不足。
2. **认证问题**：尚未完整证明 Vulkan 与官方 CUDA COLMAP 等价，程序仍 fail-closed 标记 `not_cuda_parity`。
3. **性能问题**：单阶段约 57.6 秒，距离全 132 帧 30 分钟差约 10 倍。
4. **内存问题**：单 reference 约 3.31GB，18GB 机器无法粗暴并发多个完整 workspace。
5. **源码/产物不一致**：暂停时有未重新打包的 barrier 源修改。
6. **用户信任问题**：此前多次称“官方链”但后来发现 flag、转换、过滤或导出不同，用户对任何“差不多官方”的说法极其敏感。
7. **许可问题**：不同模型、训练数据、SIFT、CUDA、第三方依赖必须分开审计，不能笼统说“可商用”。
8. **沟通问题**：不要长时间无更新；运行超过 30～60 秒要报告正在做什么、实测耗时和是否卡住。

---

# 十三、严格的下一步计划

在用户明确说“继续”以前不要执行。用户恢复后按以下顺序，不要跳步。

## Phase 0：冻结和恢复一致状态

1. 只读记录当前 `git status`、目标文件哈希、frozen manifest 和 build identity；
2. 明确 ring-only、ring+barrier source、57.590s 稳定基线三者身份；
3. 不碰其他产品改动；
4. 优先恢复到最近已验证的 57.590s 稳定基线，或在用户明确同意时完成一次 ring+barrier 单 ref 验证；
5. 没有测试和哈希闭环前禁止全量跑。

## Phase 1：建立可比较的逐图产物

当前 probe 不能只打印耗时。必须让单 reference 测试持久化：

- photometric depth；
- photometric normal；
- geometric depth；
- geometric normal；
- consistency graph/mask；
- cost；
- RNG state 或能证明 RNG 序列的摘要；
- 输入/参数/source view manifest；
- shader/source/SPIR-V/runtime hash；
- elapsed time、peak memory。

所有后续优化都必须对同一 frozen ref0 输出做比较。

## Phase 2：用 Apple 官方 GPU counters 定位

只跑一个 reference，采集：

- occupancy；
- register spill；
- threadgroup memory 限制；
- texture bandwidth；
- ALU utilization；
- barrier stall；
- 每个 pass GPU 时间。

没有 counter 证据不要继续猜。

## Phase 3：只做有官方依据的机械无损优化

优先级：

1. **机械标量化 K/R/T/H/P 小数组**：保持逐项计算顺序，减少 `spvUnsafeArray` 和寄存器压力；
2. **精确 barrier 语义**：对照 CUDA `__syncthreads`、SPIR-V memory semantics 和生成 MSL，缩到正确范围，但不能造成竞态；
3. **官方像素坐标纹理采样语义**：先做小型 fixture，证明 Vulkan 2D descriptor array + unnormalized sampling 与官方输入一致，再替换 normalized 除法；
4. **维护者 PR 的 cost caching**：只提取不改公式、不用 `__expf` 的部分，并逐图比较；
5. **persistent backend/pipeline/descriptor**：减少每 reference 冷启动；
6. **two-buffer arena / 删除 photometric 无用资源**：先解决内存，再考虑安全并发；
7. **并发 independent references**：只有单 ref 内存显著下降、GPU counter 显示有闲置且 18GB 安全时才尝试，绝不能直接并发 3～4 个 3.31GB workspace。

每个优化都按以下 gate：

```text
改一个变量
→ compile + SPIR-V validate
→ contract tests
→ 同一 ref0 逐图输出比较
→ 单 ref 性能
→ 内存
→ retain / revert
```

## Phase 4：单 reference 硬门槛

在恢复全量 132 帧之前，至少满足：

- 单 photo/geo 阶段进入约 5～6 秒量级，或给出严谨的新全流程预算；
- 输出不出现新的数值漂移；
- peak memory 可控；
- 深度/法线/一致性图可持久化和比较；
- shader、SPIR-V、bundle、runtime manifest 完全一致；
- 所有目标测试通过。

若机械无损优化后仍明显高于门槛，停止假装“再优化一点就行”，向用户报告 M3 Pro 全官方参数 ≤30 分钟不可达的证据。

## Phase 5：132 帧全量和网页验收

只有单 ref gate 通过后：

1. 顺序或受控并发执行 132 refs；
2. 完成 photometric；
3. 完成 geometric consistency；
4. 用官方 StereoFusion；
5. 输出真彩 PLY；
6. 统计点数、耗时、峰值内存、失败/跳过帧；
7. 用单一网页打开，不自动 TSDF、裁切、体素降采样；
8. 用户肉眼检查放射状飞点、表面、墙体、完整度和密度。

## Phase 6：手机本地化

Mac 质量和速度成立后才继续：

- 先独立测试 Bundle；
- 再真实 iPhone；
- 生产 benchmark 最终必须在物理 iPhone 的真实生产管线完成；
- 测后台执行、系统调度、热降频、内存和中断恢复；
- 不能要求用户一直前台等待；
- 不能在没有 iOS 合法后台时间机制的情况下承诺无限后台 GPU 任务；
- Android/鸿蒙暂时可不真机适配，但算法和 shader 不能写成 Apple 专属。

---

# 十四、接手后第一轮允许执行的只读命令

先不要构建或运行。只读核对：

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld/colmap-vulkan-dense-20260826
git branch --show-current
git rev-parse HEAD
git status --short
git diff -- vendor/official_dense/cost_ops/cost_ops.glsl
git diff -- vendor/official_dense/sweep/sweep_full_openmvs_pcg.comp
shasum -a 256 \
  vendor/official_dense/cost_ops/cost_ops.glsl \
  vendor/official_dense/sweep/sweep_full_openmvs_pcg.comp \
  vendor/official_dense/vulkan_shader_bundle/assets/sweep_sweep_full_openmvs_pcg.comp.spv \
  vendor/official_dense/vulkan_shader_bundle/frozen_manifest.json
```

然后核对：

```bash
rg -n 'not_cuda_parity|barrier\(|circular|LocalRefImage|num_iterations|num_samples|window_radius' \
  vendor/official_dense test/official_dense_cost_ops_contract_test.dart
```

不要把 `git status` 中大量其他产品文件当成稠密任务自己造成的，也不要清理它们。

---

# 十五、重要本地实验目录索引

```text
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_cuda_lifetime_benchmark_20260829
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_20260828
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_mvkstats_photo_ref0_20260829_01
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_official2000_20260829
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_official_ring_photo_ref0_20260829_01
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_dense_xorwow_official2000_run_20260829
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_diagnostic768_audit_20260829
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_local_weightcache_benchmark_20260829
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_rotate_u32_benchmark_20260829
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_safe_spirv_benchmark_20260829
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_subgroup_barrier_benchmark_20260829
/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/colmap_vulkan_timing_breakdown_20260829
```

初始 TG 白墙交接原文：

```text
/Users/kaidongwang/.codex/attachments/0e9c5292-c6aa-4079-a25f-40e066eb1097/pasted-text.txt
```

这是历史证据，不是当前唯一真相；当前代码/产物优先。

---

# 十六、5090 和远端状态

历史 Vast.ai 5090 曾用于 TG/MVG 10 轮训练。历史连接信息曾为：

```text
ssh -p 30028 root@213.224.31.105
ssh -p 23397 root@ssh5.vast.ai
```

历史远端路径：

```text
/data/finetune_pack
/data/casdiffmvs_mvgZeroDTU.ckpt
/data/BlendedMVG
/root/diffmvs
/venv/main/bin/python
```

这些信息可能已经过期、实例可能已释放。不要自动连接、续租或假设数据仍在。绝对不要在交接中泄露私钥。用户目前要求暂停，也没有理由继续租 5090；当前主线是 Mac/Vulkan COLMAP 稠密，不是训练。

---

# 十七、哪些事情已经被否定或暂时不做

- 不继续盲目增加 TG 训练轮数；
- 不把 10 轮 TG/MVG 单场景结果说成普遍胜利；
- 不使用许可谱系不清的 LingBot-Map 官方综合权重做商用；
- 不以 VGGT 作为手机主线；
- 不把 MapAnything 24 帧窗口说成官方标准方案；
- 不使用 confidence mask 后残缺严重的 MapAnything 作为最终结果；
- 不使用 CasDiffMVS 严格过滤造成只剩 626 万点的融合结果；
- 不用 GLUEMAP 稀疏图替代用户需要的稠密点云；
- 不把 CUDA 服务端当手机本地方案；
- 不写 Apple 独占的稠密算法主线；
- 不用 `__expf`、降低分辨率、减少迭代等有损方式满足速度；
- 不在当前源码/bundle 不一致时跑 132 帧全量；
- 不再以“文件变大”代替真实进度、进程和日志检查。

---

# 十八、对接时应当如何向用户沟通

用户不希望看被写散的文档或模糊进度。每次沟通要直接回答：

1. 现在具体在做哪一步；
2. 已经完成了什么；
3. 实测耗时是多少；
4. 是否卡住，若卡住卡在哪里；
5. 当前结果能否网页查看；
6. 下一步多久能看到结果；
7. 哪些是官方、哪些是移植、哪些是实验；
8. 失败就明确说失败，不要用“有进展”掩盖。

运行超过一分钟，要给简短进度。不要连续半小时只说“还在查”。不要把计划写成完成事实。

---

# 十九、最终事实摘要

截至暂停时：

- CasDiffMVS 纯 BlendedMVG 32 轮基线已完成；稳定、少重影，但白墙不完整；
- CasDiffMVS + TG/MVG 50/50 短程 10 轮已完成；部分洞变小，但出现新错误连接，未证明总体胜出；
- LingBot-Map 因综合权重商业谱系证据不足未进入商用；
- MapAnything 官方链及多个变体已跑；点多、表面好，但 132 帧全局重影明显；严格一致性过滤又损失完整度；
- GLUEMAP 属于全局稀疏几何，不直接解决稠密输出；
- 当前正式方向是复用现有 COLMAP 稀疏结果，跨端 Vulkan 复刻 COLMAP PatchMatch MVS，再用官方 StereoFusion；
- 已实现端到端 132 帧，生成 17,052,272 点真彩 PLY；总体几何可见，但有放射状飞点、点数不足；
- 单 reference 从约 355 秒降到 57.590 秒稳定基线；仍远不满足 30 分钟全量目标；
- 性能瓶颈已确认主要在 GPU sweep kernel；
- 当前正在调查寄存器压力、barrier、纹理坐标与 occupancy；
- 最近 ring buffer 优化变慢到 61.943 秒；
- 暂停时源码、SPIR-V、frozen bundle 有一个未打包 barrier 修改，不可直接视为一致版本；
- 当前没有资格宣称 100% 官方 parity；
- 用户要求暂停，所以现在不应继续运行。

你的第一责任不是马上“跑起来”，而是保护现场、恢复可证明的一致基线、建立逐图输出证据，然后一个变量一个变量地继续机械复刻和无损优化。

---

# 二十、接手者确认模板

在用户要求恢复工作时，先用简短中文确认：

```text
我已接住断点：当前主线是 COLMAP 4.1.1 PatchMatch MVS → Vulkan/SPIR-V → MoltenVK → 官方 StereoFusion，不是继续训练 CasDiffMVS，也不是 MapAnything。最近稳定单阶段是 57.590 秒；17,052,272 点全量 PLY 有放射飞点；ring-only 变慢到 61.943 秒；暂停时有一个尚未打包的 barrier 源修改，所以我会先只恢复/冻结一致基线，不会直接跑 132 帧，也不会动生产 iPhone。随后用单 ref 的深度、法线、一致性图和 GPU counters 定位，再做有官方依据的机械无损优化。
```

只有用户明确说“继续”之后才进入 Phase 0。
