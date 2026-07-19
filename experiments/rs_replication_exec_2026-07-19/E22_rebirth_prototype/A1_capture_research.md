# A1 采集分叉调研(2026-07-19 上午):RS 照片规格 + 12MP in-AR 跨端

## RealityScan Mobile 照片分辨率/长宽比 取证结论清单

### 总裁决:精确像素尺寸 = **UNRESOLVED**(官方零声明,社区零 EXIF 实锤)

扫遍官方文档全目录(System Requirements / Application Settings / Camera View / Project Files / Step-by-Step / Useful Information)+ release notes 1.2→1.8.1 全部,以及 Epic 论坛 Discourse 全文搜索(exif / 4032 / 3024 / 12MP / megapixel / HEIF resolution / image size 等十余组查询)、Fabbaloo 两篇 hands-on、Falkingham 博客、engineering.com、CG Channel、KIRI/swiftwand 对比文、PMC 论文、arXiv 2604.19216(与 RS 做采集对比实验的论文)——**没有任何来源给出 RS Mobile 照片的像素尺寸、MP 数或长宽比数字**。以下是分级旁证。

---

### ① 官方分辨率声明:查无(E1 级最接近的句子)

- **E1** 文件格式:"The images in HEIF format (or JPG on Android—check Application settings)" — https://dev.epicgames.com/documentation/realityscan-mobile/RealityScan-Project-Files (注:现行 Application Settings 文档里已无图像格式开关,只有 Scanning Mode / Data usage / Masking 等 9 项)
- **E1** 1.7 Android Bugs Fixed:"HEIF images being saved in low resolution." — 官方承认 Android 曾有低分辨率保存 bug(1.7 修复)— https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-mobile-1-7-release-notes
- **E1** 1.5.3 iOS Bugs Fixed:"Jpeg fallback on Heic issue" — iOS 存在 HEIC→JPEG fallback 路径 — https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-mobile-1-5-3-release-notes-ios-only
- **E1** 系统门槛:"RealityScan is compatible with iOS devices, which can run version 16 and higher, and Android devices, which support ARCore" — https://dev.epicgames.com/documentation/realityscan-mobile/RealityScan-System-Requirements-and-Installation
- **E1** 张数上限:"The image limit is set to 300 images." — https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-camera-view
- 排除项:rshelp.capturingreality.com 是**桌面版**(原 RealityCapture)帮助,其 "60 Mpx and more" 句属桌面语境,不适用。

### ② 社区 EXIF 尺寸:查无(UNRESOLVED)

- 最接近:**E3** Epic 论坛用户 Ghost_Ly(Xiaomi 13 Ultra):"I'm used xiaomi13U taked 311 photos…the 311 photos is HEIC format" — 只证 Android 也出 HEIC,无尺寸 — https://forums.unrealengine.com/t/2132099
- **E3** S22 Ultra 用户查过 RS Mobile 文件 EXIF,只抱怨 GPS 字段缺失,未提尺寸 — https://forums.unrealengine.com/t/2654212
- reddit 直接抓取被墙,间接检索(多组关键词)零命中含像素尺寸的帖子。

### ③ AR 模式 vs Camera Control 模式规格是否不同:**有官方级旁证(差异存在),但无规格数字**

- **E1**(最硬一条)1.8 Android Bugs Fixed:"Poor image quality & large HEIF file size for scans made in AR mode" — 官方实锤:**AR 模式照片走的是另一条管线,质量曾差于其他模式**(至少 Android)— https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-mobile-1-8
- **E1** 1.6 release notes:AR 模式 "camera settings cannot be adjusted";Camera Control 模式 "full manual control over your camera settings, allowing you to adjust focus, shutter speed, ISO values, white balance and flash" — 两模式相机栈不同 — https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-mobile-1-6-release-notes
- **E1** 1.8 iOS Known Bugs:"RAW image files don't match JPEG files" — 1.8 起 iOS 侧存在 RAW 文件(暗示非 AR 模式走 AVCapture 且并存 RAW+JPEG)— 同 1.8 URL
- **E1** 1.8 起共三模式:"AR Guidance / Object Mode / Standard Mode",后两者 "advanced camera controls"
- **INF**:iOS AR Guidance 若用 ARKit `captureHighResolutionFrame`(iOS 16 门槛与 app 的 iOS 16+ 要求吻合;Apple WWDC22 称该 API "should return a 12 megapixel frame",即 4032×3024 4:3),则 AR 模式照片 ≈12MP 4:3——**此为推断,无人反编译证实 RS 用了该 API**。Android AR 模式绑 ARCore(E1)同理推断走 AR 相机流(1.8 前的 AR 模式画质 bug 与此吻合)。

### ④ 上传是否降分辨率:查无声明(UNRESOLVED)

- **E1** 照片确会上传云端处理:Data usage 设置 "analyze your images and process your projects only when you are connected to the selected internet connection";1.5.3 bug "Photos do not upload after waiting 1-2 hour outside the app"
- **E3** Fabbaloo(2022 beta, iOS):"the processing is done in the cloud with zero opportunity to provide any tweaking" — https://www.fabbaloo.com/news/hands-on-with-realityscan-part-2
- 1.7 的 "HEIF images being saved in low resolution" 是**本地保存 bug**,不是上传降采样声明。无任何来源声明上传前降/不降分辨率。

### 给上游的可操作结论

要拿到确切数字,文本情报已穷尽,只剩实测一条路:真机装 RS Mobile,各模式拍几张,Files→On My iPhone→RealityScan→Captures 里直接看 HEIC 尺寸(iOS 端零成本)。已知官方事实支持的最小画像:iOS=HEIC(有 JPEG fallback,1.8 另存 RAW)、Android=HEIF/JPG、AR 模式与 Camera Control 管线不同且 AR 模式历史上质量更差、300 张上限。

Sources: [1.7 RN](https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-mobile-1-7-release-notes) | [1.8 RN](https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-mobile-1-8) | [1.6 RN](https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-mobile-1-6-release-notes) | [1.5.3 RN](https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-mobile-1-5-3-release-notes-ios-only) | [Project Files](https://dev.epicgames.com/documentation/realityscan-mobile/RealityScan-Project-Files) | [App Settings](https://dev.epicgames.com/documentation/en-us/realityscan-mobile/RealityScan-Application-Settings) | [Sys Req](https://dev.epicgames.com/documentation/realityscan-mobile/RealityScan-System-Requirements-and-Installation) | [Camera View](https://dev.epicgames.com/documentation/realityscan-mobile/realityscan-camera-view) | [论坛2132099](https://forums.unrealengine.com/t/2132099) | [论坛2654212](https://forums.unrealengine.com/t/2654212) | [Fabbaloo P2](https://www.fabbaloo.com/news/hands-on-with-realityscan-part-2) | [Apple captureHighResolutionFrame](https://developer.apple.com/documentation/arkit/arsession/3975720-capturehighresolutionframe)

---

## 三平台"AR 会话内 12MP 静照"能力表(截至 2026-07)

| 平台 | 官方 API | in-AR 静照上限 | 保证等级 | 关键约束 |
|---|---|---|---|---|
| **iOS ARKit** | `ARSession.captureHighResolutionFrame`(iOS 16+) | **12MP(4032×3024)**,带完整 pose/anchors | E1+E2,一等公民 API,全机型(A12+)行为一致 | 48MP 必须停 ARKit;12MP 上限至今未升 |
| **Android ARCore** | **无对等 API**。仅 SharedCamera(Camera2 interop)+ 自加 JPEG ImageReader surface | 文档名义 **"e.g. 12MP" occasional JPEG,仅 "high-end phones"** | E1 文档存在,E3 工程不可保证(无样例/无设备清单/有崩溃报告) | 保证线只有"1 个额外 surface 且分辨率=某个 CPU config"(典型≤1920×1080);active 时禁 `setRepeatingRequest` |
| **HarmonyOS AR Engine** | **无任何路径** | 预览纹理 ~1440×1080;无 RGB 取流 API、无拍照 API | E1(API 面缺失即证据) | 相机由 AR Engine 经 `SetCameraGLTexture` 独占渲染;无 shared-camera 概念;Kit 仅限中国境内接入 |

## 证据明细

**iOS(结论未过时,维持原判)**
- E1:"Requests a frame outside of the normal frequency that contains a high-resolution captured image."(iOS 16.0+)— https://developer.apple.com/documentation/arkit/arsession/capturehighresolutionframe(completion:)
- E2(Apple 员工,Frameworks/Vision Pro Engineer):"However, `session.captureHighResolutionFrame` should return a **12 megapixel frame**."并明示勿与 `recommendedVideoFormatFor4KResolution` 混淆 — https://developer.apple.com/forums/thread/709811
- INF:检索 2025-2026 无任何升限(48MP in-AR)证据;Apple 文档无变更痕迹。原 grounded 结论 "in-AR 硬上限 12MP、48MP 须停 ARKit" **仍成立**。

**Android ARCore(截至 v1.54.0)**
- E1(能力天花板,分层写死在文档里):high-end phones = "2x YUV CPU streams, e.g. 640x480 and 1920x1080 / 1x GPU stream, e.g. 1920x1080 / **1x occasional high res still image (JPEG), e.g. 12MP**";mid-tier 二选一(有 JPEG 就只剩 1 路 CPU 流);默认流 "1x YUV CPU stream, currently always 640x480" — https://developers.google.com/ar/develop/java/camera-sharing
- E1(唯一硬保证):额外 surface 仅保证 "a single additional surface, with a resolution equal to one of the CPU resolutions returned by `Session.getSupportedCameraConfigs`"(典型≤1080p,非 12MP);active 期间 "must not call `CameraCaptureSession#setRepeatingRequest`";"The Camera2 APIs can be used directly without restriction **while ARCore is paused**."(pause 拍照=断 tracking,不算 in-AR)— https://developers.google.com/ar/reference/java/com/google/ar/core/SharedCamera
- E1(无新特性):whatsnew 至 v1.54.0(v1.49-1.54 全查)无任何 captureHighResolutionFrame 对等物或高分辨率捕获新特性;近年唯一相机相关=v1.45 torch mode — https://developers.google.com/ar/whatsnew-arcore
- E3(生态现状):官方 issue 求"AR 会话内拍高清静照"样例,2022-10-31 开至今 **Open、零 Google 回复、零样例** — https://github.com/google-ar/arcore-android-sdk/issues/1547
- E3(碎片化实锤):`setCameraConfig` 选高分辨率 config 在 Pixel 3/Note 9 直接崩 "Error configuring streams: Function not implemented (-38)",且 `getSupportedCameraConfigs` 返回的 config 并不保证真能配置 — https://github.com/google-ar/arcore-android-sdk/issues/1660 ;多 surface 叠加致设备无法处理的历史报告 — https://github.com/google-ar/arcore-android-sdk/issues/239
- UNRESOLVED:哪些具体机型支持"12MP JPEG 第四流"**无官方清单**(supported-devices 页无此维度);"high-end phones" 无定义;旗舰实拍规格社区无系统性数据。

**HarmonyOS AR Engine(HarmonyOS NEXT)**
- E1:相机预览=GL 纹理路径 "HMS_AREngine_ARSession_SetCameraGLTexture(arSession, textureId)",官方示例尺寸 `int32_t width = 1440; int32_t height = 1080;` — https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arengine-c-arworld
- E1(API 面缺失):API 参考中 ARFrame 仅有 `acquireDepthImage16Bits` / `acquireDepthConfidenceImage` / `acquireSceneMesh`,**无 RGB 相机图像获取、无拍照/高分辨率捕获 API** — https://developer.huawei.com/consumer/en/doc/harmonyos-references/arengine-api-arengine
- E1(部署红线):"仅支持在中国境内(香港特别行政区、澳门特别行政区、中国台湾除外)接入使用" — https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arengine-overview
- E3:旧 HMS AR Engine(Android/EMUI)有 `HwArFrame_acquireCameraImage` 但同样只到预览分辨率 — https://www.joyindie.com/articles/33785.html
- UNRESOLVED:AR Engine 占用相机期间能否用 Camera Kit 并发抓拍,官方零表述;无 shared-camera 文档 → INF:当前无官方 in-AR 高清静照路径。

## 最终判定:**不可跨端 —— 分层(iOS 独有真 12MP)**

- **iOS = 可**(唯一有一等公民 API 的平台,12MP 上限 2026 未变)。
- **Android = 名义可、工程不可保证**:12MP occasional JPEG 只是文档口径(high-end only),无对等 API、无样例(#1547 近 4 年无人理)、无设备清单、config 崩溃在案;唯一跨机型保证只有 ≤1080p 级 CPU 帧。原 2026-06 审计"4K 对等不存在、AR Optional 分层"**不过时**,仅需补一句修正:12MP occasional JPEG 文档路径存在,可作高端机 best-effort 试探(运行时探测 + 失败降级 1080p),不可作产品承诺。
- **HarmonyOS = 不可**:连 RGB 取流 API 都没有,天花板即 1440×1080 预览纹理。

对产品的含义:凡依赖"in-AR 12MP 取色/纹理"的管线(如取色分辨率、enrich 源图质量)在 Android/鸿蒙没有对等输入,跨端设计必须按"iOS 12MP / Android ≤1080p(高端机试探 JPEG)/ 鸿蒙 ≤1440×1080"三档喂图预算做。
