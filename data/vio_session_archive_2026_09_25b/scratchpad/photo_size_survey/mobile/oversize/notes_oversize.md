# 商业 3D 重建 App 对超大/超规格照片的处理（2026-09-25）
只算手机 App 及其配套云端。

## Apple PhotogrammetrySession（iOS 17+ 手机端也可用）
- Limits（官方，iOS 17/macOS 14）：按设备的常量上限 maximumInputImageDimension、maximumNumberOfInputImages
  - maximumInputImageDimension："If images larger than this are provided, they will be ignored and an `.invalidSample` message will be output."
  - maximumNumberOfInputImages：超出的部分忽略，并对每张输出 .invalidSample
  https://developer.apple.com/documentation/realitykit/photogrammetrysession/limits-swift.struct/maximuminputimagedimension
- Output 里分开报：invalidSample(id:reason:) 样本无效 / skippedSample(id:) 没能用于重建 / stitchingIncomplete 没能全部拼接 / requestError
- iOS 上的具体数值：没找到；个人仓库 PawelWywiol/photogrammetry 在 M2 16GB Mac（macOS 26.5）上读出 1000 张 / 16384 px（仅供参考，非手机）
- ObjectCaptureSession：到达设备重建上限时默认停止拍摄（WWDC23 10191）
- 外部照片：iOS 上 PhotogrammetrySession 可吃 AVCapture 拍的 HEIC，只会警告缺 LiDAR 点云，Apple 工程师称可忽略（论坛 810457）
- 内存：Apple 工程师（2026-05，论坛 827311）预填充数组 "can cause out of memory traps on iOS devices"，建议用惰性序列或文件夹输入
- 论坛 810496（2025-12，无回复）：iOS 26 上 170–200 张 2160x3840 JPG 第二三次运行 std::bad_alloc（VTPixelTransferSession）

## Polycam（iOS/Web 导入 + 云端）
- 网页端：上传前在浏览器压缩；图太大浏览器内存不够会失败；帮助页让用户自行缩到 12MP，不行再 8MP，并报 bug 附上图片尺寸和张数
  https://learn.poly.cam/hc/en-us/articles/27489260990868 （2026-07-14 更新）
- 导入限制：张数 20 起、按套餐 150/300/2000（Splat 1000）；格式 PNG/JPG；视频 15 s–30 min、≤16 GB；没有单张像素/大小上限
  https://learn.poly.cam/hc/en-us/articles/30549121659412
## KIRI Engine（App/Web/API + 云端）
- API：图片 20–300 张；视频 ≤1920x1080、≤3 min；500 错误码：2005 张数超上限、2007 少于 20 张、2009 视频不符合要求、2010 格式不符；没有单张尺寸类错误码
  https://docs.kiriengine.app/photo-scan/image-upload/ https://docs.kiriengine.app/code-details
- App：Basic 150 / Pro 500 张（4.0 发布）
- 预处理工具页：接受 JPG/PNG/TIFF/HEIC/RAW；无缩图说明
## RealityScan Mobile：员工 JakubVanko（2026-09-21）"you can only process images that you capture in the application" ⇒ 不支持导入
  https://forums.unrealengine.com/t/saved-photos/2776006 ；应用内每次最多 300 张（官方文档，搜索摘要）
## Scaniverse：手机 App 没找到导入；外部 360 视频只能走网页版（桌面浏览器、云端），只收视频不收静态图，按时长限 5/10 min
  https://www.nianticspatial.com/docs/scaniverse/360camera/
## Luma：官方采集 API 客户端（2024 已归档）无大小检查；5 GB（视频或图片 zip）只见于第三方教程，且让用户自己缩图
## Varjo Teleport（iOS 采集 + 云端）：图片 PNG/JPEG/HEIC，50–2000 张或总 ≤5 GB；视频 30 s–15 min 或 ≤5 GB；无单张像素限制
  https://teleport.varjo.com/help/en_US/capturing/uploading
## PIX4Dcloud（PIX4Dcatch 的云端）：≤4000 张；警告 42 MP 以上大画幅相机即使不到 4000 张也未必能处理；"Images must not be modified (rotated, cropped, or edited)"
  https://support.pix4d.com/hc/en-us/articles/360043611612 https://support.pix4d.com/hc/en-us/articles/14988429657117
## 华为 3D 建模服务：搜索摘要称「建议 12MP(4032×3024)、上传前不要裁剪、用原始分辨率」——原文未核（华为文档站只回框架、CSDN 521）
## 易模：官网/新闻页无张数、大小、分辨率限制；搜索摘要称自定义建模 ≥50 张（未核）
## Metascan / Qlone / WIDAR：没找到导入外部照片的说明或限制
