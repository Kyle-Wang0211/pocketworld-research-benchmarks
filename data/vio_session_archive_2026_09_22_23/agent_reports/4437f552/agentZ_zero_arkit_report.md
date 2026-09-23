# 零 ARKit 采集路径(开关 ON 时一次 ARSession 都不起)

日期 2026-09-22 · 分支 `feat/ios-zero-arkit-capture` · 起点 `feat/vio-consumption-flag`@`5f3a223`

---

## 0. 一句话

**开关 ON 时 ARKit 通道上一条消息都没有**(单测带阴性对照钉死:OFF 时同一条通道上**有**
`startSession`,ON 时零);相机归 `PwCameraSlot`(经新加的租约闸),位姿归 XRSLAM 并
**换到了 ARKit 的 y-up 系**,内参/曝光来自我们自己的相机流,照片按另一位 agent 的签名调。

**OFF 逐位不变**:12 帧回放的位姿序列 sha256 仍是
`b3362fb59f7793e18facfb6d84a6b5bf7104088bb379a6b84711340ae8f905ad`
(上一刀在改 `lib/` 之前算出来的金值,本刀一位没动)。

🔴 **零运行证据**:全程没开摄像头、没碰 iPhone。ON 这条臂**没在真机上跑过一次**。
✅ 但**真机 Release 构建跑通了**(`Runner.app` 258 MB),并用 `nm -g` 核实了
44 个导出符号全是 `T` —— 那一步还抓出了一个我自己的 pbxproj UUID 撞车(§7.4)。

---

## 1. commit(2 个是我的,3 个是 cherry-pick)

```
7206969  ios 导出白名单放开到 44 个 + 修 UUID 撞车 + 照片换成真门面   ← 本刀
988863e  补导出 pw_camera_slot_exposure/_lock/_unlock        ← cherry-pick 28ff7de(照片 agent)
72046c9  我们自己的相机栈补上高清拍照 + 逐张内参 sidecar      ← cherry-pick 405eca6(照片 agent)
20ee298  修 PwXrslamLive.swift 从未加进 Runner target        ← cherry-pick 4433da1(照片 agent)
9684457  ios 采集页:开关 ON 时完全不启动 ARKit               ← 本刀主体
8ea3595  official_capture: 整体等比缩放机制 + provenance     ← cherry-pick 145d8a6(尺度 agent)
--------  以上基于 5f3a223（消费层接线)
```

`git diff --stat 5f3a223..HEAD`:24 个文件,约 +4700 / −80。

---

## 2. 改动清单

### 2.1 新增 —— 我写的(6 个 lib 文件 + 5 个测试 + 1 个 Swift)

| 文件 | 行 | 做什么 |
|---|---:|---|
| `lib/vio/pose/xrslam_world_axis.dart` | 136 | **换轴**:XRSLAM z-up → ARKit y-up |
| `lib/vio/pose/xrslam_tracking_state.dart` | 181 | **状态映射表** + confidence + 三个禁用词 |
| `lib/vio/pose/zero_arkit_camera_gate.dart` | 112 | 带**相机租约**的起停(FFI 绑定) |
| `lib/vio/pose/vio_pose_source_runtime_flag.dart` | 100 | 开关的**第二来源**(运行期启动参数) |
| `lib/vio/capture/zero_arkit_capture_runtime.dart` | 334 | 相机 + 会话 + 内参换算,可注入 |
| `lib/vio/capture/zero_arkit_photo_api.dart` | 173 | 照片接口的薄适配器(**只调不实现**) |
| `lib/vio/capture/zero_arkit_scale_provenance.dart` | 111 | 尺度 provenance + 用户距离入口 |
| `ios/Runner/PwZeroArkitGate.swift` | 128 | 运行期开关的原生读取 + 相机租约闸 |
| `test/xrslam_world_axis_test.dart` | 204 | 9 例 |
| `test/xrslam_tracking_state_map_test.dart` | 167 | 14 例 |
| `test/zero_arkit_capture_path_test.dart` | 481 | 19 例(含阴性对照) |
| `test/vio_pose_source_runtime_flag_test.dart` | 91 | 8 例 |
| `test/ios_exported_symbol_whitelist_contract_test.dart` | ~230 | 6 例(§7) |

### 2.2 修改

| 文件 | 改了什么 |
|---|---|
| `lib/vio/pose/vio_ar_pose_provider.dart` | 换轴接进 `_toArPose`;状态映射换成表;照片走接口;`start()` 起运行时、`stop()` 停运行时;新增 `anchorScaleWithUserDistance` |
| `lib/vio/pose/vio_pose_source_switch.dart` | `current` 改成两来源**取或**;新增 `currentProvenance` |
| `lib/ui/official_capture/ar_capture_page.dart` | ON 时构造 `VioArPoseProvider(runtime: ZeroArkitCaptureRuntime())`;ON 时不挂 ARKit 的 `UiKitView` |
| `test/vio_pose_consumption_wiring_test.dart` | 上一刀那三行「证明没换轴」的断言改成「按置换表换了轴」 |
| `ios/Runner.xcodeproj/project.pbxproj` | 注册 `PwZeroArkitGate.swift`;导出白名单(§7) |

🔴 **没碰另两位 agent 的文件**:`PwCameraSlot.swift` / `OfficialAetherARKitPlugin.swift` /
`camera_slot_ffi.dart` 的改动**全部来自 cherry-pick**,不是我编辑的。
🔴 **UI 文案/布局一个字没改。**

---

## 3. 「不启动 ARKit」是怎么做到的、怎么证的

### 3.1 机制

`CaptureSession.attach()`(`capture_session.dart:1112`)里只有这一处会起 ARSession:

```dart
if (poseProvider case final PlatformARPoseProvider platformProvider) {
  await platformProvider.ensureStarted();     // → invokeMethod('startSession')
}
```

`VioArPoseProvider` 不是 `PlatformARPoseProvider` ⇒ 这一句整个跳过 ⇒
原生 `OfficialAetherARKitPlugin` 的 `ARSession` **根本不会被建出来**
(它是 `startSession` 里 lazy 建的,`OfficialAetherARKitPlugin.swift:2178`)。

预览那个 `UiKitView`(`pocketworld_official_arkit_preview`)内部是 `ARSCNView`,
`attachSessionIfReady()` 会 **0.05 秒一次地轮询**一个永远不会出现的 session
(`Timer` 永不 `invalidate`),画面还恒黑 ⇒ ON 时不挂它。

### 3.2 判据(`test/zero_arkit_capture_path_test.dart` A 组)

| | ARKit 通道上的消息 |
|---|---|
| **ON**(`VioArPoseProvider` + 完整 `attach()` + 一次 `tick()`) | **空** |
| **OFF**(平台臂,同一个 mock handler) | 含 `startSession` ✅ |

🔴 第二行是**阴性对照**:没有它,「ON 没调」可能只是因为测试压根没接上那条通道。

---

## 4. 换轴函数与它的判据

### 4.1 置换(`xrslam_world_axis.dart`)

```
x_A = −y_X      y_A = +z_X      z_A = −x_X
```
出处:2026-09-16 共享录制上 XRSLAM 轨迹与 ARKit 轨迹的 **SE(3) 实测拟合**。
位置 `p_A = P·p_X`;姿态 `R_A = P·R_X`(**只左乘** —— 只有世界系换了,
相机自身的局部系两边同为 OpenGL 式,不是 `P·R·Pᵀ` 的相似变换)。

### 4.2 🔴 我写错过一条理由,已改正

我最初在文件头断言:上游 `xrslam-ios` SceneKit 侧那个 `(x,y,z)→(−y,−x,−z)`
**行列式是 −1(镜像)**,所以可以直接判掉。
**算了一遍,不是。** 两个候选的行列式**都是 +1**,都是真旋转,determinant 分不开它们。
(我是在自己写的那条「反例」测试红了之后才发现的 —— 那条测试断言它是 −1,当场失败。)

**改正后的判据**(现在写在源码和测试里的那条):看**重力轴落到哪**。
两者在 ARKit 系里差一个绕 x 轴的 90°(`U·Mᵀ` 固定 x、y→−z、z→+y):

| | XRSLAM 的重力轴 `+z` 换过去变成 |
|---|---|
| 实测那个 | ARKit 的 **`+y`** = 「上」 ✅ |
| 上游 SceneKit 那个 | ARKit 的 **`−z`** = 一个**水平**方向 ❌ |

而 ARKit 的 `worldAlignment = .gravity`(`OfficialAetherARKitPlugin.swift:2196` 写死)
保证 y 就是重力反方向,XRSLAM 的世界系同样是重力对齐的 z-up
⇒ 只有实测那个能让两边的「上」对上;上游那个会让整个 dome 躺倒 90°。
上游那个是**显示侧**把 SceneKit 相机朝向一起掰过来用的,不是世界系换算。

### 4.3 单测(9 例,全绿)

- 三条基向量逐位落在表上;
- 行列式 = +1(**并写明这条分不开两个候选**,它挡的是「写重一个轴/漏一个符号」);
- 🔴 **重力轴判据**(上面那张表,连同 `U·Mᵀ` 的 90° 逐向量核对);
- **模长严格不变** —— 这条同时是「**没有人顺手把 33.75 mm 杠杆臂补上**」的闸;
- 「相机看向 XRSLAM 的 +z(天花板)」换过去必须变成「看向 ARKit 的 +y」;
- 姿态路径与位置路径对同一个向量给出同一结果(证明没有第二个隐藏变换);
- 退化四元数(引擎第一个 `TRACKING_SUCCESS` 返回零范数,09-16 实证)**原样返回**,
  不归一化成一个假的好数据;
- 4×4 列主序、平移在 `[12..14]`、左上 3×3 与换轴后的旋转一致。

### 4.4 杠杆臂:查过了,**不补**

`EnginePosePoller._readFromEngine` 取的是 **CAMERA_POSE**
(`PwXrslamTransportCore.cpp:229` 的 `PW_XRSLAM_T_WORLD_CAMERA`),
ARKit 的 `camera.transform` 也是相机位姿 ⇒ **两边同口径**。
补 33.75 mm 的 `p_bc` 反而会**引入** 3.38 cm 的偏差(09-16 我们正是因为
反向搞错了这件事而带着 3.38 cm 比了很久)。用「换轴不改模长」把这条钉住。

---

## 5. 状态映射表

`XRSLAMState` 只有三个取值(`vendor/xrslam/include/XRSLAM.h:101-105`);
`ARPose.trackingStateName` 有七个(`ar_pose.dart:76-88`)。**三对多 ⇒ 不确定的显式标 unknown。**

| XRSLAMState | → trackingStateName | isTracking | confidence | 为什么 |
|---|---|---|---|---|
| `INITIALIZING(0)` | `limited_initializing` | false | **exact** | 与 ARKit 的 `.limited(.initializing)` 语义相同 |
| `TRACKING_SUCCESS(1)` | `normal` | **true** | **exact** | 两边都表示 6DOF 可用。本表唯一完全对齐的一条 |
| `TRACKING_FAIL(2)` | `limited_unknown` | false | 🔴 **unknown** | 引擎**只说失败不说原因** |
| (会话没建起来) | `not_available` | false | — | 这是**会话**状态不是引擎状态,优先级最高 |
| (还没读到状态) | `limited_initializing` | false | — | |
| (未知码,如 7) | `limited_unknown` | false | 🔴 **unknown** | 不静默回落;`why` 里带上那个数值 |

### 🔴 三个**永远产不出**的词(写成常量 `kXrslamUnreachableTrackingStates`,有测试查)

| 词 | 为什么不用 |
|---|---|
| `limited_relocalizing` | 出货 XRSLAM **没有重定位**(loop closure 结果通道 09-19 实证是空实现)。报它 = 宣称一个不存在的能力,还会让 `PoseDriftTracker` 的分桶读成「它在重定位,再等等」 |
| `limited_excessive_motion` | 引擎不报原因。**而且**这个词正是 `capture_session.dart:1584` 那道 `_isExcessiveMotion` 闸的触发条件 —— 编它会**直接改采集行为** |
| `limited_insufficient_features` | 同上;另外 `XRSLAMGetResult(RESULT_FEATURES)` 在出货引擎里是空实现(09-19 实证),连判据都拿不到 |

### 🔴 顺手改掉上一刀的一个错

`vio_ar_pose_provider.dart` 原来在 `lastKnown` 档报 `'limited_relocalizing'`。
按上面第一行,那是错的,已改成走引擎状态表。

### `worldMappingStatus` 那 29 处:Dart 侧**零消费者**

全仓 grep:`worldMappingStatus` / `world_mapping` 在 `lib/` 下**0 命中**,
29 处全在 `OfficialAetherARKitPlugin.swift` 内部。而 ON 时那个插件整体不被激活
⇒ **不需要映射**,也不该为它编一个对应物。Dart 侧真正的状态面只有
`trackingStateName`(七词)+ `isTracking`,就是上面那张表。

---

## 6. 运行期开关(`--dart-define` 到不了的那条)

### 怎么在真机上打开(**不需要重新出包**)

```bash
xcrun devicectl device process launch --terminate-existing \
  --device <UDID> com.kyle.PocketWorld -- -PWVioPoseSource xrslam
```

`-Key value` 形式的启动参数被 iOS 塞进 `NSArgumentDomain`,
`ios/Runner/PwZeroArkitGate.swift` 的 `pw_vio_pose_source` 同时读
`UserDefaults.standard.string(forKey:)` **和**自己扫一遍 `ProcessInfo.arguments`(取或)。

> 🔴 取日志只能 `devicectl ... --console`,锁屏即 `RequestDenied`(09-22 记忆)。

### 不变量(4 条,`test/vio_pose_source_runtime_flag_test.dart` 8 例全绿)

1. **默认仍然是关的**:两条来源都不设 ⇒ `arkit`;
2. 符号不存在(模拟器/单测/安卓/dead-strip)⇒ `raw == null` ⇒ 当作没设;
3. 打错字(`xrsl` / `XRSLAMM` / 中文)**回落 arkit 且不抛**;
4. 显式传 `arkit`/`platform` ⇒ 仍然 arkit(**不是「设了就开」**)。

`currentProvenance` 会说清是哪条来源决定的:
`default_arkit` / `dart_define` / `launch_argument` / `debug_override`。
第二来源**只读不写** —— app 不会把自己持久化到研究臂上。

### 相机租约闸(运行期自证)

`PwCameraSlot` 自建 `AVCaptureSession` 且**不经过** `PwARCameraLease`
(`PwCameraSlot.swift:49` 自己写着),而 ARKit 独占后置相机,两条一起开
⇒ `FigCaptureSourceRemote err=-17281`,**两条都废**。之前只靠「调用方记得别同时开」。

新 `pw_zero_arkit_camera_start` 先向**既有的** `PwARCameraLease`(ARKit 的
`startSession` 用的是同一把锁)申请,拿不到就返回 **−100 失败关闭**,不去抢;
`pw_zero_arkit_camera_owned()` 回答「相机现在在谁手里」,不用靠日志猜
(09-20 教训:换臂实验必须有运行期自证)。
返回码 **−100(被占)与 −101(符号不在)分开** —— 混成一个码会让真机排查走岔。

---

## 7. 🔴 导出符号白名单 —— 顺带挖出一个**已经在生产上生效**的静默故障

> 这一节是协调者转达「用户已拍板放开白名单」之后做的。判据用的是一条可核的规则,
> 不是手挑。**但下面第一段是我在执行过程中查出来的、比白名单本身更大的问题,
> 请单独过目。**

### 7.1 发现:`-exported_symbol` 是**排他**的,而它 09-18 就被引入了

ld64 的语义:**只要出现一个 `-Wl,-exported_symbol`,导出表就变成排他白名单** ——
没列进去的符号会被从主二进制的动态符号表里摘掉。而 `DynamicLibrary.process()`
(= `dlopen(NULL)` + `dlsym`)**只找得到导出的符号**。

`git log -S` 查到:这串 flag 是 **2026-09-18 的 `a9378db`**
(「ios: camera frame slot, reachable from Dart over FFI」)引入的,当时只列了
6 个 `pw_camera_slot_*`。那一刀把导出表从「默认全导出」变成了「只导出这 6 个」,
于是**早就在用**的这些符号一起被关掉了:

| 符号组 | Dart 查它的文件 | 实现在哪 | 后果 |
|---|---|---|---|
| `pw_jxl_*`(9 个) | `official_capture/photo_archive_ffi_codec.dart:154-186` | `pw_jxl_bridge.mm`(在 Sources ✅) | JXL 照片归档编解码**静默降级** |
| `pw_zpaq_*`(8 个) | `official_capture/database_archive_ffi_codec.dart:123-149` | `pw_zpaq_bridge.cpp`(在 Sources ✅) | zpaq 数据库归档**静默降级** |
| `pw_imu_*`(4 个) | `vio/pose/native_imu_ffi.dart:143-150` | `PwImuSource.swift` ✅ | VIO 喂料 |
| `pw_xrslam_live_*`(8 个) | `vio/ffi/xrslam_live_ffi.dart:145-329` | `PwXrslamLive.swift` ✅ | VIO 位姿 |

**「静默」是最坏的部分**:仓里每一处 FFI 门面都按「符号不在 = 功能降级」处理,
不抛、不报警(这是对的设计,09-19 那次「缺个符号把整条渲染回路打断」的直接结果)。
所以这四组功能在 Release 里**关掉了却不会有任何症状显形**。

⚠️ 我**没有**在真机/真 Release 产物上确认 JXL / zpaq 确实失效 —— 上面是从
ld64 语义 + `DynamicLibrary.process()` 语义 + `git log` 推出来的。
要坐实需要 §7.4 的 `nm` 那一步。**这一条请用户/相关 owner 复核。**

### 7.2 用的规则(不手挑)

```
白名单 ⊇ ( lib/ 下 Dart 按名字查的符号 ) ∩ ( Runner target 自己定义的符号 )
```
两边都是 grep 出来的:
- 左边:`lib/**/*.dart` 里 `.lookup<…>('name')` / `.lookupFunction<…>('name')` 的字符串字面量 ⇒ **126 个**;
- 右边:`ios/Runner/*.swift` 的 `@_cdecl("name")`(**27 个**)+ 编进 Runner 的 C/C++ bridge。

### 7.3 加了 33 个(11 → 44),三份配置(Debug/Release/Profile)各加一份

| 组 | 个数 | 依据 |
|---|---:|---|
| `pw_xrslam_live_{create,begin,destroy,latest,stats,timing,timebase,gpufe_trail}` | 8 | `lib/vio/ffi/xrslam_live_ffi.dart:145,148,150,151,153,243,292,329` |
| `pw_jxl_{version,revision,error_message,encode_jpeg_file,encode_jpeg_file_cancellable,reconstruct_jpeg_file,reconstruct_jpeg_file_cancellable,cancellation_generation,request_cancel}` | 9 | `lib/official_capture/photo_archive_ffi_codec.dart:154,157,160,163,167,171,176,181,186` |
| `pw_zpaq_{version,revision,error_message,last_error,compress_file,decompress_file,cancellation_generation,request_cancel}` | 8 | `lib/official_capture/database_archive_ffi_codec.dart:123,126,129,132,136,140,144,149` |
| `pw_imu_{start,stop,latest,stats}` | 4 | `lib/vio/pose/native_imu_ffi.dart:143,146,147,150` |
| `pw_zero_arkit_camera_{start,stop,owned}` | 3 | `lib/vio/pose/zero_arkit_camera_gate.dart:107,109,111` ← **本刀新增** |
| `pw_vio_pose_source` | 1 | `lib/vio/pose/vio_pose_source_runtime_flag.dart:77` ← **本刀新增** |

同时给这 16 个 Swift `@_cdecl` 符号补了配套的 `-Wl,-u,_xxx`(jxl/zpaq 本来就有)。

### 🔴 **故意没加**的两组,以及一个更大的发现

| 组 | 为什么不加 |
|---|---|
| `pw_sqlite_*`(7 个,`database_prune_ffi.dart` / `database_archive_ffi_preprocessor.dart` 在查) | **实现根本不在 Runner target 里**:`ios/Runner/pw_sqlite_descriptor_transform.cpp` 文件在(2481 行,函数都在),但 `project.pbxproj` 里**零命中** —— 从没进过 Sources build phase |
| `pw_lepton_*`(7 个,`lepton_photo_archive_ffi_codec.dart` 在查) | `vendor/lepton_jpeg/libs/ios-arm64/libpw_lepton_jpeg_ffi.a` 只是一个 `PBXFileReference` + 在分组里,**没有 `in Frameworks` 条目** ⇒ 没被链进来 |

**导出一个不存在的符号救不了它们**,那是另一条要单独修的缺口
(与 `PwXrslamLive.swift` 从没进 target 是同一类 bug,照片 agent 刚修了那一个)。
`pwofficial_*` / `pwsfm_*` / `aether_*` / `pw_telemetry` 也不在名单里,但那是**对的** ——
它们在 `PWOfficialSfm.framework` / thermion 里,不走 Runner 的导出表
(`pw_telemetry` 走的是 `AetherFfi.resolveLibraryForBindings()`,不是 `process()`)。

### 7.4 验证

✅ **契约测试**`test/ios_exported_symbol_whitelist_contract_test.dart`(**6 例**全绿),
   把上面那条规则钉成永久判据:新加一个 `@_cdecl` 又在 Dart 里查它、却忘了加白名单
   ⇒ 当场红并打出缺的名字。还查了「三份配置的白名单完全一致」和「白名单里每个名字
   都真的有定义」(ld64 对导出不存在的符号只警告不失败 ⇒ 拼错不会显形)。
   **阴性对照做过**:手工删掉 `pw_xrslam_live_create` 那一行 ⇒ 测试红,
   报文逐字打出 `pw_xrslam_live_create`;恢复 ⇒ 绿。
   第 6 例是被这次构建失败逼出来的:**pbxproj 无重复 UUID**。
   阴性对照同样做过:把 `D001`/`D011` 改回 `C001`/`C011` ⇒ 当场红,
   报文逐字复现这次撞车的那两行。

### 🔴 真机 Release 构建 + `nm` —— **做了,而且它抓出了一个我自己的 bug**

```
$ flutter build ios --release --no-codesign      # 第一次
Error (Xcode): Undefined symbol: _pw_vio_pose_source
Error (Xcode): Undefined symbol: _pw_zero_arkit_camera_{owned,start,stop}
```

**根因不是导出表,是 pbxproj 的 UUID 撞车。** 我给 `PwZeroArkitGate.swift` 挑的
`0F1C1A10000000000000C001` / `…C011`,与 cherry-pick 进来的 `4433da1` 给
`PwXrslamLive.swift` 挑的**完全一样**。两条分支的 pbxproj 改动文本上不冲突,
git 一声不响 auto-merge,`plutil -lint` 也说 OK ⇒ Xcode 把两个 `in Sources`
解析成同一个 build file,**我的文件根本没被编译**。

🔴 **抓到它的只有真机 Release 构建**:`flutter analyze`、全量单测、`plutil -lint`
全是绿的。也正因为白名单里配了 `-Wl,-u`(强制引用),链接期才报了 undefined ——
**没有那个 `-u`,链接会静默通过,符号要到运行期 `dlsym` 才缺**。

把我这边改成 `D001` / `D011`(UUID 让给先到的那个文件,免得日后从他们分支
cherry-pick 又撞),重建:

```
$ flutter build ios --release --no-codesign      # 第二次
✓ Built build/ios/iphoneos/Runner.app (258.0MB)

$ nm -g --defined-only build/ios/iphoneos/Runner.app/Runner | grep _pw_
→ 44 个,**全部是 T**
$ diff <白名单> <nm 结果>
IDENTICAL (44/44)
```

**排他性自证**(证明 §7.1 不是推测):三个定义在二进制里、但不在白名单上的符号 ——

| 符号 | `nm --defined-only` | `nm -g --defined-only` |
|---|---:|---:|
| `pw_device_model` | 1 | **0** |
| `pw_documents_path` | 1 | **0** |
| `pw_process_resident_bytes` | 1 | **0** |

定义在,导出没有 ⇒ **白名单确实是排他的**,§7.1 里「jxl/zpaq 被一起关掉了」成立。

构建用的三个未文档化环境变量(协调者提示的,确认必需):
`PW_PRODUCT_SOURCE_MANIFEST_SHA256`(`tool/product_source_manifest.sh` 算,
本次 `3d416d66…72f5ed`)、`PW_DIAGNOSTIC_BUILD_ID`、`PW_VIO_SHADOW_MODE=off`。
构建全程挂了一个 1.2 GiB 的磁盘看门狗(同机有别的 agent 在构建);构建产物
(258 MB)已在跑完后删掉。

---

## 8. 其余部分

### 8.1 相机与会话(`ZeroArkitCaptureRuntime`)

起法逐条抄台架 `ar_minimal_loop_page.dart`:相机先起 → 等真实内参 → 建会话。
**顺序不能换**(`XrslamSession.start` 内部起 IMU 时要用相机那条串行队列,没登记返回 −4)。

| 参数 | 值 | 出处 |
|---|---|---|
| 采集尺寸 | 1920×1440 | 显示/成片口径 |
| 喂引擎尺寸 | 640×480 | 上游 18 份 iPhone 标定 **18/18** 都是它;1920×1440 直喂实测撞吞吐墙 |
| fps | 30 | 上游 `ViewController.swift:255` |
| 锁镜头 | 0.835 | 上游 `ViewController.swift:256`;不锁 fx 全程游走(实测单场 120 秒漂 10.90%) |

**内参换算**`scaleIntrinsicsForFeed`:`fx'=fx·(feedW/capW)`,`cx'` 同理,y 方向各自算。
🔴 写成独立函数 + 单测,因为 **09-22 的安卓喂料链在这一步漏写过(fx 留成 0)**。
provenance 标 `deviceApi`(系统 API 自报,不是我们测的、不是查表、不是占位)。

**两处失败关闭**:
- 相机拿不到内参 ⇒ **不建会话**(拿 `xrslam_session` 的 PLACEHOLDER `fx=1000/cx=640`
  开跑不会报任何错,只会安静地全错);
- 会话起不来 ⇒ 相机也停掉,不留一个空转的采集。

### 8.2 照片

先按约定的 C ABI 自己绑了一遍,**对方分支落地后换成直接调他们的门面**
(`lib/vio/ffi/pw_camera_photo_ffi.dart`,cherry-pick `405eca6`)——
同一套符号绑两遍迟早会漂。现在 `zero_arkit_photo_api.dart` 只是个薄适配器,
存在的理由是让单测能注入替身。

两条如实:
- 接口不可用 ⇒ `saveCurrentFrame` 返回 `unsupported`,**不假装成功**;
- **拍成了也不报 `saved`** ⇒ 报 `saved_elsewhere` + 真实路径。原生写的是它自己选的
  路径(`Documents/pw_photos/<requestId>.heic`),不是 `spec.jpegPath`;
  报 `saved` 会让 `CaptureSession` 去找一个不存在的文件。
- `captureHighResolutionStill` 返回 `null`:它的契约里有一串 ARKit 专有字段
  (photo-card 反馈 / SfM 灰度喂料 / 缩略图),零 ARKit 臂一个都产不出,
  半真半假地填回去比 null 更危险。

结果**按 `requestId` 配对,不按到达顺序** —— 上一张迟到的结果会被当成这一张,
而且不会报任何错。曝光**不替调用方加中点**(交出原始 `t` 与 `exposure` 两项,
加了就没人知道加过没加过)。

### 8.3 尺度

ON 时 SCALE-ANCHOR(`gravity_align.dart:215`,相对 ARKit 重锚)**结构上不可用** ——
没有 ARKit 可锚。所以:

- 默认 `provenance = 'vio_unanchored'`、`mayReportAbsoluteDimensions = false`;
- 唯一出口是 `metric_rescale.dart` 的用户输入距离(cherry-pick `145d8a6`);
- **不做 UI**(UX 由产品负责人定),只留入口函数 `anchorScaleWithUserDistance`;
- 🔴 **缩放被拒时尺度状态不变**,仍是未锚定(调用方不要在 catch 里把它打开)。

### 8.4 预览

ON 时不挂 ARKit 的 `UiKitView`(理由见 §3.1),**布局与尺寸一字未改**
(同一个 `CapturePreviewRect` + 同一个黑底),换掉的只是里面那块画面来源。
🔴 **用我们自己的相机流画预览本刀没做** —— 那是「共享 AR 渲染器」那条分支的事
(`ar_minimal_loop_page` 已经把 Filament 这条路验过)。这里如实留一块黑,不假装有预览。

---

## 9. 证据

### 9.1 OFF 逐位不变

```
$ flutter test test/vio_pose_source_switch_off_parity_test.dart
[OFF-PARITY] poseStream sha256 = b3362fb59f7793e18facfb6d84a6b5bf7104088bb379a6b84711340ae8f905ad
All tests passed!
```
与上一刀的金值**逐位相同**。

### 9.2 `flutter analyze`

改动的 15 个 lib/test 文件:**No issues found**。
`ar_capture_page.dart` 的 5 条是**既有的**(4 个一直没人引用的声明 + 1 条
`use_null_aware_elements`),与上一刀报告里列的完全一致。

### 9.3 全量 `flutter test` —— **我自己跑的阴性对照**

上一刀的报告给了一个 baseline,但那是另一次环境下的。我在**同一个 worktree、
同一次会话**里把分支 checkout 回 `5f3a223` 又跑了一遍全量,逐用例对拍:

| | 通过 | 失败 |
|---|---:|---:|
| baseline `5f3a223` | 1850 | 11 |
| 本分支最终 `7206969` | **1930** | **11** |

```
REGRESSIONS (fail in mine, pass in baseline):   NONE
FIXED/FLAKY  (fail in baseline, not in mine):   NONE
shared failures: 11   ← 失败集合**完全相同**
```

+80 = 新增用例(我的 56 + cherry-pick 进来的 metric_rescale 17 与 photo ffi 7)。
那 11 个失败全在本刀未触碰的文件里(opencv 契约 3、staging RLS 2、
xrslam 构建契约 2、xrslam 内参 1、xrslam 复刻契约 1、两个加载失败)。

> ⚠️ 上一刀报告里记的是 **12** 个失败,多一个 `social_profile_models_test.dart`
> 的加载失败。**那一条在我这台机上两次全量里都没复现**(baseline 与本分支都是 11)。
> 所以它是偶发的,**不是我修好的**。

### 9.4 Swift

`swiftc -typecheck`(带 `PwARCameraLease.swift` + `pw_camera_slot_start/stop` 的签名桩)
**零错误**。完整 typecheck 过不了是因为缺 `Flutter.framework`(bridging header 生成 PCH 失败),
与本刀无关。

---

## 10. 🔴 ON 路径还缺什么才能真机跑

按「必须先补」排序:

1. **预览画面**(§8.4)。ON 时现在是黑屏。要用 `PwCameraSlot` 的帧经 Filament 画背景 ——
   台架 `ar_minimal_loop_page` 已验过这条路,但把它搬进生产采集页是**渲染那条分支**的事。
   没有预览,用户无法取景 ⇒ 这条臂目前连「能用」都谈不上。
2. ~~`nm -g` 坐实导出白名单~~ → **已做**,见 §7.4(44/44 全 T)。
3. **每机常量 `c`**(`cameraTimeOffsetSeconds`)现在传 **0.0**。09-22 定案:
   td = `c + (读出+曝光)/2`,曝光那一半由原生传输层逐帧加,**但 `c` 要一场定**。
   B 段录制测出 `c* ≈ +3 ms`(相对 ARKit),这里没接上。
4. **质量判据仍只有一条**(继承上一刀):纹理判据要关键点(`GetResultFeatures` 是空实现)、
   尺度可观测性要世界系线加速度。⇒ `mayReportAbsoluteDimensions` 恒 false。
   这是 fail-safe 方向,但也意味着 ±5% 那条判据**今天还没有输入可判**。
5. **没有 3DOF 静止兜底**(`stationaryAttitude` 传 null,要独立的 IMU 订阅)。
6. **照片与位姿的配对**:照片 `t` 与位姿同域(host clock),但**谁去做那次配对、
   用不用曝光中点**,本刀没接 —— 只把两项原始数据交出来了。
7. **`saveCurrentFrame` 的路径口径**:原生自选路径 vs `spec.jpegPath`,
   需要两边 owner 谈一个口径(现在如实报 `saved_elsewhere`,下游还没处理这个状态)。
8. **真机验证**:ARKit 独占相机这条我只做了租约闸,**没在真机上验过 −100 那条分支
   真的会触发、也没验过 ON 时相机真的能起来**。

---

## 11. 约束遵守

- ✅ 没开摄像头、没碰 iPhone;
- ✅ 没改 UI 文案/布局(只在 ON 分支换了预览的**画面来源**);
- ✅ 没写 `~/.claude/`;
- ✅ 开工前 `df -h`(8.4 Gi → 最低 1.9 Gi,全程有别的 agent 在同机构建;
  iOS 构建加了 1.2 GiB 的磁盘看门狗);
- ✅ 主 checkout `~/Developer/pocketworld` 全程未动;
- ✅ `pubspec.lock` 的本机路径覆盖已还原,未提交;
- ✅ iOS Release 构建产物 `build/ios`(258 MB)跑完即删;
- ✅ 分支已 push 到 `origin/feat/ios-zero-arkit-capture`,**未合任何分支**;
- ✅ worktree 用完即删。

---

## 12. 给下一个人的三条

1. **pbxproj 的 UUID 要挑得不容易撞。** 三个 agent 并行各加一个 Swift 文件,
   我和照片 agent 就撞了(`…C001`/`…C011`)。现在有测试查,但挑的时候
   最好先 `grep` 一下候选值。
2. **`-Wl,-u` 值钱。** 它把「符号没编进去」从一个运行期的静默失效
   变成了一个链接期的硬错误。新加 `@_cdecl` 符号时,`-u` 和
   `-exported_symbol` 要一起加。
3. **ON 这条臂现在缺的是预览画面**(§10 第 1 条),不是位姿也不是相机。
   那块归「共享 AR 渲染器」那条分支。
