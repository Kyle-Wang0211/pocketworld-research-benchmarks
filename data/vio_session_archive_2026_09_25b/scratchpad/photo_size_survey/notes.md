# 照片尺寸调研笔记 (2026-09-25)

## Apple
- WWDC26 session 304 "Implement high resolution photo capture" https://developer.apple.com/videos/play/wwdc2026/304/
  - 12MP 为基线；24MP 多帧融合（iPhone 15 起相机 App 默认）；48MP 单帧，需 balanced/quality 优先级；只有 .photo preset 支持 24/48
  - "Setting maxPhotoDimensions is a request, not a guarantee"
  - 需 setPreparedPhotoSettingsArray 预分配；deferred processing / responsive capture
- Apple 采集指南 https://developer.apple.com/documentation/realitykit/capturing-photographs-for-realitykit-object-capture
  - "Shoot at the highest resolution your camera supports and use RAW format if possible."
- ObjectCaptureSession 实拍：论坛 794169，iPhone 12 Pro Max（12MP 传感器）HEIC 3024x4032，深度 192x256 —— 不能证明 48MP 机型行为
- WWDC23 10191：iOS 端只支持 reduced detail

## Android
- CaptureRequest.SENSOR_PIXEL_MODE (API 31) https://developer.android.com/reference/android/hardware/camera2/CaptureRequest#SENSOR_PIXEL_MODE
  - "By default, all camera devices operate in ... SENSOR_PIXEL_MODE_DEFAULT mode."
  - DEFAULT: "sensors would typically perform pixel binning"；MAX: "typically operate in unbinned mode"
  - 两个 StreamConfigurationMap 的输出不能混在同一 CaptureRequest
- ULTRA_HIGH_RESOLUTION_SENSOR (API 31)：max 模式像素阵列至少 24MP；REMOSAIC_REPROCESSING 能力
- CameraX ResolutionSelector PREFER_HIGHER_RESOLUTION_OVER_CAPTURE_RATE (1.3.0)：只用 getOutputSizes+getHighResolutionOutputSizes（默认 map）；
  "This mode does not allow applications to select those ultra high resolutions."
- CameraX ImageCapture 默认 HIGHEST_AVAILABLE_STRATEGY；默认 4:3；默认 CAPTURE_MODE_MINIMIZE_LATENCY
- 第三方访问：Open Camera 开发者：厂商把 "high photo resolutions" 限在原生相机；Nokia G21 50MP 帖回答「normal ... to be pixel binned」；Fairphone 5 论坛同
- 鸿蒙：photoProfiles 枚举；preconfig 默认 4:3；单段式默认 SPEED；没找到合并/全像素官方说明

## COLMAP (main@922cd08, 2026-09-25)
- FeatureExtractionOptions.max_image_size=-1 → SIFT 自动 3200；ALIKED/LoMa 1600（extractor.cc EffMaxImageSize）
- ImageResizerThread 缩图 → keypoint.Rescale 回原图坐标
- SiftExtraction.max_num_features 8192, first_octave -1
- PatchMatchStereo/StereoFusion max_image_size -1（全尺寸）；FAQ 显存不够就减小

## 实测
- pix-pro Poco X8 Pro Max 50MP vs iPhone 16 Pro Max 48MP：大项目 12MP RAW 更聪明默认；小物体高分辨率更好
- pix-pro iPhone 16 Pro Max：48MP/RAW "noticeable but slight increase"，摄影测量里不重要

## App
- Polycam 网页帮助（搜索摘要，原页 Cloudflare 挡）：上传失败时缩到 12MP，再失败 8MP
- RealityScan Mobile：未公开采集分辨率；1.7 修 "HEIF images being saved in low resolution"(Android)；1.8 已知问题 RAW 与 JPEG 不匹配；上传全分辨率（搜索摘要）
- KIRI：视频上传 ≤1920x1080；照片分辨率未公开

## 追加（Apple 官方逐字核对）
- AVCapturePhotoSettings.maxPhotoDimensions：默认取 supportedMaxPhotoDimensions 中最小值（iOS16+）
- AVCapturePhotoOutput.maxPhotoDimensions：必须 startRunning 前设，改动会触发长时间重配
- photoQualityPrioritization 默认 balanced
- WWDC26 304 逐字核对：request not guarantee；iPhone 15 起相机 App 默认 24MP；48MP 单帧仅 balanced/quality；24/18MP 仅 quality；只有 .photo preset；"processing can take several seconds"
- ObjectCaptureSession.Configuration 公开属性只有 checkpointDirectory / isOverCaptureEnabled，无分辨率选项；GuidedCapture 示例不设尺寸
- 论坛 776538：iPhone 16 Pro 48MP ProRAW 快门→文件 1.2–1.6 s；Apple 工程师建议 deferred processing
- 论坛 811832：开发者观察不设 maxPhotoDimensions 恒 12MP（0 回复）
- Lux/Halide iPhone 14 Pro 评测：48MP ProRAW 最长约 4 s；48MP 直出 JPG 明显更快

## 追加（Android）
- StreamConfigurationMap.getHighResolutionOutputSizes：≥24MP 的尺寸允许 <10fps

## 追加（桌面软件）
- Metashape 2.2 手册：对齐 High=原图，Medium=每边/2，Low=/4，Lowest 再/2，Highest=每边×2；深度图 Ultra high=原图，其后每档每边/2；拍摄建议 ≥5MP 且用最高分辨率
- RealityScan(RealityCapture) 对齐 Image downscale factor：最佳精度用 1；重建 Normal 深度图降 2，High detail 恒 1（help 页）
- AliceVision develop@8e4f0be：SIFT quality normal → firstOctave 0（全尺寸），≤6MP 上采样；preset normal 最多 20000 点；DepthMap downscale 默认 2
- 3DF Zephyr：关键点档 5000–20000；MVS 分辨率百分比；官方：缩图有时反而更好（JPEG/传感器伪影）

## 追加（画质实测）
- Sony 官方：暗光 2x2 合并，亮光片上 remosaic 回 Bayer
- ETASR 2024 (10.48084/etasr.8309)：不同手机对比、混杂，非同机合并 vs 全像素
- MDPI Sensors 2024 (10.3390/s24227311)：10 台手机，未比较合并 vs 全像素
- 严格的同机 12MP 合并 vs 48/50MP 全像素 SfM 精度论文：没找到

## 没找到
- Polycam/KIRI/RealityScan/Scaniverse/Luma/Qlone(仅"4K images")/Metascan 在 48/50MP 手机上的应用内拍照像素
- ObjectCaptureSession 在 48MP 机型上的输出尺寸（唯一公开样本是 12MP 传感器机型）
- 鸿蒙官方关于四拜耳合并/全像素的说明
