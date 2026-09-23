# VIO 消费层接线(默认关闭的开关后面)

日期 2026-09-22 · 分支 `feat/vio-consumption-flag` · commit **`5f3a22333956d431c629e1a65852720c229b70f6`**(短 `5f3a223`)
已推到 `origin`(github.com/Kyle-Wang0211/pocketworld)。**未合到 `feat/vio-shared-ar-renderer`,未合到 main。**

---

## 0. 一句话结论

**契约与管线接通了,生产行为逐位不变,并且有一个哈希对照把「不变」钉死。**
开关 `PW_VIO_POSE_SOURCE` 默认空 = ARKit;OFF 时 12 帧回放脚本穿过混合解算后的位姿序列
sha256 **与接线之前的 `f0b3a40` 逐位相同**(金值是在改 `lib/` **之前**算出来的,不是事后回填)。

🔴 **开关 ON 这条臂今天在真机上拿不到 6DOF** —— 喂料链断在相机:`PwCameraSlot` 自建
`AVCaptureSession`,而 ARKit 在会话运行期间独占后置相机。**契约通了,喂料没通。**
这一条本次**没有**修,理由见 §6。

---

## 1. 工作区

| 项 | 值 |
|---|---|
| worktree | `~/Developer/pocketworld-wt-consume`(`git worktree add … -b feat/vio-consumption-flag HEAD`) |
| 起点 | `f0b3a40`(主 checkout 的 `feat/vio-shared-ar-renderer` HEAD) |
| 体积 | 建完 **446 MB**(仓里 14 G 的绝大部分是 untracked 的引擎归档/构建树,worktree 不带) |
| 磁盘 | 开工 `6.0Gi` avail → `pub get` 后 `4.9Gi` → 删除 worktree 后 `4.5Gi`。🔴 比预期低,因为**同一台机上有别的 agent 在跑**(`git worktree list` 里有一个 `…/scratchpad/wt-android-feed`),不是本任务的残留 |
| 主 checkout | **一个字节没碰**(它有别人的 11 项未提交改动) |

🔴 `flutter pub get` 会把 `pubspec.lock` 改成本机的 `thermion_dart` 路径覆盖(`../thermion_dart_pw`)。
那是环境相关的,**没有提交**,commit 前 `git checkout -- pubspec.lock` 还原。

---

## 2. 改了哪些文件 / 哪些行

### 2.1 新增(5 个文件,1196 行)

| 文件 | 行数 | 做什么 |
|---|---:|---|
| `lib/vio/pose/vio_pose_source_switch.dart` | 96 | 开关本身。`enum PwVioPoseSource { arkit, xrslam }` + `PwVioPoseSourceSwitch` |
| `lib/vio/pose/vio_ar_pose_provider.dart` | 341 | `VioArPoseProvider implements ARPoseProvider, ARPoseSourceLabel` —— 适配器本体 |
| `lib/vio/quality/pose_confidence.dart` | 191 | 可信度汇总 + **产品容差常量 ±5%** |
| `test/vio_pose_consumption_wiring_test.dart` | 374 | (b)(c)(d) 三组判据,11 个用例 |
| `test/vio_pose_source_switch_off_parity_test.dart` | 194 | (a) OFF 逐位不变的哈希对照,1 个用例 |

### 2.2 修改(3 个文件,+175 / −10)

**`lib/official_capture/capture_session.dart`**(+121)

| 位置 | 改动 |
|---|---|
| `:52` | 新增 `import 'package:flutter/foundation.dart' show visibleForTesting;` |
| `:288`(原)`String _lastPoseSource = 'arkit';` | → `late String _lastPoseSource = _platformPoseSourceLabel;` |
| 新增 `:294-310` | `late final String _platformPoseSourceLabel = _readPoseSourceLabel();` —— provider 不实现 `ARPoseSourceLabel` 就返回 `'arkit'`;自报未知标签 **抛 `StateError`**(在**会话首次使用时**炸,不是拍到一半) |
| 新增 `:316-320` | `static const Set<String> _knownPoseSources = {'arkit','xrslam','imu'}` |
| 新增 `:331-368` | **`static bool _poseSourceCarriesCameraGeometry(String)`** —— 显式 `switch`,`default:` 抛 `StateError` |
| 新增 `:377-391` | 三个 `@visibleForTesting` 窗口:`debugLastPoseSource` / `debugPlatformPoseSourceLabel` / `debugPoseSourceCarriesCameraGeometry` |
| `_resolveHybridPose` 内 **3 处** `_lastPoseSource = 'arkit';` | → `= _platformPoseSourceLabel;`(`= 'imu'` 那处不动) |
| **原 `:1599-1607`**(自动入库路径) | 三处 `_lastPoseSource == 'arkit'` → 一个 `carriesCameraGeometry` 局部变量 |
| **原 `:1875-1881`**(手动快门路径) | 两处同样的隐式闸 → 同一个 helper。🔴 **任务书只点了 1599-1607,但同一个 bug 在手动路径也有一份**,一起修了 |

**`lib/official_dome/ar_pose.dart`**(+15):新增可选接口
```dart
abstract interface class ARPoseSourceLabel { String get poseSourceLabel; }
```
不实现它 = `'arkit'` ⇒ `PlatformARPoseProvider` 与 `test/` 里每个 mock **一行不变**。

**`lib/ui/official_capture/ar_capture_page.dart`**(+49):接线点在原 `:755`
```dart
final vioProvider = PwVioPoseSourceSwitch.isSelfVio ? VioArPoseProvider() : null;
final session = CaptureSession(targetPoints: _targetPoints, poseProvider: vioProvider);
```
默认 `vioProvider == null` ⇒ `CaptureSession` 内部照旧 `PlatformARPoseProvider()`。
另加:可信度订阅(只 `debugPrint`,**不 setState、不进 UI**)+ `dispose` 里的取消/释放。
🔴 **UI 文案/布局/引导一个字没改。**

---

## 3. 开关

```
--dart-define=PW_VIO_POSE_SOURCE=xrslam     # 打开自研臂
--dart-define=PW_VIO_POSE_SOURCE=           # 默认,= ARKit
```

- 认 `''` / `arkit` / `platform` → ARKit;`xrslam` / `selfvio` → 自研臂(大小写与空白不敏感)。
- 🔴 **认不出的值回落 ARKit,不抛** —— 构建命令行的一个错别字不该把生产用户切到研究臂上。
  debug 下打一行 `[PwVioPoseSourceSwitch] 无法识别的 …,已回落到 arkit`。
- 测试用的运行期覆盖:`PwVioPoseSourceSwitch.debugOverride`(生产代码不写它)。
- 写法抄仓里已有的三处同款:`PW_VIO_SHADOW` / `PW_CAM_TD_MS` / `PW_VIDEO_FORMAT`。

### 🔴 一个必须说清的前提:iOS 上这个开关**物理上打不开**

`lib/main.dart:183-192` 的注释是 2026-08-09 的真机实证:**`--dart-define` 到不了本工程的
iOS xcconfig 链**(这正是后端地址被改成运行期解析的原因)。同一条对本开关成立 ——
**出货 iOS 包里 `kPwVioPoseSourceRaw` 永远是默认值,永远 ARKit。**

对「默认关闭」这条要求,这是**更强**的保证;但它同时意味着:想在真机上跑 ON 这条臂,
`--dart-define` 不够,必须另配一条运行期开关(与 `EndpointConfigResolver` 同款)。
**那条路本次没做**,见 §6。

---

## 4. 可信度 / 产品容差 ±5%

`lib/vio/quality/pose_confidence.dart`:

```dart
/// 🔴 来源 = 产品决策(2026-09-22),不是发表值、不是标准值。
const double kPwEstimatedDimensionToleranceRelative = 0.05;
```

文件头写清了三件事:
1. **这是允许上限,不是「我们的精度是 5%」。** 我们自己实测的 VIO 尺度偏差是 **4.13%**
   (09-19 共享录制回放),同场四段跨度 **0.73%–10.80%** —— 单场之内就能越线。
2. 对照:RICS Band E(净面积/估价)≈ 4 m 上 1.25%,**比 5% 严**,这一档够不到;
   USIBD LOA20 = 15 mm–5 cm;带 LiDAR 的 RoomPlan 在一个具体房间上也跑出过 5.7%。
3. **没有**去改 `ScaleObservabilityConfig.targetRelativeScaleSigma`(默认 0.01)——
   那是滑窗内 1σ 统计量,与「对外承诺的容差上限」不是一个东西,改它会动既有行为和单测。

`VioPoseConfidence` 是纯数据,`toJson()` 里带 `tolerance_provenance: "product_decision_2026_09_22"`。
`summarizeVioPoseConfidence()` 把四条(位姿档位 / 尺度可观测性 / 初始化窗口 / 纹理)汇总成
`VioPoseTrustTier { none, orientationOnly, poseOnly, metric }`。

🔴 **`mayReportAbsoluteDimensions` 的判据是 `scaleVerdict == sufficient && initPhase == converged`,
不是拿 σ 去跟 5% 比** —— σ 是窗口内的离散度,对一个跨帧一致的系统性尺度偏差(我们那 4.13%)
完全无感。这是 09-20「拿均值的标准误当误差棒」那次栽的坑的直接后果,写进了注释。

---

## 5. 测试

### 5.1 (a) 开关 OFF 与改前逐位相同 —— 哈希对照

`test/vio_pose_source_switch_off_parity_test.dart`。做法:

1. `_ReplayPoseProvider` 回放一段写死的 12 帧 `ARPose` 脚本,覆盖 `_resolveHybridPose`
   的**全部**支路(pre-lock / ARKit normal 建锚 / ARKit limited 走 IMU 代入 / IMU→ARKit 过渡 ramp);
2. 把 `CaptureSession.poseStream` 交出的**混合解算后**位姿逐字段规范化序列化,取 sha256;
3. 与写死的金值比。

**金值是在接线之前的 pristine worktree 上跑这同一个文件算出来的**(连跑两次确认稳定),
然后才动 `lib/`:

```
# ① lib/ 未动,HEAD = f0b3a40
$ flutter test test/vio_pose_source_switch_off_parity_test.dart
[OFF-PARITY] poseStream sha256 = b3362fb59f7793e18facfb6d84a6b5bf7104088bb379a6b84711340ae8f905ad
[OFF-PARITY] poseStream sha256 = b3362fb59f7793e18facfb6d84a6b5bf7104088bb379a6b84711340ae8f905ad   ← 复跑相同

# ② 改完 lib/ 之后
$ flutter test test/vio_pose_source_switch_off_parity_test.dart
[OFF-PARITY] poseStream sha256 = b3362fb59f7793e18facfb6d84a6b5bf7104088bb379a6b84711340ae8f905ad
00:00 +1: All tests passed!
```

🔴 **为什么哈希的是 poseStream 而不是 `_onPoseTick` 的落盘产物**:`_onPoseTick` 的
origin-settle 闸读 `_clock.elapsedMicroseconds`(真实墙钟),同一份输入两次跑不出同一个结果 ——
拿它做金值只会得到一个随机失败的测试。位姿序列是这条链上**确定性的**那一段,也正是
「换位姿源会动什么」的那一段。

🔴 **踩到一次自己的坑**:第一版用 `await Future.delayed(50ms)` 等事件循环,单文件下过、
全量套件并发下不够 ⇒ 在全量跑里红了一次。已改成**有界轮询**(收满 12 帧就走,10 秒硬上限)。
同一条教训:让测试去等墙钟,只会把「异常」伪装成「很慢」。

### 5.2 (b) 开关 ON:位姿到达消费点 + 可信度非空

`test/vio_pose_consumption_wiring_test.dart`,3 个用例:

- **位姿 + 外参 + 内参 + 可信度全部穿过去,且源标签是 xrslam**:注入一个脚本化的
  `EnginePosePoller`(`TRACKING_SUCCESS` + 单位四元数),手工 `tick()` 三次 ⇒
  `session.poseStream` 收到 3 帧;`isTracking == true`;`extrinsic4x4.length == 16`;
  `intrinsicFxFyCxCy == [448.97, 448.97, 320, 240]`;`session.debugLastPoseSource == 'xrslam'`;
  `debugPoseSourceCarriesCameraGeometry('xrslam') == true`;可信度流 3 个事件、字段全非空、
  `toleranceRelative == 0.05`、`tolerance_provenance == 'product_decision_2026_09_22'`。
  🔴 还逐位断言 `position.{x,y,z}` 等于引擎给的三元组 —— **证明没有偷偷换轴**。
  🔴 也断言 `mayReportAbsoluteDimensions == false`(没有尺度样本 ⇒ fail-safe 方向)。
- **引擎没出位姿 ⇒ 优雅降级**:`isTracking=false`、`extrinsic4x4` 空、`scaleAlignAnchorCount == 0`、
  `tier == none`、**不抛**。
- **XRSLAM 臂没有取帧出口 ⇒ `saveCurrentFrame` 如实 `unsupported`**,不假装成功。

🔴 测试**不等真实定时器**:`pollInterval` 传 1 小时,手工调 `tick()`。

### 5.3 (c) `capture_session` 新分支

- `arkit` / `xrslam` 带相机几何;`imu` 不带;
- **未知源抛 `StateError`**(`debugPoseSourceCarriesCameraGeometry('who_knows')`);
- provider 自报未知标签(`'martian_vio'`)⇒ **会话一用就炸**,而不是拍到一半才发现丢了外参;
- 不实现 `ARPoseSourceLabel` 的 provider ⇒ `'arkit'`(证明既有 mock / 平台臂不变)。

### 5.4 (d) 开关解析:默认空 = ARKit / 大小写空白 / 打错字回落不抛 / 标签封闭。

### 5.5 命令与输出

```
$ cd ~/Developer/pocketworld-wt-consume
$ flutter analyze lib/vio/pose/vio_pose_source_switch.dart \
    lib/vio/pose/vio_ar_pose_provider.dart lib/vio/quality/pose_confidence.dart \
    lib/official_capture/capture_session.dart lib/official_dome/ar_pose.dart \
    test/vio_pose_consumption_wiring_test.dart test/vio_pose_source_switch_off_parity_test.dart
Analyzing 7 items...
No issues found! (ran in 2.1s)
```

```
$ flutter analyze lib/vio lib/official_capture lib/official_dome lib/ui/official_capture
Analyzing 4 items...
… 8 issues found. (ran in 9.1s)
```
🔴 那 8 条**全部是既有的**(`pwva_master.dart` 的 `unawaited_return_in_try_block`、
`platform_pose_provider.dart` 两条 `use_null_aware_elements`、`ar_capture_page.dart` 里
四个一直没人引用的声明 `_stopRecordingIfRunning` / `_onCenterTap` / `_PhotoPositionOverlay` /
`_CaptureButtonOrDome` + 一条 `use_null_aware_elements`)。**我改动的 7 个文件零问题。**

全仓 `flutter analyze lib/ test/` 是 **43 issues,改前改后同样是 43**;其中 11 个
`error` 全在 `test/opencv_autocapture_vision_validation_test.dart` 与
`test/zz_post_delivery_probe_test.dart` 两个文件里,`git diff --stat` 对这两个文件是 **0 行**。

**全量 `flutter test`(JSON reporter,逐用例对照 HEAD)**:

| | 通过 | 失败 | 跳过 |
|---|---:|---:|---:|
| HEAD `f0b3a40`(把 `lib/` `test/` 全部 stash 掉跑的基线) | 1837 | 12 | 1 |
| 本次 `5f3a223` | **1849** | **12** | 1 |

```
regressions: NONE
pre-existing identical: True
```

**+12 = 本次新增的 12 个用例;失败集合与 HEAD 逐项相同**,12 个都在本次未触碰的文件里:

```
opencv_autocapture_vision_contract_test.dart   (3)
opencv_autocapture_vision_validation_test.dart (1, 加载失败)
social_profile_models_test.dart                (1, 加载失败)
staging_upload_rls_contract_test.dart          (2)
xrslam_build_profiles_contract_test.dart       (2)
xrslam_intrinsics_test.dart                    (1)
xrslam_official_replica_contract_test.dart     (1)
zz_post_delivery_probe_test.dart               (1, 加载失败)
```

⚠️ 所以「`flutter test` 全绿」这句话**不能说** —— 仓里进来的时候就有 12 个红的。
能说的是:**一个回归都没有,失败集合逐项相同,新增 12 个全绿。**

---

## 6. 没做的,和为什么

### 6.1 🔴 开关 ON 时真机上拿不到 6DOF —— 喂料链断在相机(**最大的缺**)

`PwCameraSlot` 自建 `AVCaptureSession`;ARKit 在会话运行期间**独占**后置相机
(`ar_capture_page.dart:737-747` 的既有注释是实证:并行开相机 ⇒
`FigCaptureSourceRemote err=-17281`,两条路一起废)。生产采集页今天由 ARKit 开着相机,
所以 `VioArPoseProvider` 在真机上会一直停在 `TRACKING_SUCCESS` 之前。

两条出路,**都没做**,也**不该**在「默认关闭的开关」这一刀里做:
(a) 采集页改成不开 ARKit(那就不是「默认关闭」了);
(b) 原生侧把 `ARFrame.capturedImage` 转喂 `PwXrslamLive`(要动 `AetherARKitPlugin`)。

降级是**优雅**的:拿不到位姿就交 `isTracking=false` 的 ARPose、`tier=none`,
`CaptureSession` 的既有闸照常把它挡在落盘之外 —— 不崩、不脏数据。

### 6.2 🔴 iOS 上没有运行期开关

见 §3。`--dart-define` 到不了出货 iOS 的 xcconfig 链,所以 ON 这条臂**在真机上根本进不去**。
要跑它得补一条运行期开关(照 `EndpointConfigResolver` 的形状)。**本次没做。**

### 6.3 三条质量判据里只喂得起一条

`VioArPoseProvider` 只驱动 `VioInitializationGate`。另两条**如实留空**(传 `null`):
- **纹理判据**要关键点 —— 出货引擎的 `XRSLAMGetResult(RESULT_FEATURES)` 是**空实现**(09-19 实证);
- **尺度可观测性**要世界系线加速度(IMU 流 + 已解算重力)—— 采集页上 IMU 已被
  `OrientationTracker` 占着,再起一条就是第二个 `CMMotionManager`,上游明确不这么做。

⇒ 后果是 `mayReportAbsoluteDimensions` 恒为 `false`。**这是 fail-safe 方向,不是 bug**,
但也意味着「±5% 容差」这条判据今天**还没有输入可判**。没有去编一个假样本填上。

### 6.4 没有 3DOF 静止兜底

`stationaryAttitude` 传 `null`,理由同上(要独立的 IMU 订阅)。如实少这一档。

### 6.5 没换轴

`vio_pose_source.dart` 文件头写死:世界系约定我们有**两个互相矛盾**的记录
(实测 SE(3) 拟合 `x_A=−y_X, y_A=+z_X, z_A=−x_X` vs 上游 SceneKit 硬编码 `(x,y,z)→(−y,−x,−z)`)。
在从我们自己的 build 打一个真实位姿判死之前,任何换轴都是猜。
⇒ 交出的位姿在**引擎自己的世界系**里,靠 `poseSource: 'xrslam'` 这个标签告诉下游
「这份外参不是 ARKit 口径」。这正是把闸改成显式 switch 的意义所在。

### 6.6 没上机 / 没开摄像头 / 没碰 iPhone

按约束。所以本次**只有单测级证据,没有运行/精度证据**。

### 6.7 `VioArPoseProvider` 没有帧保存出口

`saveCurrentFrame` / `captureHighResolutionStill` 返回 `unsupported` / `null`。
出货引擎导出的 5 个符号里没有任何取图像的入口。假装成功会让 `CaptureSession`
以为落盘了而实际没有,所以如实返回,让既有失败路径原样生效。

---

## 7. 收尾

- `pubspec.lock` 的本机路径覆盖已还原,**未提交**。
- worktree `~/Developer/pocketworld-wt-consume` 已 `git worktree remove --force`,exit 0,`git worktree list` 里已不在。分支与 commit 都还在。
- 分支 `feat/vio-consumption-flag` 已推到 `origin`,**未合任何分支**。
- 主 checkout `~/Developer/pocketworld` 全程未动(它仍停在 `feat/vio-shared-ar-renderer` + 11 项未提交改动)。

---

## 附:速查

| 用途 | 路径 |
|---|---|
| 开关 | `lib/vio/pose/vio_pose_source_switch.dart` |
| 适配器 | `lib/vio/pose/vio_ar_pose_provider.dart` |
| 可信度 + ±5% 常量 | `lib/vio/quality/pose_confidence.dart:37` |
| 显式位姿源闸 | `lib/official_capture/capture_session.dart` → `_poseSourceCarriesCameraGeometry` |
| provider 自报标签接口 | `lib/official_dome/ar_pose.dart` → `ARPoseSourceLabel` |
| 接线点 | `lib/ui/official_capture/ar_capture_page.dart`(原 `:755`) |
| OFF 哈希对照 | `test/vio_pose_source_switch_off_parity_test.dart`,金值 `b3362fb5…` |
| ON / 闸 / 开关 的判据 | `test/vio_pose_consumption_wiring_test.dart` |
