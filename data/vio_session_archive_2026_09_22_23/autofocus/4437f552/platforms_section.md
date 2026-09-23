## 3. 四端手动镜头接口矩阵(全部经官方文档原文核过)

| | **iOS** AVFoundation | **Android** camera2 | **HarmonyOS** `@ohos.multimedia.camera` | **Web** W3C Image Capture |
|---|---|---|---|---|
| **A. 能否定位** | ✅ `setFocusModeLocked(lensPosition:completionHandler:)`(iOS 8+),前提 `isLockingFocusWithCustomLensPositionSupported`(iOS 10+)+ `lockForConfiguration()` | ✅ `CONTROL_AF_MODE = OFF` + `LENS_FOCUS_DISTANCE`(API 21);需 `MANUAL_SENSOR` 能力(FULL 必含,LIMITED 需查)且 `LENS_INFO_MINIMUM_FOCUS_DISTANCE > 0`;LEGACY 只能设 0(无穷远) | ✅ `ManualFocus.setFocusDistance(distance)`,门槛 `isFocusDistanceSupported()` + `FocusMode.FOCUS_MODE_MANUAL` | ⚠️ 规范有:`applyConstraints({focusMode:'manual', focusDistance:x})` |
| **B. 单位/语义** | **0…1 归一化**,`0.0` = 能对焦的**最近**,`1.0` = **最远**(且「1.0 不代表无穷远」),默认 1.0 | **屈光度 1/m**,`0.0f` = **无穷远**,越大越近;钳到 `[0, minimumFocusDistance]`。**方向与 iOS 相反** | **0…1 归一化**,`0.0` = 最近、`1.0` = 最远,默认 1.0。**与 iOS 同向** | `double`,规范说「**usually** represents distance in **meters**」;能力表 `{min,max,step}` |
| **C. 到位回调** | ✅ **`completionHandler(CMTime)`** —— 时间戳 = 第一帧已应用全部设置的 buffer;多次调用 FIFO。**四端里唯一的「镜头已到位」硬信号** | ❌ 无 completion;逐帧看 `LENS_STATE` MOVING→STATIONARY;文档明说「may take several frames」 | ❌ 同步 `void`,**无回调**;`focusStateChange` **仅自动对焦模式触发**,手动模式拿不到 | ⚠️ `applyConstraints()` 的 Promise 只表示约束被接受,**不承诺镜头已到位** |
| **D. 读当前位置** | `lensPosition`(只读,**KVO**)、`isAdjustingFocus`(KVO);非逐帧 | ✅ **逐帧在 CaptureResult**:`LENS_FOCUS_DISTANCE`、`LENS_FOCUS_RANGE`(near/far 屈光度对)、`LENS_STATE` | `getFocusDistance()` 同步轮询,非逐帧 | `getSettings().focusDistance`,轮询 |
| **E. 步进/延迟** | ❌ 全未文档化;不支持的值抛异常 | 无最小步进;`LENS_STATE` 有定义;无到达时间上限 | ❌ 全未文档化 | `MediaSettingsRange.step` 有定义;延迟无规范文字 |
| **F. 模式组合** | `setFocusModeLocked` 会把 `focusMode` 置 `.locked`,锁后仍可 KVO 读值;无闪帧说明 | `AF_MODE_OFF`:"The auto-focus routine does not control the lens; android.lens.focusDistance is controlled by the application";OFF 下 `CONTROL_AF_STATE` 恒 INACTIVE | `FOCUS_MODE_MANUAL`「不支持对焦点设置」;`getFocusDistance()` 与模式无关 | 规范只在示例里把 manual 与 focusDistance 一起下发;非 manual 下行为未规定 |
| **G. 标定等级** | ❌ **无标定**:"doesn't correspond to an exact physical distance, nor does it represent a consistent focus distance from device to device" | ✅ **三档** `LENS_INFO_FOCUS_DISTANCE_CALIBRATION`:UNCALIBRATED / APPROXIMATE(屈光度但不可重复)/ CALIBRATED(屈光度且对应真实物理距离) | ❌ 无标定说明,纯归一化 | ❌ 无保证 |
| **可用性红线** | 稳:iOS 8+ | 稳:API 21+,但要查能力 | 🔴 **`ManualFocus` 在 API 12–20 是系统接口(仅系统应用,错误码 202 Not System Application),API 24 / HarmonyOS 6.1.1(2026-05-26)起才开放**;且**只混入 `PhotoSession`,`VideoSession` 不含 ManualFocus** | 🔴 **只有 Chromium 实现**(Chrome/Chrome Android **76+**);**WebKit 的 IDL 里 focusMode/focusDistance 只存在于 FIXME 注释 ⇒ Safari(含 iOS)不支持**;Firefox 的 webidl 里没有这两个成员 |

**关键原文**(链接见 §7):
- iOS `lensPosition`:"The range of possible positions is 0.0 to 1.0, with **0.0 being the shortest distance at which the lens can focus and 1.0 the furthest**. Note that 1.0 doesn't represent focus at infinity. The default value is 1.0."
- iOS `setFocusModeLocked` 的 handler:"The system passes a time value that matches that of **the first buffer to which its applied all settings**. It synchronizes the timestamp to the device clock…"
- Android 标定:"APPROXIMATE and CALIBRATED devices report the focus metadata in units of diopters (1/meter), so **0.0f represents focusing at infinity**…";UNCALIBRATED:"…do not correspond to any physical units… **0.0f still represents farthest focus**"
- Android `LENS_FOCUS_DISTANCE`:"…it may take **several frames** before the lens can move to the requested focus distance. While the lens is still moving, android.lens.state will be set to MOVING."
- HarmonyOS `setFocusDistance`:"…in the range [0.0, 1.0], where **0.0 indicates the shortest achievable focus distance and 1.0 indicates the longest focus distance**. The default value is 1.0."(`arkts-apis-camera-ManualFocus.md`,API 24+)
- Web:"Focus distance is a numeric camera setting that controls the focus distance of the lens. The setting **usually represents distance in meters** to the optimal focus distance."

**对我们的三条后果**
1. **单位三套、方向两套**(iOS/HarmonyOS 归一化近→远 = 0→1;Android 屈光度远→近 = 0→大;Web 米)⇒ 算法内部必须用**一个统一的内部标度**,四端各写一个薄薄的换算 + 标度校准(libcamera 的 `cfg_.map` 分段线性就是干这个的,可直接沿用它的结构)。
2. **只有 iOS 有「到位回调」**;Android 靠 `LENS_STATE`,HarmonyOS 和 Web **什么都没有** ⇒ 跨端统一的等待策略只能是 libcamera 那套「**等 N 帧**」(`step_frames`),iOS/Android 上再用回调/状态提前结束。
3. 🔴 **现状锁的 `lensPosition = 0.835` 偏在远端**(0=最近,1=最远)。拍 20–30 cm 小物体本该往 0 那一侧走。这是「一直无法对焦」最直接的一条解释 —— 但**本调研没做实测,不下断言**,仅指出文档语义与当前取值的方向矛盾(验收表 A 会直接量出来)。

**Flutter `camera` 插件(0.12.1)**:只有 `setFocusMode(FocusMode.auto/locked)` 与 `setFocusPoint`,**没有任何 lensPosition / focusDistance 接口** ⇒ 四端都得走我们自己的平台通道(iOS 已有 `PwCameraSlot`)。CameraX `CameraControl` 同样没有手动焦距,只能经 `@ExperimentalCamera2Interop` 下发 `CaptureRequest.Key`。
