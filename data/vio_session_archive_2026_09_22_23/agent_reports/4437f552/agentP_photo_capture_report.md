# agentP — 我们自己的相机栈补「高清拍照」(零 ARKit 路径)

- 分支 `feat/ios-native-photo-capture`,已推 `origin`(github.com/Kyle-Wang0211/pocketworld)
- worktree `~/Developer/pocketworld-wt-photo`(交付后已 `git worktree remove`)
- 起点 `f0b3a40`

| commit | 内容 |
|---|---|
| `4433da1453b54ada979c2bb18a84cc241ac651f8` | 修 `PwXrslamLive.swift` 从未加进 Runner target(既有构建阻塞) |
| `405eca61efa77dde861b71e7016dd4fac2606e93` | **高清拍照主体**:Swift + Dart 门面 + 单测 + 两个符号的导出白名单 |
| `28ff7de55a65234c00265a264c3a689516f2f59a` | 补导出 `pw_camera_slot_exposure/_lock/_unlock`(三个既有孤儿符号) |

---

## 1. 抄了 Apple AVCam 的哪些函数

样例:**AVCam: Building a Camera App**
<https://developer.apple.com/documentation/avfoundation/avcam-building-a-camera-app>
本轮实际逐行对照的源码是样例包内的
`AVCam/Swift/AVCam/PhotoCaptureDelegate.swift` 与 `AVCam/Swift/AVCam/CameraViewController.swift`。

| AVCam 里的东西 | 我们抄到哪 |
|---|---|
| `CameraViewController.configureSession()` 的 `// Add photo output.` 一段(`session.canAddOutput(photoOutput)` → `addOutput` → 置高清开关) | `PwCameraSlotImpl.start()`,在 `beginConfiguration` 块内、`addOutput(videoDataOutput)` 之后 |
| `CameraViewController.capturePhoto(_:)` 的 settings 构造:`var photoSettings = AVCapturePhotoSettings()` + `if photoOutput.availablePhotoCodecTypes.contains(.hevc) { photoSettings = AVCapturePhotoSettings(format: [AVVideoCodecKey: AVVideoCodecType.hevc]) }` | `PwCameraSlotImpl.capturePhoto(requestId:)` |
| AVCam 注释原文 "The Photo Output keeps a weak reference to the photo capture delegate so we store it in an array to maintain a strong reference…" + `inProgressPhotoCaptureDelegates[settings.uniqueID]` | `inFlightPhotos: [Int64: PwPhotoCaptureProcessor]`,**先入表再 `capturePhoto`** |
| `PhotoCaptureProcessor` 类本身:`init(with requestedPhotoSettings:…)`、`didFinish()`、completionHandler 让持有者放掉自己 | `PwPhotoCaptureProcessor` |
| `photoOutput(_:willBeginCaptureFor:)` | 记 `resolvedSettings.photoDimensions` |
| `photoOutput(_:willCapturePhotoFor:)` | AVCam 放快门动画;我们无 UI,改抓一次 `device.exposureDuration` 作兜底 |
| `photoOutput(_:didFinishProcessingPhoto:error:)` — `photoData = photo.fileDataRepresentation()` | **逐字同句**,另加 `photo.timestamp` / `photo.metadata` EXIF / `photo.cameraCalibrationData` |
| `photoOutput(_:didFinishCaptureFor:error:)` — 错误检查 → `guard let photoData` → 持久化 → `didFinish()` | 同一结构,持久化换成写沙盒 |

### 三处**刻意偏离**(不是抄漏)
- **(a) 落盘位置**:AVCam 走 `PHPhotoLibrary` + `PHAssetCreationRequest` 存进用户相册;我们写 app 沙盒 `Documents/pw_photos/`。重建管线读的是沙盒里的照片 + sidecar,而且我们没有也不该要相册写权限。
- **(b) `flashMode`**:AVCam `.auto`,我们**钉死 `.off`**。生产 ARKit 路径根本不会打闪光;打了闪的照片与同批未打闪的在光度上不是一套数据,而且闪光改曝光时长,`exposure_s` 就不再能与视频流的曝光中点对齐。
- **(c) Live Photo / 深度 / `previewPhotoFormat`**:AVCam 全接,我们全不接。少接一项就少一处能改变 `resolvedSettings` 的变量。

### 额外从 SDK 头文件(iPhoneOS26.2.sdk)核实并写进注释的三条
- `AVCapturePhotoOutput.h:1496`:`cameraCalibrationDataDeliveryEnabled` 只有在 `cameraCalibrationDataDeliverySupported == YES` **且** "2 or more devices are selected for virtual device constituent photo delivery" 时才能置 YES ⇒ **单摄(`.builtInWideAngleCamera`)永远拿不到照片自带内参**。(仓里 `PwVioCapability.swift:39` 早有同样的结论,本轮回到头文件复核确认。)
- `AVCapturePhotoOutput.h:544/1454`:`maxPhotoDimensions` 必须取自 `activeFormat.supportedMaxPhotoDimensions`,且推荐在 `startRunning` 之前设;`AVCapturePhotoSettings.maxPhotoDimensions` **默认是最小的那个** ⇒ 逐张不写就等于主动要最低分辨率。
- `AVCapturePhotoOutput.h:348`:`maxPhotoQualityPrioritization = .quality` 会打开 OIS。而 `AVCaptureDevice.h:2311` 说 "The extrinsicMatrix and camera intrinsics should only be used when video stabilization is disabled" ⇒ 我们钉 `.speed`(顺带也关掉多帧融合,融合出来的照片没有单一曝光时刻)。
- `AVCapturePhotoOutput.h:1990`:`AVCapturePhoto.timestamp` "synchronized to the synchronizationClock of the AVCaptureSession … analogous to `CMSampleBufferGetPresentationTimeStamp()`" ⇒ **拍照时刻与视频流 PTS 同域,不需要换算**。

---

## 2. 接口实现(签名与约定完全按定死的来)

### Swift `@_cdecl`(追加在 `ios/Runner/PwCameraSlot.swift`)
```swift
@_cdecl("pw_camera_slot_capture_photo")
public func pw_camera_slot_capture_photo(_ requestId: Int64) -> Int32

@_cdecl("pw_camera_slot_photo_result")
public func pw_camera_slot_photo_result(_ outPath: UnsafeMutablePointer<CChar>,
                                        _ cap: Int32,
                                        _ outNums: UnsafeMutablePointer<Double>) -> Int32
```
- `capture_photo` **只受理不等待**。0 = 已受理;`-1` 相机没起来 / `-2` 这个会话装不了 `AVCapturePhotoOutput` / `-3` 同 `requestId` 还在飞 / `-4` `Documents/pw_photos/` 建不出来。
- `photo_result` 的 9 个 double 顺序冻结:`[requestId, fx, fy, cx, cy, width, height, t, exposure]`。0 = 有结果(**已消费**);`-1` = 还没有;`-2` = `cap` 放不下这条路径且**不消费**结果。
- **语义是 FIFO 逐个取走,不是"读最近一次"**(比"最近一次"更强:连拍时先完成的先出,来不及轮询也不会被顶掉)。原生侧上限 32 条,超了丢最老的并 `NSLog` 计账。调用方正确用法是循环取到 `null`。

### Dart 门面
- 实现:`lib/vio/ffi/pw_camera_photo_ffi.dart` — `PwCameraPhoto.capture/result/drain/available` + `PwCapturedPhoto`(10 个字段 + `sidecarPath`)。查符号用 `DynamicLibrary.process()`,包在 `try/catch` 里,**符号不在返回 `null` 不抛**(降级风格抄 `xrslam_live_ffi.dart`)。
- 冻结的调用名在 `lib/vio/pose/camera_slot_ffi.dart` 上转发(那里才是 `PwCameraSlot` 类所在):
  `PwCameraSlot.capturePhoto(requestId)` / `PwCameraSlot.photoResult()` / `PwCameraSlot.photoAvailable`。

### 落盘与 sidecar
- 照片:`Documents/pw_photos/<requestId>.heic`(HEVC 可用时)或 `.jpg`。
- sidecar:同目录 `<requestId>.json`,用生产同一个 `PWJSONSafety.data(withJSONObject:)` 序列化。
- 键(与生产 ARKit 路径同名的是 `t` / `intrinsics_fxfycxcy` / `image_w` / `image_h`):

```json
{ "version":1, "source":"avfoundation_photo_output",
  "native_role":"pw_camera_slot_photo_output", "request_id":…,
  "t":…, "image_w":…, "image_h":…, "image_dims_provenance":"image_file_header|resolved_photo_settings",
  "resolved_photo_w":…, "resolved_photo_h":…,
  "intrinsics_fxfycxcy":[fx,fy,cx,cy],
  "intrinsics_provenance":"photo_camera_calibration_data|video_connection_scaled|none",
  "intrinsics_scale":{ "video_w":…,"video_h":…,"sx":…,"sy":…,"aspect_mismatch":false },
  "exposure_s":…, "exposure_provenance":"photo_exif_exposure_time|device_exposure_duration_at_completion|none",
  "photo_file_type":…, "photo_settings_unique_id":…, "flash_mode":0,
  "video_stream_unchanged":{ … 见下 … } }
```
- **内参两条路都在代码里**:优先 `AVCapturePhoto.cameraCalibrationData`(按 `intrinsicMatrixReferenceDimensions` 缩到实际像素);拿不到就用同一会话视频连接的 `kCMSampleBufferAttachmentKey_CameraIntrinsicMatrix` 按 `photoW/videoW`、`photoH/videoH` 缩。**哪条写在 `intrinsics_provenance` 里**。按 Apple 头文件,单摄下实际必然走第二条。
- 照片实际像素尺寸从**文件头**读(`CGImageSourceCopyPropertiesAtIndex`,只读头不解码),与 `resolvedSettings.photoDimensions` 同时写出,不一致时两个数都在。
- sidecar 写不出去时**把照片一并删掉** —— 不留"看起来有、其实没内参"的废片。

---

## 3. 视频流不降档的自证方法

三道,前两道是结构性的、第三道是运行期的:

1. **写 `activeFormat` 的顺序**:照片输出在 `beginConfiguration` 块内加,而 `device.activeFormat = f` 在 `commitConfiguration` 之后才写 ⇒ **我们是最后一个写 activeFormat 的人**,照片管线不可能把它改回去。
2. **只挑不换**:`maxPhotoDimensions` 只在 `device.activeFormat.supportedMaxPhotoDimensions` 里取面积最大的那一项,**绝不为照片去换 `activeFormat`**。代价是照片分辨率上限由"视频流要的那个格式"决定 —— 这是刻意取舍。`canAddOutput(photoOutput)` 为假时只记 `photoOutputNote = "can_add_output_false"`、继续跑 VIO,只让 `capture_photo` 返回 `-2`。
3. **运行期逐项比对**,写进每张 sidecar 的 `video_stream_unchanged`:
   - `configured` = 采集配置完成、`startRunning` **之前**的视频档快照;
   - `at_photo` = 这张照片完成时再取一次;
   - 比的字段:`active_format_w/h`、`active_format_subtype`、`active_format_binned`、`min/max_frame_duration_s`、`video_settings_w/h`、`intrinsic_delivery_enabled`、`active_stabilization_mode`;
   - 外加 `video_frames_offered_before/after`(两次之间视频流实际交付了多少帧 —— 拍照期间视频流是不是停了,在这里显形);
   - 结论落成布尔 `unchanged`。**降档了就会在这里显形,不需要人去猜。**
   - `CMTimeGetSeconds` 一律过有限性闸(NaN 会让整张 sidecar 写不出去,进而连坐删照片)。

🔴 **这三道全是"怎么证"的设计,不是"已经证了"**。真机上一张照片都没拍过(本轮不许开摄像头)。

---

## 4. 构建与 nm 输出

```
$ flutter build ios --release --no-codesign
Xcode build done.                                           70.1s
✓ Built build/ios/iphoneos/Runner.app (257.9MB)

$ nm -g --defined-only build/ios/iphoneos/Runner.app/Runner | grep pw_camera_slot
000000010143f3f0 T _pw_camera_slot_acquire
0000000101442d58 T _pw_camera_slot_capture_photo      ← 新
000000010143f5f4 T _pw_camera_slot_exposure           ← 本轮补导出
000000010143f52c T _pw_camera_slot_intrinsics
000000010143f7b0 T _pw_camera_slot_lock               ← 本轮补导出
0000000101442dd4 T _pw_camera_slot_photo_result       ← 新
000000010143f488 T _pw_camera_slot_release
000000010143f260 T _pw_camera_slot_start
000000010143f544 T _pw_camera_slot_stats
000000010143f358 T _pw_camera_slot_stop
000000010143f940 T _pw_camera_slot_unlock             ← 本轮补导出

$ xcrun dyld_info -exports … | grep camera_slot    # 11 个,与上表一一对应
```

Release 构建需要三个身份环境变量(仓内既有的生产闸,不是本轮加的):
```
PW_PRODUCT_SOURCE_MANIFEST_SHA256=$(sh tool/product_source_manifest.sh)
PW_DIAGNOSTIC_BUILD_ID=<label>   PW_VIO_SHADOW_MODE=off
```

其他自证:
- `flutter analyze lib/vio/ffi/pw_camera_photo_ffi.dart lib/vio/pose/camera_slot_ffi.dart test/pw_camera_photo_ffi_test.dart` → **No issues found**
- `flutter test test/pw_camera_photo_ffi_test.dart` → **7/7 通过**(记录解析 4 条 + 降级 3 条;降级那三条在主机上跑是**天然阴性对照**,符号本来就不可能在)
- `swiftc -typecheck -target arm64-apple-ios15.0`(PwCameraSlot.swift + PWJSONSafety.swift + PwXrslamLive 桩)→ 零 diagnostics

---

## 5. 🔴 路上撞到的两个**既有**缺陷(都不是本轮引入)

### (1) `PwXrslamLive.swift` 从来没进过 Runner target
`ios/Runner/PwXrslamLive.swift` 在 `b467ecc` 入库,但 `Runner.xcodeproj/project.pbxproj` 里**没有它的任何条目**(`grep -c PwXrslamLive` = 0,主仓与全部 13 个 worktree 一致为 0)。后果:
```
Swift Compiler Error (Xcode): Cannot find 'PwXrslamLive' in scope
ios/Runner/PwCameraSlot.swift:126:8 / :273:8
```
**阴性对照**:把本轮改动全 stash、在干净的 `f0b3a40` 上构建,报一模一样的两条错。已在 `4433da1` 用四行 pbxproj 条目修掉。

### (2) `-Wl,-exported_symbol` 白名单 —— 「绑定存在 ≠ 符号存在」第四例
pbxproj 的 `OTHER_LDFLAGS`(Debug/Profile/Release 三份)里有一张显式导出白名单。**它是排他的**:改前 `dyld_info -exports` 显示整个 app 只导出 **11 个符号**(5 个 `XRSLAM*` + 6 个 `pw_camera_slot_*`)。

- 我的两个新 `@_cdecl` 一开始只是 local `t`(`nm --defined-only` 能看到、`nm -g` 看不到)⇒ `DynamicLibrary.process()` 查不到。已加进三份配置。
- 同时发现 **`pw_camera_slot_exposure` / `_lock` / `_unlock` 三个既有符号也不在白名单里**,而它们的 Dart 绑定早就写好并在用(`camera_slot_ffi.dart:221`、`xrslam_session.dart`)。按门面的降级风格,它们只会静默返回 null,不报错。已在 `28ff7de` 单独一个提交里补上(便于独立 revert)。
- 🔴 **还没处理、需要人拍板**:`pw_xrslam_live_*`、`pw_imu_*`、`PWXrslamTransport*`、`pw_lepton_*`、`pw_jxl_*` 等一大批 Dart FFI 目标**同样不在白名单里** ⇒ 在 Release 产物里全部查不到。这意味着 Release 包里那些通路实际是关着的。本轮没动。

---

## 6. 真机验证要看什么(一条都没跑过)

1. **零 ARKit 出照片**:不启动 ARKit,`PwCameraSlot.start(width:1920,height:1440,fps:30)` → `PwCameraSlot.capturePhoto(id)` 返回 0 → 循环 `photoResult()` 直到拿到记录。沙盒 `Documents/pw_photos/` 下应有 `<id>.heic` + `<id>.json` 成对。
2. **视频流没被降档**(最要紧):看 sidecar 的 `video_stream_unchanged.unchanged` 是否为 `true`,以及 `configured` 与 `at_photo` 两张快照逐项相等;`video_frames_offered_after - before > 0` 说明拍照期间视频流没停。任何一项不等 = 照片输出动了视频流,本设计的前提就不成立。
3. **照片分辨率**:`image_w/h` 与 `resolved_photo_w/h` 是否一致;是不是 `activeFormat.supportedMaxPhotoDimensions` 的最大项。若只拿到 1920×1440,说明这个 VIO 格式不支持更高的静照 —— 那是取舍不是 bug,但要记下来。
4. **内参 provenance**:`intrinsics_provenance` 预期是 `video_connection_scaled`(单摄下 Apple 不给照片标定)。若出现 `none`,说明视频连接的逐帧内参没到(检查 `intrinsic_delivery_enabled` 与 `active_stabilization_mode` —— 防抖开着内参就不下发)。`intrinsics_scale.aspect_mismatch` 必须是 `false`。
5. **时间戳同域**:`t` 应与同期视频帧 PTS 处在同一量级(开机时长量级),差值是相机管线延迟(几十 ms);若差出成千上万秒,说明不同域,不能拿来和 VIO 位姿配。
6. **曝光**:`exposure_provenance` 预期 `photo_exif_exposure_time`;`exposure_s` 应与同期 `pw_camera_slot_exposure` 读到的视频曝光同量级。
7. **连拍不丢**:连发 5 个 requestId,`photoResult()` 应按完成顺序全部取到;看 `NSLog` 有没有 `photo results dropped`。
8. **不泄漏**:拍照前后 `pw_camera_slot_stats` 的 `acquired - released` 仍恒为 0 或 1。

---

## 7. 已知残留 / 没做的

- **照片连接的防抖没有显式关**。依据是 `AVCapturePhotoOutput.h:348` —— OIS 由 `maxPhotoQualityPrioritization` 控制,我们已钉 `.speed`。但 `photoOutput.connection(with:.video)?.preferredVideoStabilizationMode` 没显式置 `.off`(视频连接那条早就置了)。5 行可补,真机上先看 sidecar 里内参的一致性再决定。
- **`AVCapturePhotoOutput` 在 `start()` 里无条件装**,哪怕这一轮不打算拍照。代价是占一点 ISP 静照管线资源;好处是符合 Apple "set before startRunning" 的要求(懒加载会触发头文件说的 "lengthy reconfiguration")。
- 24 MP 档(`(5712,4284)`)按头文件"only serviced as 24MP when opted-in to `autoDeferredPhotoDeliveryEnabled`";我们没开延迟交付,所以若设备给出这一项会被服务成更小的图 —— 不会报错,实际尺寸从文件头读,sidecar 里如实写。
- 没跑全量测试套件(仓里基线本就有 11–12 个既有失败),只跑了新增那个文件。
- 磁盘:开工 8.4 GiB → 完工 ~2.8 GiB(Xcode/Pods/Runner.app 产物)。worktree 已删,构建产物随之消失。
