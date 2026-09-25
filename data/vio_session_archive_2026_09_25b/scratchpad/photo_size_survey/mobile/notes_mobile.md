# 手机端 App 照片尺寸调研笔记（第二轮，2026-09-25）
只收手机 App 证据；桌面软件不算。

## Apple ARKit / Object Capture（系统层，所有基于 ARKit 的 iOS 扫描 App 共用）
- 论坛 828928（2026-06）：iPhone 17 Pro 上 ObjectCaptureSession 失败日志
  `ObjectCaptureSession.takeStillImageCapture(isAutoCapture:): Failed to capture high resolution frame!`
  同时 ARSession 报 sensor failure ⇒ ObjectCaptureSession 静帧走 ARSession 高分辨率帧路径（日志证据，尺寸未写）
  https://developer.apple.com/forums/thread/828928
- WWDC22 10126 Discover ARKit 6：高分辨率帧 = 原生相机分辨率；iPhone 13 上即 12MP；点名用于 Object Capture
  https://developer.apple.com/videos/play/wwdc2022/10126/
- 论坛 709811（2022-07，Apple 工程师，M1 iPad Pro）：captureHighResolutionFrame "should return a 12 megapixel frame"
- 论坛 724790（2023-02，Apple 工程师）：iPhone 14 Pro 人脸追踪 capturedImage 1440x1080；深度恒 640x480
- 官方文档 captureHighResolutionFrame(completion:)（iOS 16）：最高分辨率要选 non-binned videoFormat；
  captureHighResolutionFrame(using: AVCapturePhotoSettings)（iOS 26.0 起）+ VideoFormat.defaultPhotoSettings（iOS 26.0）
  "Some video formats do not support a significantly higher still image resolution than the streaming camera resolution."
- 论坛 769604（2024-12 DTS）：AR 会话中用超广角拍 48MP "There is no supported way to do this"
- 论坛 794169（上轮已记）：iPhone 12 Pro Max Area Mode HEIC 3024x4032，深度 192x256
- 论坛 810457（2025-12，Apple 工程师）：ObjectCaptureSession 在 HEIC 里写自定义元数据，没有公开途径自行提供
- it-jim 博客：iPhone 13 Pro Max 上手机端 vs Mac 重建；ObjectCaptureSession 存 HEIC；iOS 端没有细节档
- 没找到：48MP 机型（14 Pro 起）上 ObjectCaptureSession Images 目录 HEIC 的实测尺寸

## Polycam
- 官方帮助「How to Extract Raw Data」：LiDAR 模式原始导出 cameras JSON 示例 width 1024 / height 768，fx 712.37
  https://learn.poly.cam/hc/en-us/articles/38276871185044
- openMVS issue #1071 用户 trv-rscanlo2（2023-12-04）："the images are 1024x768 and the depth images are 256x192"（Polycam 示例数据）
  https://github.com/cdcseacave/openMVS/issues/1071
- 帮助「Web App 上传失败」：缩到 12MP，再失败 8MP（上轮已记）
- robogeosociety #36（2026-05，iPhone 16 Pro）：Space 模式可选手机端 Custom 处理 vs Cloud；没提照片尺寸
- 帮助「How to Use Object Mode」（2026-07-14 更新）：照片/物体模式要求 "Keep WiFi or cellular active throughout cloud processing" ⇒ 云端；变焦 0.5x/1x/3x/微距；每次最多 2000 张；未写尺寸
  https://learn.poly.cam/hc/en-us/articles/27425185907348-How-to-Use-Object-Mode
- dev.scaniverse.com 对比文：Polycam、KIRI、Luma 云端；Scaniverse 手机端

## RealityScan Mobile（Epic）
- Falkingham 博客（2023-11，Galaxy Fold 3，主摄 12MP）："creates a sparse 3D point cloud ... on device, it's still uploading the full resolution images"
  https://peterfalkingham.com/2023/11/24/realityscan-photogrammetry-on-android/
- 论坛 721368：iOS 照片存 Files→RealityScan→Captures，HEIF；Android 在 Android/data/com.epicgames.realityscan/files/projects/；无尺寸
- 1.7.1（2025-08）：iOS 微距镜头；1.9（2026-08）：无分辨率条目
- Epic 文档站 dev.epicgames.com 本轮超时，未读到 Camera View / Application Settings

## Scaniverse（Niantic）
- 官方 FAQ：全部数据在手机本地处理；Android 需 ARCore Depth API；未写尺寸 https://dev.scaniverse.com/support
- Medium/scaniverse.com 博客 403，跳过

## Qlone
- 官方 FAQ：照片模式 "takes higher quality 4K images"（高级版）；带垫子 AR 模式手机端实时处理；iOS 无垫子模式走 Qlone Cloud；仅 iOS
  https://www.qlone.pro/faq

## KIRI
- FAQ/博客/4.0 发布/API 文档：均无照片尺寸；API 仅限张数 20–300；视频 ≤1920x1080；云端
- 帮助「Space Mode」（2026-07-14）：Default/Dense/Custom 手机本地；Cloud "Uses high-resolution images"，走 Polycam 服务器
  https://learn.poly.cam/hc/en-us/articles/36655587097620
- 帮助「Supported devices / Android 下载」：Android 需「高分辨率相机」，无具体像素

## PIX4Dcatch（Pix4D，手机采集 App，iOS+Android，云端 PIX4Dcloud 或桌面 PIX4Dmatic 处理）
- Advanced Settings（iOS）：Resolution = Normal（低于 4k*）/ 4K（约 4K*）/ Maximum（高于 4k*）；"* Actual values depend on the device model"；
  高分辨率采集仅 iPhone 11 起、iPad Pro 5 代起；Android 高级设置里没有分辨率项
  https://support.pix4d.com/hc/en/articles/360044027012
- FAQ "Can I select the image resolution?"：iOS 可选、随机型；Android "Due to limitations imposed by ARKit and ARCore, image resolution cannot be selected."
  最大分辨率+>1750 张建议 ≥10GB 空间
  https://support.pix4d.com/hc/en-us/articles/360043331092
- Google Play 用户评论（搜索摘要，未读原文）："since android limits the developer to low resolution images"

## ARCore（系统层）
- Shared camera 文档：默认 CPU 流 "currently always 640x480"（追踪用）；GPU 流 typically 1920x1080；
  高端/中端机：可再加 "1x occasional high res still image (JPEG), e.g. 12MP"
  https://developers.google.com/ar/develop/java/camera-sharing

## 手机本地重建类（LiDAR/ARKit 视频帧）
- 3D Scanner App（Laan Labs）：OpenMask3D #13 用户 pranav-satheesan-mphasis（2024-03-20）"the RGB images were in 1440x1920"（"Export all data"）
  https://github.com/OpenMask3D/openmask3d/issues/13
- Record3D：#108 用户（2025-02-24）LiDAR 模式 RGB (960,720)、深度 (256,192)；作者回复确认 RGB 为高分辨率、深度为小图
  https://github.com/marek-simonik/record3d/issues/108 ；#76 作者（2024-01）"The RGB images were downsampled to VGA resolution."（某个特定录制情形）
- Polycam LiDAR 关键帧 1024x768（见上）

## Metascan（Abound Labs）
- 官方支持页："Photo Mode uploads your photos to our photogrammetry servers for processing." 无照片尺寸 https://aboundlabs.com/support
## WIDAR
- 官方指南：照片扫描上传云端处理；无尺寸 https://web.widar.io/en/how-to-use-photo-scan-2/
## Trnio：云端处理（搜索摘要，trnio.com 页面抓取失败）；"hi-res images"，无具体数
## 华为 HMS Core 3D Modeling Kit（端侧采集 SDK + 云侧建模）
- 搜索摘要（未能核对原文，华为文档站超时、Medium 403）：物体建模支持的图像分辨率 "1440 x 1080 px (on Huawei phones which use AR Engine) and 480p to 1080p (on non-Huawei Android phones)"；物体 <30cm³
- 官方博客（CSDN/博客园）：普通 RGB 手机多角度拍照 → 上传云端 → 生成模型
## 学术
- TMO arXiv 2303.15060：作者自研 Object Capture 采集 App，iPhone 13 Pro（12MP），AR-capture 图 4032x3096，ARKit 视频 1280x720
- MR-Compare arXiv 2607.20325：iPhone 15 Pro Max，Scaniverse 手机端优化、Polycam Space 云/后处理；移动端用视频
- PIX4Dcatch iOS 技术更新说明：1.17.0（2022-10-11）"Ability to select camera resolution for capture from iOS 16"（与 ARKit 6 高分辨率帧同一版本系统）；
  1.29.0（2023-11-27）修复 "capturing high resolution or 4k" 时深度图损坏；2.12.0 修复 "maximum resolution projects" 焦距
  https://support.pix4d.com/hc/en-us/articles/360043445632
- PIX4Dcatch Android 技术更新说明：无分辨率条目；设备兼容 "All ARCore enabled devices" https://support.pix4d.com/hc/en-us/articles/360056359911
- RealityScan Android 上线公告（2023-06-20）：需要 ARCore、Android 7+ https://www.realityscan.com/news/realityscan-mobile-is-now-available-for-android-devices
- KIRI FAQ「How does KIRI Engine process the files」：上传云端服务器重建 https://www.kiriengine.app/faq/how-does-kiri-engine-process-the-files
- KIRI 照片扫描功能页："there are no specific camera requirements"（摘要）
- 易模（武汉博雅弘拓，App Store 3.3.7 2024-09-29）：照片/视频上传云端建模，5–20 分钟；无尺寸 https://app.gongchuangshijie.com/cloud/

## 被挡/跳过
- Reddit 搜索接口 403；Medium（Scaniverse、Huawei Developers）403；scaniverse.com/news 403；hackster 403；
- dev.epicgames.com RealityScan 文档超时；developer.huawei.com 超时

## 结论（只写有证据的）
1. 没有任何一家手机 App 公开写明在 48MP/50MP 机型上用全像素（8064x6048 或 8160x6144 之类）拍摄或重建。
2. 手机本地重建的出货 App，公开可见的输入全是视频流级别帧：Polycam LiDAR 1024x768、3D Scanner App 1440x1920、Record3D 960x720、
   华为 3D Modeling Kit（未核原文）华为机 1440x1080 / 非华为 480p–1080p；Apple Object Capture 手机端只出 reduced 细节。
3. 需要高分辨率的都走云端：Polycam 照片/物体模式、Polycam Space 的 Cloud 选项（"Uses high-resolution images"）、KIRI、RealityScan（稀疏点云在手机，
   上传全分辨率）、Metascan、WIDAR、Qlone 无垫子模式、Trnio、易模、PIX4Dcatch（PIX4Dcloud）。
4. 系统层上限：ARKit 高分辨率帧官方说法为「原生相机分辨率」、Apple 工程师 2022 说 12MP（M1 iPad Pro）；iOS 26 起可传 AVCapturePhotoSettings；
   ARCore 共享相机：追踪 CPU 流固定 640x480，高端机可偶发一张约 12MP JPEG；PIX4Dcatch 官方称 Android 受 ARCore 限制不能选分辨率。
5. 云端/网页侧对超大图的处理：Polycam 网页上传先在浏览器压缩，失败就让用户缩到 12MP、再不行 8MP。
