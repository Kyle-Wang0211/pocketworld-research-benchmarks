# Android VIO 喂料链接线 —— 交付报告

日期 2026-09-22 · 仓 `~/Developer/pocketworld` · 分支 `feat/android-vio-feed`
· commit **`001087c04506a2501734dacc04ddc9d642534739`**(短 `001087c`)· 已 push 到 origin

---

## 0. 一句话结论

**链条接上了,编译全绿,但一帧都没真正到过 XRSLAM —— 本机没有 Android 设备也没有模拟器镜像,
所有证据都是链接级与类型级。**

此前的断点(agent4 报告 §6(b)):Kotlin / JNI / `.so` 三样都在,`PwXrslamTransport` **全仓零引用**;
IMU 读了从不 push;**相机源完全不存在**。现在三条都补上了,并且第一次给 Android 侧留下了编译证据
——`android_ready/README.md` 那句「**No Kotlin has ever been compiled**」到此为止。

🔴 同时补上两个此前不存在的东西:一份能重跑的 `.so` 构建配方 + 收据,和一次真正的 Kotlin 编译。
后者第一次跑就抓到一个真 bug(见 §5)。

---

## 1. 定位:文件在哪个仓、哪个目录

`grep -rn "PwXrslamTransport" ~/Developer/pocketworld ~/Developer/pw_android_probe ~/Developer/arloopbench` 的结果:

| 仓 | 结论 |
|---|---|
| `~/Developer/pocketworld/android_ready/` | ✅ **唯一的真 Android 工作**。Kotlin / JNI / CMake / 预编译 `.so` 全在这里 |
| `~/Developer/pw_android_probe` | ⚰️ 零命中(Vulkan/WGSL 确定性探针,与 SLAM 无关) |
| `~/Developer/arloopbench` | 只有 iOS 侧对 `PwXrslamTransportCore` 的引用 + `sync_from_production.sh` 的一致性检查;**没有 Android** |

`android_ready/native/xrslam/CMakeLists.txt:24` 编的确实是与 iOS 同一份
`vendor/xrslam/transport/PwXrslamTransportCore.cpp` —— 已实测(见 §4 构建日志里第 2 个编译单元的路径)。

---

## 2. 文件清单

### 新增(3 个 Kotlin + 2 个脚本 + 1 份收据)

| 文件 | 行数 | 做什么 |
|---|---|---|
| `~/Developer/pocketworld/android_ready/kotlin/com/pocketworld/capture/PwVioCameraSource.kt` | 381 | camera2 + `ImageReader`(`YUV_420_888` 取 Y 平面)。此前**完全不存在**的那一环 |
| `~/Developer/pocketworld/android_ready/kotlin/com/pocketworld/capture/PwXrslamFeed.kt` | 621 | `ios/Runner/PwXrslamLive.swift` 的逐结构移植:有界入队 + 串行 worker + 时基自证 |
| `~/Developer/pocketworld/android_ready/kotlin/com/pocketworld/capture/PwDeviceCalibration.kt` | 273 | 逐机型 `p_bc`/`q_bc`/`c` 表 + 三态 provenance + device yaml 生成。**表是空的** |
| `~/Developer/pocketworld/android_ready/native/xrslam/build_transport.sh` | 88 | NDK+cmake 直编 `.so`,带 4 道闸(不需要 Gradle) |
| `~/Developer/pocketworld/android_ready/scripts/compile_kotlin_check.sh` | 82 | kotlinc 对 `android.jar`+`flutter.jar` 的类型检查与字节码生成 |
| `~/Developer/pocketworld/android_ready/native/xrslam/transport_build_receipt.json` | 60 | `.so` 的构建收据(工具链版本、源码 sha、导出符号、四道闸结果) |

### 修改

| 文件 | 改了什么 |
|---|---|
| `android_ready/kotlin/com/pocketworld/capture/PwXrslamTransport.kt` | 补 3 个 `external fun`(`nativeCreateWithCameraTimeOffset` / `nativeGetLastTimestampTrace` / `nativeGetCounters`)+ 公共包装 + `STREAM_*` 常量。`System.loadLibrary` 从 `companion object { init }` 挪进实例 `init`(因为新加的 `companion object Streams` 不能与原来那个并存) |
| `android_ready/native/xrslam/PwXrslamTransport.cpp` | 对应补 3 个 JNI 出口(只 marshalling,零判断) |
| `android_ready/kotlin/com/pocketworld/capture/PwImuSource.kt` | `start()` 多一个可选 `externalHandler`:非 null 时**不起自己的线程**,两条 IMU 流挂到调用方给的串行 handler 上。传 null 时行为逐字不变 |
| `android_ready/kotlin/com/pocketworld/capture/PwCapturePlugin.kt` | 补 6 个 MethodChannel 入口:`startVio` / `stopVio` / `vioStats` / `vioTimebase` / `vioTiming` / `vioLatestPose` / `vioSelection`。喂料链从这里被真正调起来 |
| `android_ready/kotlin/com/pocketworld/capture/PwExitInfoReader.kt` | 🔴 去掉 `i.subReason` —— 编译不过,详见 §5 |
| `android_ready/gradle/app-build.gradle.kts.snippet` | 补 `sourceSets`(此前 `android_ready/kotlin` 根本不参与构建);`ndkVersion` r28 → **r29**(与两份收据对齐);把已成死配置的 `defaultConfig.externalNativeBuild` 注释掉并写明原因 |
| `android_ready/native/xrslam/libs/arm64-v8a/libpw_xrslam_transport.so` | **重编替换**。旧的(8 月,115 KB)只导出 5 个 JNI 符号;新的(38 KB,strip 过)导出 8 个。sha256 `f9fb09efacaf75a0bb431dee24a09bef2f06f43551dff63a331c66f43bf0db4b` |
| `android_ready/README.md` | 三处过期陈述改掉 + 新增「What the first compile caught」一节 + API provenance 表纠错 |
| `test/vio/ffi/xrslam_official_replica_contract_test.dart` | +3 组断言,断的是**引用关系**不是文件存在 |
| `android_ready/.gitignore` | 忽略两个离线编译产物目录 |

---

## 3. 时间戳换算的依据

### 公式

```
t_canonical = CaptureResult.SENSOR_TIMESTAMP
            + CaptureResult.SENSOR_EXPOSURE_TIME        / 2
            + CaptureResult.SENSOR_ROLLING_SHUTTER_SKEW / 2
            ( + 每机常量 c,由传输层在 Create 时施加,不在喂料层加 )
```

实现在 `PwXrslamFeed.offerFrame()`(worktree 里 `android_ready/kotlin/.../PwXrslamFeed.kt`),
`c` 走 `PWXrslamTransportCreateWithCameraTimeOffset` —— **与 iOS 同一个 C 入口**。

### 每一项的出处

| 项 | 依据 |
|---|---|
| `SENSOR_TIMESTAMP` 是**首行曝光起点** | camera2 官方文档口径(与 `PwCameraProbe.frameMetadata` 的既有注释一致) |
| 加 `exposure/2 + skew/2` | ① Huai arXiv 2001.00470 §IV.B:修正是 "subtracting half of the sum of [rolling shutter + exposure]"(我们是加到起点上,等价);② 我们自己的跨端契约 `~/Developer/xrslam/xrslam-interface/include/XRSLAM.h:94-150` 条目 09 + `XRSLAMManager.cpp:92-99` 的换算就是 `+0.5·exposure+0.5·readout` |
| 为什么比 iOS 多一项 `skew/2` | iOS 不公开卷帘读出时间,只能连同管线固定延迟一起塞进 `c`;Android **公开** `SENSOR_ROLLING_SHUTTER_SKEW`(API 21),所以能算的部分就要算出来,`c` 里只剩管线固定延迟 |
| 两个键是 **optional** | `SENSOR_EXPOSURE_TIME` / `SENSOR_ROLLING_SHUTTER_SKEW` 都是 optional key。缺哪个就按 0 计**并计数**(`timebase()` 第 12/13 项),不伪造、不丢帧 |
| IMU 时间戳 | `SensorEvent.timestamp`,`CLOCK_BOOTTIME`。`PwImuSource` 原样透传 |
| 时钟域 | `CaptureResult.SENSOR_TIMESTAMP` 只有在 `SENSOR_INFO_TIMESTAMP_SOURCE == REALTIME` 时与 IMU 同域;`UNKNOWN` 时文档原话 "monotonic but not comparable to timestamps from other subsystems"。🔴 **本层不自己估这个偏移** —— 估计量(Cristian 最窄窗 best-of-N + 单调性否决)早就在 `android_ready/dart/pw_android_capture/lib/src/clock_offset.dart` 里且有单测,README 的规矩是「判断放 Dart,Kotlin 只搬运」。调用方把结果作为 `startVio` 的 `cameraClockOffsetNs` 传进来;REALTIME 机器传 0。传了什么、实际加了多少,`vioTimebase` 如实报出 |

### 运行期自证(抄 iOS `timebase(into:)`)

`PwXrslamFeed.runOneFrame()` 推完当帧立刻从 C 账本读 `PWXrslamTimestampTrace`
(worker 串行且只有这里推相机 ⇒ 读到的必是本帧),两条残差**必须恒 0**:

- `|trace.raw_timestamp − 我们推的 canonical|`
- `|(trace.effective − trace.raw) − trace.applied_offset|`

不为 0 ⇒ `Log.e` 「本场归因作废」。`vioTimebase` 返回 15 个 double,**前 12 项与 iOS 逐位对应**,
后 3 项是 Android 独有的元数据缺失计数(iOS 没有 skew 这个键)。

---

## 4. 编译输出

### (a) JNI + 跨端 C++ 传输层 —— NDK r29 + cmake + ninja

命令:
```
ANDROID_NDK_HOME=/opt/homebrew/share/android-ndk \
  android_ready/native/xrslam/build_transport.sh
```

输出(节选,四道闸全过):
```
== (0) toolchain ==
Android (13989888, +pgo, -bolt, +lto, -mlgo, based on r563880c) clang version 21.0.0
  (https://android.googlesource.com/toolchain/llvm-project 5e96669f06077099aa41290cdb4c5e6fa0f59349)
cmake version 4.2.3
1.13.2
== (1) configure + build ==
[1/3] Building CXX object CMakeFiles/pw_xrslam_transport.dir/PwXrslamTransport.cpp.o
[2/3] Building CXX object .../vendor/xrslam/transport/PwXrslamTransportCore.cpp.o
[3/3] Linking CXX shared library libpw_xrslam_transport.so
libpw_xrslam_transport.so: ELF 64-bit LSB shared object, ARM aarch64, version 1 (SYSV),
  dynamically linked, BuildID[sha1]=f1bd9935b8b97cb01401630e0f14934b3ac6209d
== (2) 符号闸:JNI 出口 vs Kotlin external 声明 ==
  (exported 8 行 == declared 8 行,diff 空)
✅ 符号闸通过 (8 个)
== (3) 16 KB 页对齐 ==
PASS  aarch64  libpw_xrslam_transport.so  min PT_LOAD align=0x4000 (16 KB) over 3 segments
---- 1 checked, 0 failed, 0 skipped
== (4) 未定义符号必须全部由核心库提供 ==
XRSLAMCreate / XRSLAMDestroy / XRSLAMGetResult / XRSLAMPushSensorData / XRSLAMRunOneFrame
✅ 引擎符号全部由 libxrslam_generic_4beb1a9.so 提供
```

🔴 `clangRevision 5e96669f...` 与 `core_build_receipt.json` 里引擎核心用的**是同一个**,
NDK 版本也都是 `29.0.14206865` —— JNI 与引擎核心同工具链档。

### (b) Kotlin —— kotlinc 2.4.20

命令:`android_ready/scripts/compile_kotlin_check.sh`

```
== toolchain ==
info: kotlinc-jvm 2.4.20 (JRE 27)
android.jar: /Users/kaidongwang/Library/Android/sdk/platforms/android-34/android.jar
flutter.jar: /opt/homebrew/share/flutter/bin/cache/artifacts/engine/android-arm64/flutter.jar
== compile ==
(1 条 warning:PwExitInfoReader.kt:56 elvis 多余 —— 既有代码,不是本次改动)
== produced classes ==  23 个 .class(PwXrslamFeed / PwVioCameraSource / PwDeviceCalibration
                        / PwXrslamTransport / PwCapturePlugin / … 全部)
== JNI 声明 vs .so 导出 ==
✅ 编出来的 class 里的 native 方法与 .so 导出一一对应
✅ kotlinc 全绿
```

第二道交叉核对用的是 `javap -p` 读**编出来的字节码**里的 `native` 方法,与 `nm -D` 读
`.so` 的导出比 —— 两边都不是「读源码里的声明」。

### (c) Dart

```
$ flutter test test/vio/ffi/xrslam_official_replica_contract_test.dart
00:02 +15: All tests passed!          # 12 既有 + 3 新增

$ cd android_ready/dart/pw_android_capture && dart analyze && dart test
(770 issues,全部 info 级;grep 过 error/warning:0 条)
00:00 +88: All tests passed!
```

### (d) Gradle —— **没跑,跑不了**

仓里**没有 `android/` 目录**(Flutter Android app 从未创建),`manifest/` 与 `gradle/` 仍然是
`.snippet` 文本。要跑 Gradle 就得先 `flutter create --platforms=android .` 并把 snippet apply
进去,那超出「接线 + 编译」的范围,而且会拉 Gradle 发行版 + AGP + 依赖(磁盘只剩约 4 GB,
且任务给的 Gradle 缓存上限是 2 GB)。**如实报:Gradle 从未跑过。**

kotlinc + NDK-cmake 这条路覆盖了本次写的 100% 代码的类型检查与链接,抓不到的是:
资源、manifest 合并、R8/proguard、以及任何运行期行为。

---

## 5. 🔴 第一次真编 Kotlin 就抓到的 bug(既有代码)

`PwExitInfoReader.kt:58`:

```
error: unresolved reference 'subReason' on receiver of type 'ApplicationExitInfo'
            m["subReason"] = i.subReason
```

`ApplicationExitInfo.getSubReason()` **不在公开 SDK 里**(`@hide`/`@SystemApi`),
`android-34/android.jar` 里根本没有这个方法。原代码用 `Build.VERSION_CODES.S` 做版本闸 ——
**运行期版本闸拦不住一个编译期就不存在的符号**。`README.md` 的 *API provenance* 表把它记成
「API 31,guarded」,那一行是错的,已改。

处理:**去掉,不用反射绕**。反射能编过,但在设备上仍可能被 hidden-API 黑名单拦下,
那只是把编译错误换成运行期静默返回 null。Dart 侧 `ExitTriage` 的判据本来就是 `description`
子串(README 自己写着 "The description substring is the only discriminator"),不依赖它。

这正是旧 README 预言的「a typo would only surface at the first Gradle build」那一类错 ——
只不过在 `kotlinc` 上就显形了,便宜得多。

---

## 6. 与 iOS 参考实现的对照 / 四处显式差异

复刻的性质(每条都能在 `ios/Runner/PwXrslamLive.swift` 找到对应):

| 性质 | iOS | Android |
|---|---|---|
| 三条流共享一个**串行到达上下文** | `PwCameraSlot` 的 `queue`,IMU 用 `OperationQueue.underlyingQueue` 绑上去 | `PwXrslamFeed.arrivalHandler`(一条 `HandlerThread`);`ImageReader.setOnImageAvailableListener` 与 `PwImuSource.start(externalHandler=)` 都挂它 |
| 算法只在**另一条串行 worker** 上跑 | `workQueue` | `pw-vio-work` HandlerThread |
| 回调只做**有界入队**,绝不等算法 | `onCameraFrame`/`enqueueImu` | `offerFrame`/`enqueueImu` |
| 在途上限 帧 2 / IMU 400 | 逐字相同 | 逐字相同 |
| 陀螺与加速度**分开推、各带自己的时间戳、先陀螺后加速度** | `onGyro`/`onAccel` | `onImuSample`;先后由 `PwImuSource.start()` 的 `wanted` 列表(陀螺在前)+ 共享 handler 保证 |
| push→RunOneFrame→GetResult **一次原子调用** | `PWXrslamTransportPushCameraAndRunRaw` | 同一个 C 入口 |
| 只有 `TRACKING_SUCCESS`(1)才更新位姿 | `XRSLAM_iOS.mm:171` | 同 |
| 计数从 C++ 账本读,不在宿主语言合成 | `PWXrslamTransportGetCounters` | `nativeGetCounters` |

**四处显式差异(都是平台事实,不是设计选择):**

1. **`channel=1`(luma8)而不是 iOS 的 `channel=4`(BGRA)。**
   camera2 `YUV_420_888` 的 Y 平面就是 8 位灰度、`pixelStride` 按规范恒为 1,
   直接是引擎要的 `CV_8UC1`(`~/Developer/xrslam-4beb1a9-thr/xrslam-interface/src/XRSLAMManager.cpp:143-145`
   @4beb1a9:`channel == 1` ⇒ `cv::Mat(rows, cols, CV_8UC1, image->data, image->stride)`,
   **不做 cvtColor**)。比 iOS 少一次转换。`pixelStride != 1` 或非 direct buffer 时
   **计数拒绝**(`framesRejectedLayout`),不静默错像素。

2. 🔴 **加速度原值直推,不乘 iOS 那个 `-9.80665`。**
   iOS 乘它是因为 CoreMotion 的 `CMAcceleration` 单位是 **g** 且符号与比力相反
   (平放屏幕朝上 z ≈ −1.0 g)⇒ ×(−9.80665) 得 +9.80665 m/s²。
   Android `TYPE_ACCELEROMETER` 文档口径是 **m/s²** 且平放屏幕朝上 z ≈ **+9.81**
   ⇒ 两端换算后同号同量纲,Android 侧不需要标度也不需要取反。
   ⚠️ **这是本次唯一一处不能在本机证伪的换算**(无 Android 设备)。
   `vioTiming` 报 `lastAccelMagnitude`:静置时应 ≈ 9.8;接近 1.0 说明单位错,
   z 号相反说明符号错。**报事实,不做判定。**

3. **多一项 `skew/2`** —— 见 §3。

4. **时钟域偏移由 Dart 传入** —— 见 §3 末。

---

## 7. 逐机型标定表:空的,而且必须空

`PwDeviceCalibration`:

- `TABLE: Map<String, Extrinsic> = emptyMap()` —— `p_bc`/`q_bc` 一个都没有
- `CAMERA_TIME_OFFSET_SECONDS: Map<String, Double> = emptyMap()` —— 每机常量 `c` 一个都没有
- 查不到 ⇒ 返回 `placeholder`(单位四元数 + 零平移),provenance = `PLACEHOLDER`
- `logProvenance()` 在 `startVio` 时打 `Log.w`:
  `🔴 PLACEHOLDER calibration in use: … -- this run MUST NOT report absolute scale.`
- `startVio` 的返回 map 里带 `placeholders: [...]`,上层拿得到

**为什么不抄 iOS 的值**:iOS 那 18 份是上游 `xrslam-ios/visualizer/configs/` 里逐机型标定过的;
Android 上游 **0 份**。iOS 的 `q_bc` 对 18 款 iPhone 全相同(Apple 全系轴系一致),
Android 没有这个保证 —— camera2 有 `LENS_POSE_ROTATION`/`LENS_POSE_TRANSLATION`(optional key),
那才是这台机器自己的答案。`fromCameraPose()` 写了,但**默认不启用**:
camera2 的坐标约定与 XRSLAM 的 `q_bc`/`p_bc` 是否同一口径(方向 / `LENS_POSE_REFERENCE` /
平移是 c→b 还是 b→c)**没在机器上核过**,调用方必须显式传 `trustCameraPose = true`。

契约测试钉死了「表是空的」这条(`Android per-device calibration table is empty and
provenance-tagged`)——**要加表项就得同时改断言并写出处**。

`buildDeviceConfigYaml()` 逐字段对齐 iOS 的 `XrslamConfigBuilder.buildDeviceConfigYaml()`
(`lib/vio/ffi/xrslam_config.dart:378-421`),包括那几条坑的注释(`noise` 必须是 2×2 矩阵、
四个 `cov_*` 逐字沿用上游 18 份 iPhone yaml)。一处**刻意不同**:
`camera_distortion_flag` 跟着 `LENS_DISTORTION` 走 —— 因为 `applyVioTuning` 把
`DISTORTION_CORRECTION_MODE` 关掉了,图像是**带畸变**的,iOS 那边写 0 的前提
(「ARKit 交出的是已校正帧」)在 Android 上不成立。

---

## 8. 分辨率 / 帧率 / 不用 LiDAR

- `PwVioCameraSource.MIN_WIDTH = 1920` / `MIN_HEIGHT = 1440`(产品硬下限)。
  选型:优先精确 1920×1440 → 否则**面积最小的 ≥1920×1440** → 都没有就取最大的
  并 `Log.e` + `Selection.meetsMinimum = false`。**不静默降档。**
- 帧率:`CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES` 里取**最高上界**,同上界候选里优先**定帧**区间
  `[x,x]` —— 可变区间会让曝光在暗处拉长,而曝光时长直接进时间戳换算且运动模糊直接打特征。
- **零 LiDAR/ToF**:契约测试断言 `PwVioCameraSource` 不含 `DEPTH16` / `ImageFormat.DEPTH`;
  manifest snippet 原本就写着 "Deliberately absent: nothing here requests LiDAR/ToF depth, by policy"。
- 丢帧归因:用 `acquireNextImage()`,**不用 `acquire`-latest 那个重载**(后者静默丢帧,
  账就记在平台里,分不清「引擎吃不下」和「我们没来取」)。契约测试把那个名字禁掉了。

---

## 9. 没做到的 / 缺什么才能真机验证

1. **没有 Android 真机,也没有模拟器。**
   模拟器要装 system-image(约 1.5 GB)+ emulator 包,而且**没有 app 可装**
   —— 仓里没有 `android/` 目录。磁盘只剩约 4 GB。没做,也没伪造任何运行数据。
2. **Gradle 从未跑过**,snippet 仍未 apply(见 §4d)。
3. **一帧都没到过 XRSLAM。** 时基自证的两条残差、`framesDropped`、`lastAccelMagnitude`、
   位姿 —— 全都是**代码里有出口但没有读数**。
4. **加速度符号/单位映射是文档论证不是实测**(§6 差异 2)。
5. **逐机型 `p_bc`/`q_bc`/`c` 全是 PLACEHOLDER** ⇒ 这条链跑出来的结果**不得报绝对尺度**。
6. `LENS_INTRINSIC_CALIBRATION` 是 **pre-correction active array** 像素,不是输出流像素,
   换算到所选分辨率要用 crop region —— **刻意没在 Kotlin 里做**(按 README「判断放 Dart」的规矩),
   `startVio` 收的是 Dart 算好的 `fx/fy/cx/cy`。**Dart 侧那个换算还没写。**

### 真机验证的最小前置清单

| # | 要做什么 | 为什么挡着 |
|---|---|---|
| 1 | `flutter create --platforms=android .` + apply `manifest/` 与 `gradle/` 两个 snippet | 没有 app 就没有 Gradle、没有 APK、没有可装的东西 |
| 2 | Dart 侧写 `LENS_INTRINSIC_CALIBRATION` → 输出流像素的换算,并调 `startVio` | 现在 `fx/fy/cx/cy` 缺省是 0,yaml 会是废的 |
| 3 | Dart 侧把 `clock_offset.dart` 的估计量接到 `startVio(cameraClockOffsetNs:)` | `SENSOR_INFO_TIMESTAMP_SOURCE == UNKNOWN` 的机器不换算就是**跨了两个时钟** |
| 4 | 一台 arm64 Android 真机 + `CAMERA` 运行期授权 | 相机源不申请权限(刻意) |
| 5 | 跑一次后读 `vioTimebase` | 两条残差必须恒 0;不为 0 整场归因作废 |
| 6 | 静置读 `vioTiming` 的 `lastAccelMagnitude` | 核 §6 差异 2 那条唯一未证伪的换算 |
| 7 | 标定一台机的 `p_bc`/`q_bc`/`c`,填进 `PwDeviceCalibration` 并改契约断言 | 在此之前不得报绝对尺度 |

🔴 **铁律照旧**:没全面持平/超越 ARKit 之前不上生产。本次交付的是**喂料链**,不是质量证据。

---

## 10. 交付

- 分支 `feat/android-vio-feed`,commit **`001087c`**,已 push 到
  `https://github.com/Kyle-Wang0211/pocketworld.git`(用户自己的仓)
- 16 files changed, 2025 insertions(+), 33 deletions(-)
- worktree 已用完移除,主仓工作树未被本次任务改动(`pubspec.lock` 的临时 churn 已 revert)
- 未碰 iPhone、未开任何摄像头、未写 `~/.claude/`、未编造任何标定值
