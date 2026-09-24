# Official DA3 community signal audit

日期：2026-06-04

## 结论

- 不能只看官方 GitHub issue。3DGS / ComfyUI / Blender / StableDiffusion 用户社区的信号更接近真实使用面。
- 社区里没有看到“DA3 在室内/近距离/中小场景必然重影所以不可用”的一致结论。
- 反而有多个用户把 DA3 当作快速点云、粗相机位姿、3DGS 初始化或点云 densify 工具使用。
- 同时，社区也暴露了大量工程层问题：PLY/GLB 导出差异、坐标系转换、intrinsics/extrinsics 提取、Windows bit-depth/blur、VRAM/RAM、第三方 ComfyUI node distortion。
- 因此当前更强的假设是：官方 DA3 image-only upstream 本身值得复刻；我们的 `_pose` CoreML/AR 输入、CoreML export、坐标系、npz/PLY 消费路径仍然是需要排查的地方。

## 主要社区信号

### 1. r/GaussianSplatting: DA3 被用作快速点云/粗位姿

来源：Depth Anything 3 is super fast
链接：https://www.reddit.com/r/GaussianSplatting/comments/1p70u57/depth_anything_3_is_super_fast/

要点：

- 用户把 DA3 用在 vertical 4K 60fps cellphone video。
- demo 使用约 40 帧，也有人表示 10 帧左右有过好结果。
- 他们的目标不是把 DA3 当完整传统扫描替代品，而是用它生成 rough camera positions，再用 GOLMAP/COLMAP refine，得到更好的点云或 splats。
- 有用户问 16GB VRAM + 32GB RAM 跑不动 GS，说明官方 feed-forward/GS 路径仍然不是普通移动端级别的完整训练/导出负载。

读法：

DA3 的 camera/depth 输出在社区里被认为有实用价值，但常被当作初始化或粗几何，不是“直接裸 PLY 就是最终产品”。

### 2. r/ComfyUI: 第三方 PLY/节点问题很明显

来源：Depth anything 3. ComfyUI > Blender Showcase
链接：https://www.reddit.com/r/comfyui/comments/1ozgypp/depth_anything_3_comfyui_blender_showcase_quality/

要点：

- 用户说 DA3 demo 能生成 point cloud，但官方/演示侧更偏 GLB；Blender 生态更常要 PLY。
- 第三方 ComfyUI 的 PLY 输出有人反馈 distorted。
- 有 Windows 用户反馈比 V2 更 blurry、blown out，怀疑 bit-depth 或节点实现问题。
- 有用户提到 model 输出的 intrinsics/extrinsics 是 OpenCV 坐标系，需要转换到 Blender 等坐标系。

读法：

这和我们现在看到的风险非常一致：DA3 模型输出不等于工程导出必然正确。坐标系、相机参数、格式转换、第三方 wrapper 都可能制造“看起来像模型重影”的问题。

### 3. SplataraScan: DA3 被集成用于点云 densify

来源：SplataraScan Update
链接：https://www.reddit.com/r/GaussianSplatting/comments/1ryv3u3/splatarascan_update_1click_pipeline_depth/

要点：

- 工具作者把 Depth Anything 3 集成进扫描 pipeline，用于 densify point clouds。
- 描述说这显著改善复杂场景的 structural accuracy。
- 同一个更新里也提到 COLMAP refinement 会造成 blurry results 的 bug，说明传统 SfM/优化后处理也会引入视觉问题。

读法：

DA3 在实用扫描工具里被当成增强器，而不是被社区普遍认定为会制造不可控重影。

### 4. 多个社区帖子把 DA3 和传统 GS/COLMAP 并列比较

来源：

- 3 Splatting methods compared
  https://www.reddit.com/r/StableDiffusion/comments/1pw92zr/3_splatting_methods_compared/
- Depth Anything 3 is wild
  https://www.reddit.com/r/StableDiffusion/comments/1p71pvw/depth_anything_3_is_wild/

要点：

- 有人把 traditional gsplat、DA3、SHARP 放在同一工具里比较。
- 示例里 DA3 使用较少视角，传统 gsplat 使用更多视角。
- 社区评价 DA3 快、alignment 好，但仍把传统 GS/COLMAP/refinement 作为质量路径之一。

读法：

DA3 的强项是快速 feed-forward 几何和 pose/depth consistency；最终产品质量通常还依赖 view coverage、格式转换、渲染/融合/优化。

### 5. 官方/PyPI/Hugging Face 生态不是单一 demo，而是一组集成

来源：

- Depth Anything 3 official README
  https://github.com/ByteDance-Seed/Depth-Anything-3
- depth-anything-3 PyPI
  https://pypi.org/project/depth-anything-3/
- awesome-depth-anything-3 PyPI
  https://pypi.org/project/awesome-depth-anything-3/1.0.0/
- DA3-GIANT Hugging Face discussion
  https://huggingface.co/depth-anything/DA3-GIANT/discussions/1

要点：

- 官方 README / PyPI 都强调 DA3 是 arbitrary visual inputs、with or without known camera poses。
- 官方 README 的 Awesome DA3 Projects 包含 DA3-blender、ComfyUI-DepthAnythingV3、ROS2、TensorRT、VideoDepthViewer3D 等。
- Hugging Face model card discussion 把模型标签从单纯 `depth-estimation` 扩展到 `image-to-3d`，并加入 `3d-gaussian-splatting`、`3d-reconstruction`、`pose-estimation`。

读法：

官方和社区生态都把 DA3 当几何基础模型，而不是一个固定导出格式的一键扫描成品。生态越多，坐标系/相机 convention/导出格式错误的概率也越高。

### 6. HF demo / GS 路径也不是所有环境都开放

来源：Depth Anything 3 Hugging Face Space
链接：https://depth-anything-depth-anything-3.hf.space/?__theme=system

要点：

- 抓取到的 HF Space 页面显示 `3D Gaussian Splatting rendering is currently DISABLED`。

读法：

即使官方 demo，也会因为运行环境/资源/部署策略禁用 GS 渲染。这提醒我们不要把“论文有 GS/benchmark 高”直接等同于“任意本地/mobile 环境可无痛得到干净点云/GS”。

## 和我们的推理如何对齐

1. `DA3BASE_476x742_N35` 不应再做尺寸探索；这是固定目标。
2. 但当前 APP bundle 只有 `DA3BASE_476x742_N35_pose.mlpackage`，不是官方 DA3-Streaming image-only baseline。
3. 官方 image-only 的位姿来自网络 `cam_dec`，不是 AR/VIO。
4. 社区线索支持继续优先闭合 image-only 复刻，而不是先发明 voxel/TSDF/surfel cleanup。
5. 如果 image-only target 输出仍然厚，再判断是否属于 DA3-BASE 在该 capture 上的上游几何极限。
6. 如果 image-only 明显变薄，则 `_pose` CoreML/AR 输入/坐标转换就是主嫌。

## 现在最应该查的不是“DA3 是否垃圾”

更应该查：

1. `DA3BASE_476x742_N35_image_only.mlpackage` 是否能按官方语义导出。
2. image-only 输出的 `pred_extrinsics/pred_intrinsics` 是否和 PyTorch official image-only 同 window 对齐。
3. `window_016` 的 `first35/first10` PCA minor growth 是否从旧 `_pose` 的厚层指标明显下降。
4. Research/APP 是否把 OpenCV w2c、Blender/PLY/GLB 坐标系和 camera convention 混了。
5. 是否错误使用了 full-chunk `combined_pcd.ply` 或第三方 PLY 语义，而不是 official core-frame npz downstream。
6. 是否把 DA3 的 OpenCV w2c 输出直接喂给 Blender/PLY/GLB 工具，而没有做坐标 convention 转换。

## 当前工作结论

你的直觉是对的：如果 DA3 所有人一跑室内近距离都厚得不能看，它不可能拿这个姿态发布。社区证据也不支持“DA3 普遍裸失败”。

当前最合理判断是：我们还没真正跑到官方 DA3-Streaming image-only baseline 的同目标输出。目标依旧是先复刻官方，再谈移动端产品适配。
