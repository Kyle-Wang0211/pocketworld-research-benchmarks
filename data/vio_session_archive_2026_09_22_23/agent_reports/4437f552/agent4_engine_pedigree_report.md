# XRSLAM iOS `gpufe_nothread` 臂:可复现构建 + 谱系证据

日期 2026-09-22 · 产物 sha256 `b9b14814349eb945287b06ac6f5732e9c0a939e572ed46a073e597d59ea54cd2`

---

## 0. 一句话结论

**出货那份 research 归档 `libxrslam_gpufenothread_4beb1a9.a`(sha16 `2c2bc346`)的谱系已经打通。**
新建的一条命令构建脚本,产出的 58 个归档成员里 **53 个与出货档逐字节相同**;
剩下 4 个成员的差异经逐字节定位,**只是构建目录的绝对路径被 OpenCV 的
`CV_Assert`/`__FILE__` 烤进了 `__TEXT,__cstring`**,与代码、优化、符号表全无关
(抹掉那条路径后,字符串表与符号表差异行数都是 **0**)。第 5 个差异是
`__.SYMDEF`,它只是前 4 个成员大小变化后的偏移表连带结果。

⇒ 此前回执里那句 `bench_commit: "2c88935+gpufe-uncommitted"` 的空白已经补上:
源码状态钉在 commit **`8a1cc12`**,从它出发可以重建出与出货档同源的归档。

🔴 **未做 push**,原因见 §1。

---

## 1. 钉死源码状态

| 项 | 值 |
|---|---|
| 工作树 | `/Users/kaidongwang/Developer/xrslam-4beb1a9-thr` |
| 它是什么 | **`~/Developer/xrslam` 的 git worktree**(`git rev-parse --git-common-dir` → `/Users/kaidongwang/Developer/xrslam/.git`),同一个仓 |
| 新分支 | `build/gpufe-nothread-20260922` |
| **commit** | **`8a1cc1213af541dc6a1f4e1b89e0ff3629205c91`**(短 `8a1cc12`) |
| 父 commit | `2c88935`(`pw/threading-backpressure-20260902`) |
| 提交内容 | 19 个已跟踪文件的改动 + 3 个此前未跟踪的源文件 |
| 提交后工作树 | 已跟踪文件 **0 脏**(`build-*/` 构建树未入库) |

新入库的 3 个源文件(此前**只存在于磁盘,不在任何 commit 里**,是谱系最大的洞):

- `xrslam-extra/include/xrslam/extra/gpu_image.h`
- `xrslam-extra/src/xrslam/extra/gpu_image.cpp` ← GPU 前端的 extra 后端本体
- `xrslam/src/xrslam/utility/pw_trace.h`

### 🔴 为什么没 push

```
$ git -C ~/Developer/xrslam-4beb1a9-thr remote -v
manorajesh  https://github.com/manorajesh/xrslam.git
origin      https://github.com/openxrlab/xrslam.git
```

**两个 remote 都不是用户自己的仓**:`origin` 是上游 OpenXRLab 官方项目,
`manorajesh` 是第三方个人 fork。往这两个任何一个 push 都属于「公开发到第三方项目」,
按既定规矩必须先点头。**commit 已落地在本地,等一个用户自己的 remote(或一句确认)即可推。**

### 🔴 任务书里的一处不符

任务书说「在 `~/Developer/xrslam` 里提交」。实际产出出货 `gpufenothread` 归档的树是
**`~/Developer/xrslam-4beb1a9-thr`**(出货回执 `bench_worktree` 字段自己写着),
而 `~/Developer/xrslam` 是同仓的另一个 worktree,checkout 在 `pw/vio`(`d052dc3`),
改动集完全不同(40 文件 / 2776 行,含 feature_tracker、parsac、ransac 等)。
**我提交的是真正产出该归档的那棵树**;因为是同一个仓,`8a1cc12` 在 `~/Developer/xrslam` 里同样可见。

---

## 2. 一条命令的构建脚本

**`/Users/kaidongwang/Developer/viobench-build/gpufe/build_gpufe_nothread.sh`**

```bash
build_gpufe_nothread.sh [--build-dir DIR] [--out PATH] [--jobs N] [--clean]
```

- 逐行沿用 `configure_engine.sh` 的口径(那份是从 gpufe 回执还原的),
  **只翻一个开关** `XRSLAM_ENABLE_THREADING ON→OFF`;没有重写构建逻辑。
- **默认不碰** `vendor/xrslam/libs/` 里的出货 `.a`:产物落在 `--out`。
- 产出 `.a` + `.a.syms.txt` + **收据 JSON**(schema `pw.xrslam.ios-archive-receipt/2`),
  收据含:源码 commit/branch/脏文件数、**cmake 开关全列**、工具链版本、
  依赖版本、归档成员数、`nm -g --defined-only` 导出符号清单、GPU 前端伴随库 sha256。
- ABI 闸:生产那五个符号缺任何一个即作废产物并非零退出。

### 交付物落位

| 文件 | 路径 |
|---|---|
| 归档 | `~/Developer/viobench-build/engine/libxrslam_gpufenothread_8a1cc12.a` |
| 收据 | `~/Developer/viobench-build/engine/libxrslam_gpufenothread_8a1cc12.receipt.json` |
| 符号表 | `~/Developer/viobench-build/engine/libxrslam_gpufenothread_8a1cc12.a.syms.txt` |

### 工具链(收据里已记)

`cmake 4.2.3` · `ninja 1.13.2` · `Apple clang 17.0.0 (clang-1700.6.3.2)` ·
`Xcode 26.2 (17C52)` · `iPhoneOS SDK 26.2` · eigen 3.3.7 · OpenCV 4.0.1(预编译 framework)·
ceres pinned `e809cf0c` / 1.14.0,命名空间 `pw_xrslam_ceres_1_14` · Release · `-O3 -DNDEBUG`
`-ffp-contract=off -fno-fast-math -fchar8_t` · `XRSLAM_IOS=OFF` `THREADING=OFF` `GPU_FRONTEND=ON`

---

## 3. 可复现证明(跑了 4 次,不是 2 次)

| 跑次 | 构建目录 | 脚本版本 | 产物 sha256 |
|---|---|---|---|
| run1 | `…/scratchpad/build-run1` | 初版(无归一化) | `ddf5106bc474022d…` |
| run2 | `…/scratchpad/build-run2` | 初版 | `0a19bcaddc72356b…` |
| run3 | `…/scratchpad/build-run1` | 初版 | `618a3c9758391848…` |
| **run4** | `…/scratchpad/build-run1` | **最终版** | **`b9b14814349eb945…`** |

三次原始 sha 各不相同。**逐字节查清了,两个原因,都不含糊:**

### 原因 A —— 构建目录绝对路径被烤进 4 个 `.o`(run1 vs run2)

58 个成员里 **54 个逐字节相同**,4 个不同,且每个**只差 1 个字节**:

| 成员 | 差异字节偏移 | run1 值 | run2 值 |
|---|---|---|---|
| `XRGlobalLocalizerManager.cpp.o` | 5347 | 八进制 `061` = `'1'` | `062` = `'2'` |
| `XRSLAMManager.cpp.o` | 14195 | `061` | `062` |
| `gpu_image.cpp.o` | 40388 | `061` | `062` |
| `localizer.cpp.o` | 304759 | `061` | `062` |

那个字节位于 `__TEXT,__cstring` 里的这条字符串:

```
…/scratchpad/build-run1/_deps/depends-opencv-build/opencv2.framework/Headers/core/mat.inl.hpp
                     ↑ 就是这一位
```

来源:OpenCV 的 `mat.inl.hpp` 里有 **152 处 `CV_Assert`/`CV_DbgAssert`**,宏体带 `__FILE__`;
只有这 4 个 TU 内联到了带 assert 的那段,所以只有它们把构建树路径固化进了只读字符串段。

**⇒ 构建目录路径不同,这 4 个成员必然不同。要复现某个历史 sha,必须用它原来的构建目录路径。** 已写进收据 `determinism_note_zh`。

### 原因 B —— 归档成员头的 mtime(run1 vs run3)

run1 和 run3 用的是**同一个** `--build-dir` 路径,结果 **58/58 成员逐字节全相同**,
整档 sha 却仍然不同。`ar -tv` 一比就看出来:成员头里的时间戳是构建时刻。

根因:`xcrun libtool -static -D`(deterministic)**只对散装 `.o` 生效**;
从子归档(`libxrslam-core.a` / `libyaml-cpp.a` …)拷进来的成员,
libtool 把子归档写的 60 字节头**原样搬运**,`-D` 不重写它们。

**已修**:脚本在 libtool 之后加了一步归档头归一化(把每个成员头的 `mtime`/`uid`/`gid` 清零)。
只动定长头的三个字段,**成员内容/顺序/大小/`__.SYMDEF` 偏移表全不变**(已验:归一化前后 58/58 成员内容相同,`nm` 正常)。

### 最终判据

```
run1 事后归一化  b9b14814349eb945287b06ac6f5732e9c0a939e572ed46a073e597d59ea54cd2
run3 事后归一化  b9b14814349eb945287b06ac6f5732e9c0a939e572ed46a073e597d59ea54cd2
run4 最终脚本    b9b14814349eb945287b06ac6f5732e9c0a939e572ed46a073e597d59ea54cd2
```

**同一命令、同一 `--build-dir` 路径、两次 `--clean` 全量构建 ⇒ 产物 sha256 逐位相同。**

### 与出货档的谱系对照(本次最有价值的结果)

`libxrslam_gpufenothread_4beb1a9.a`(出货,`2c2bc346`)vs run1:

- 成员清单与顺序 **完全一致**(58 项)
- **53 个成员逐字节相同**
- 5 个不同:就是上面那 4 个 `.o` + `__.SYMDEF`
- 4 个 `.o` 每个**恰好大 56 字节**,正对应路径字符串从 132 字符
  (`/Users/kaidongwang/Developer/xrslam-4beb1a9-thr/build-nothread/…`)变到 192 字符(scratchpad 路径)
- **抹掉那条路径后,四个成员的字符串表差异 0 行、符号表差异 0 行**
- 旁证:原构建树 `~/Developer/xrslam-4beb1a9-thr/build-nothread` 里的
  `libxrslam-core.a` **21/21 个成员**、散装 `XRSLAMManager.cpp.o` / `XRGlobalLocalizerManager.cpp.o`
  均与出货归档成员逐字节相同 ⇒ 那棵构建树确实就是出货档的来源

**⇒ 结论:commit `8a1cc12` 就是出货 research 归档的源码状态,谱系成立。**
要拿到与 `2c2bc346` 完全相同的字节,只需把 `--build-dir` 设回 `~/Developer/xrslam-4beb1a9-thr/build-nothread`
并去掉归档头归一化这一步。(我**没有**去重建那棵历史构建树 —— 它是现存唯一的历史物证,不该被 `--clean` 抹掉。)

---

## 4. ABI 对照

### 🔴 先更正任务书的一个前提

任务书说出货 `libxrslam_generic_4beb1a9.a` 导出 **24 个符号**。**实测不是 24,是 5。**

```
$ xcrun nm -g --defined-only libxrslam_generic_4beb1a9.a | grep -E '^(XRSLAM|XRGlobal)'
XRSLAMCreate  XRSLAMDestroy  XRSLAMGetResult  XRSLAMPushSensorData  XRSLAMRunOneFrame
```

三方互证:① 它自己的回执 `exported_abi` 就是这 5 个;
② 出货头 `vendor/xrslam/include/XRSLAM.h` 也只声明这 5 个函数;
③ arloopbench Podfile 里的 `-Wl,-u` 名单正是这 5 个,注释还记着
「`XRSLAMTryGetLatestPose` 加进去链接期直接 Undefined symbol」。
(全归档的**全部**已定义全局符号是 2403 个,绝大多数是 OpenCV/yaml-cpp/内部 C++ 符号,不是 API。)

### 新产物 vs 出货 generic

新产物 API 面 **17 个**,是 generic 那 5 个的**严格超集,一个不缺**:

| 符号 | 出货 generic | 新产物 `8a1cc12` | 出货 gpufenothread |
|---|:--:|:--:|:--:|
| `XRSLAMCreate` | ✓ | ✓ | ✓ |
| `XRSLAMDestroy` | ✓ | ✓ | ✓ |
| `XRSLAMGetResult` | ✓ | ✓ | ✓ |
| `XRSLAMPushSensorData` | ✓ | ✓ | ✓ |
| `XRSLAMRunOneFrame` | ✓ | ✓ | ✓ |
| `XRSLAMGetPropagatedPose` | ✗ | **+** | ✓ |
| `XRSLAMGetPropagatedPoseRelation` | ✗ | **+** | ✓ |
| `XRSLAMGetBodyPoseRelation` | ✗ | **+** | ✓ |
| `XRSLAMGetInitCounters` | ✗ | **+** | ✓ |
| `XRSLAMGetSolverCounters` | ✗ | **+** | ✓ |
| `XRSLAMGetPendingWorkerFrames` | ✗ | **+** | ✓ |
| `XRGlobalLocalizerCreate` / `Enable` / `IsInitialized` / `QueryFrame` / `QueryLocalization` / `TransformPose` | ✗ | **+**(6) | ✓ |

- **多了 12 个**(6 个研究用 XRSLAM* + 6 个 XRGlobalLocalizer*)
- **少了 0 个**
- 与出货 `gpufenothread` 的 17 个符号 **集合完全相同,零差异**

### 台架/生产的 FFI 绑定能不能直接链

**能,而且比出货 generic 更宽松。**

| 消费方 | 需要的符号 | 新产物满足? |
|---|---|---|
| `vendor/xrslam/transport/PwXrslamTransportCore.cpp` | 5 个函数(`XRSLAMCreate/Destroy/GetResult/PushSensorData/RunOneFrame`),其余 `XRSLAMPose`/`XRSLAMImage`/`XRSLAM_SENSOR_*` 等 14 项都是**类型与枚举,不产生符号** | ✅ 全部满足 |
| `lib/vio/ffi/xrslam_bindings.dart` | `lookup` **18 个**符号 | ⚠️ 满足 5 个,**13 个仍缺** |

🔴 **`xrslam_bindings.dart` 里 18 个绑定中的 13 个,在出货 generic 和本新产物里都不存在**:
`XRSLAMGetBias` `XRSLAMGetBodyPose` `XRSLAMGetCameraPose` `XRSLAMGetDepthFusionStats`
`XRSLAMGetHealth` `XRSLAMGetIntrinsics` `XRSLAMGetLandmarks` `XRSLAMGetLandmarksEx`
`XRSLAMGetState` `XRSLAMGetVersion` `XRSLAMPushSensorDataChecked`
`XRSLAMSetHealthThresholds` `XRSLAMTryGetLatestPose`

这是既有状况(「绑定存在 ≠ 符号存在」),**不是本次构建引入的回归** —— 新产物在这一项上只增不减。
生产真正走的是原生 transport 那 5 个,不受影响。

---

## 5. 链接冒烟(未上机)

**结果:通过。**

```
PW_XRSLAM_ARM=repro \
PW_XRSLAM_LIB_PATH=~/Developer/viobench-build/engine/libxrslam_gpufenothread_8a1cc12.a \
flutter build ios --release --no-codesign
→ ✓ Built build/ios/iphoneos/Runner.app (35.0MB)   [Xcode build 20.4s]
```

### 怎么做到不碰出货 `.a`

🔴 `~/Developer/arloopbench/vendor/xrslam` 是**指向 `~/Developer/pocketworld/vendor/xrslam` 的符号链接**,
Podfile 里 `xrslam_dir = '$(PODS_ROOT)/../../vendor/xrslam/libs/ios-arm64'` 直接落在出货目录上。
所以**没有**把新产物拷进那个目录,而是给 Podfile 的臂开关加了第三档 `repro`,
用 `PW_XRSLAM_LIB_PATH` 吃**仓外绝对路径**。

### 运行期自证(按「换臂必须有运行期自证」的规矩做)

| 证据 | 结果 |
|---|---|
| 生成的 `Pods-Runner/*.xcconfig` | `-force_load ".../libxrslam_gpufenothread_8a1cc12.a"` ✓ |
| **指纹:二进制里那条 OpenCV 路径** | `strings Runner \| grep mat.inl.hpp` → **`…/scratchpad/build-run1/_deps/…`** ← 这条字符串**只有我这次的归档才有**,出货档里是 `…/xrslam-4beb1a9-thr/build-nothread/…` ⇒ **确凿证明链进去的是新产物,不是缓存里的旧臂** |
| 五个生产符号 | `nm -a Runner` 五个全部命中(`t _XRSLAMCreate` 等,地址连续 `0x100133d0c`–`0x100134008`) |
| 引擎代码真在 | 二进制含 411 条 `xrslam` 字符串,含 `Config::sliding_window_size:` 等 `config.cpp` 的字面量 |
| GPU 前端 / Dawn | `wgpuDevice`/`wgpuQueue` 符号 14 个 ✓ |

⚠️ 两点要说清:
1. 20.4s 是**增量** Xcode 构建。但链接步骤确实重跑了 —— 指纹字符串来自本次新建的归档,缓存里不可能有。
2. Release 下那 **12 个研究符号被 dead-strip 掉了**(无人引用 + `-fvisibility=hidden`),
   `nm` 里找不到。五个生产符号因为 transport 引用 + `-Wl,-u` 保活而在。
   将来若要从 Dart 侧 `lookup` 研究符号,须往 `-Wl,-u` 名单里补。

### 已还原

- `~/Developer/arloopbench/ios/Podfile` 恢复为原件,**sha256 `3986dce5c040ccdc…` 逐字节一致**,`diff` 为空
- 重跑 `pod install`(需 `LANG=en_US.UTF-8`,否则 CocoaPods 在 ASCII-8BIT 下崩),
  xcconfig 已回到 `libxrslam_generic_4beb1a9.a`
- 临时备份 `Podfile.pre-repro-smoke.bak` 已删除
- 出货 `.a` 校验:`libxrslam_gpufenothread_4beb1a9.a` = `2c2bc346…`、
  `libxrslam_generic_4beb1a9.a` = `fdc75c99…`,**与动工前完全一致,一个字节没动**

---

## 6. 另两项工程现状盘点(只盘点,未实施)

### (a) 消费层接线 —— 整层**零生产调用者**

`lib/vio/pose/` **12 个文件**、`lib/vio/quality/` **6 个文件**,约 4200 行、约 75 个公开契约。

**生产 `lib/` 调用者数:每一个契约都是 0。** 全仓 grep 后,`lib/` 里的非测试命中只有 2 条,
且**都是注释**:`lib/vio/ffi/xrslam_live_ffi.dart:10`、`lib/vio/ffi/xrslam_session.dart:100`。

唯一 import 这两层的生产代码是 `lib/vio/render/`(`ar_minimal_loop_page.dart:33-41` 等),
但**全仓没有任何地方 import 或引用 `lib/vio/render/`** —— 无路由、无 import、无测试。
它是个够不着的探针孤岛,所以并不能让 `pose/` 变活。`lib/vio/quality/` 连 render 都没引用,
**在 `lib/vio/` 内部都是 0 importer**。

测试覆盖是有的(`test/vio/pose/` 13 个文件、`test/vio_quality_*.dart` 6 个),所以这是
「测试养着、生产死着」。

**生产今天真正的位姿链路:**
1. `lib/ui/app_shell.dart:121` → 唯一挂路由的采集页 `OfficialARCapturePage`
2. `lib/ui/official_capture/ar_capture_page.dart:755` → `CaptureSession(targetPoints: …)`,**没传 `poseProvider`**
3. `lib/official_capture/capture_session.dart:714` → `poseProvider ?? PlatformARPoseProvider()` ← 默认绑 ARKit
4. `lib/official_capture/capture_session.dart:961` → `poseProvider.start().listen(...)` ← **唯一的生产位姿消费点**
5. `lib/official_dome/platform_pose_provider.dart:71` → EventChannel `pocketworld_official_arkit/pose_stream`

**最小接线点(缝已经在,而且干净):**
`ARPoseProvider` 是 `lib/official_dome/ar_pose.dart:591` 的抽象类(`Stream<ARPose> start()` 在 `:595`),
`CaptureSession` 本来就收可选的 `ARPoseProvider`(字段 `capture_session.dart:144`,构造参数 `:707`)。
只需写**一个** adapter 实现 `ARPoseProvider`,内部驱动
`EnginePosePoller`(`lib/vio/pose/engine_pose_poller.dart:105`)→ `VioPoseSource.update()`
(`lib/vio/pose/vio_pose_source.dart:93`)→ `TrackedPose` → `ARPose`,然后在
**`lib/ui/official_capture/ar_capture_page.dart:755` 这一行**传进去(最窄、可逆),
或改 `capture_session.dart:714` 的默认值(全局)。**今天仓里没有任何 VIO 版的 `ARPoseProvider`。**

🔴 两个坑:
- 类型缝:`lib/vio/pose/` 说 `TrackedPose`,生产说 `ARPose`(`lib/official_dome/ar_pose.dart:56`,
  还带 `extrinsic4x4`/`intrinsicFxFyCxCy`/`trackingStateName`)。
- `capture_session.dart:1599-1607` 目前用 `_lastPoseSource == 'arkit'` 闸住外参/内参,
  VIO 源会**静默丢掉外参内参**,除非同时改这个分支。

**开关现状:没有任何 VIO-vs-ARKit 的位姿开关。**
`lib/vio/diagnostics/vio_shadow_switch.dart:1-6` 的 `PW_VIO_SHADOW` 只闸
`VioDiagnosticsRecorder`(影子记录器,`ar_capture_page.dart:1203/1220`),ARKit 照常独占渲染与采集。
`lib/vio/capability/capability_decision.dart:31` 的 `enum PoseSource { selfVio, platformVio, none }`
正是该用的选择器类型,但**零生产调用者**,只被 `test/vio_capability_probe_test.dart` 引用。
`capture_session.dart:287` 的 `_lastPoseSource` 只在 `'arkit'`/`'imu'` 间翻,**从不取 `'vio'`**。

### (b) Android / 鸿蒙喂料链 —— 链条断在中间

**`~/Developer/pw_android_probe`:与 SLAM 无关。** 它是 Vulkan/WGSL 的确定性探针
(`android_probe.cc` 查子组宽度、cooperative-matrix,跑 WGSL 后比 SHA-256),
有 `apk/lib/arm64-v8a/libpwprobe.so`(14.6 MB)。全树 grep `camera2|ASensorManager|xrslam` **零命中**。

**`~/Developer/pocketworld/android_ready`:唯一的真 Android 传感器工作,46 个文件。**

| 环节 | 状态 |
|---|---|
| Gradle / app 壳 | ❌ pocketworld **根本没有 `android/` 目录**;这里只有 `.snippet` 文本,从未 apply |
| Kotlin | ❌ 6 个 `.kt` **从未编译过**(README 自述:本机无 Android SDK/kotlinc/JRE) |
| **相机源** | ❌ **没有**。`kotlin/…/PwCameraProbe.kt` 只读 Camera2 **元数据**(`SENSOR_INFO_TIMESTAMP_SOURCE`、`LENS_INTRINSIC_CALIBRATION`、`LENS_DISTORTION`)并调 `CaptureRequest.Builder`(关 EIS/OIS/畸变校正)。全树无 `ImageReader`/`AImageReader`/`CameraX`/`SurfaceTexture`/capture session ⇒ **今天一帧都到不了 XRSLAM** |
| **IMU 源** | ⚠️ **有代码,但没接上**。`kotlin/…/PwImuSource.kt`(149 行)用 `SensorManager` + `TYPE_GYROSCOPE_UNCALIBRATED`/`TYPE_ACCELEROMETER_UNCALIBRATED`,`maxReportLatencyUs=0` 跑在专用 `HandlerThread`;`PwCapturePlugin.kt` 经 EventChannel `pocketworld/android_capture/imu` 送到 Dart,**到此为止** |
| **断点(承重)** | 🔴 `PwXrslamTransport.kt` 声明了五个 JNI extern + `System.loadLibrary("pw_xrslam_transport")`,C++ 侧 `native/xrslam/PwXrslamTransport.cpp` 也有对应 `Java_com_pocketworld_capture_PwXrslamTransport_*`,**但 `PwXrslamTransport` 没有被 `PwCapturePlugin.kt`、任何 Dart 文件、任何 gradle snippet 引用过**(全仓 grep `pw_xrslam_transport` 在 `.dart/.kts/.snippet/.yaml` 里 **零命中**)⇒ IMU 读了但从不 push,相机帧根本不产生 |
| 预编译产物 | ✓ `android_ready/native/xrslam/libs/arm64-v8a/libxrslam_generic_4beb1a9.so`(341 MB,未 strip),导出正是那 5 个符号,16 KB 页对齐;回执标 `artifactProvenanceStatus: "pending_deterministic_rebuild"`(**尚未从固定配方复现过**) |
| 构建配方 | ✓ `native/xrslam/build_generic_core.sh` 是完整的:clone `openxrlab/xrslam@4beb1a9` + OpenCV `c9ad577` + Ceres,打 `patches/xrslam_generic_mobile.patch`,NDK 钉 `29.0.14206865`,`ANDROID_ABI=arm64-v8a`、`ANDROID_PLATFORM=android-24`。🔴 它**从 GitHub 拉源码,不从本机任何 checkout 构建** |
| **逐机型 `p_bc`** | ❌ **0 个 Android yaml**。对照:`xrslam-ios/visualizer/configs/` 两棵树各 **18 个 iPhone yaml**(18/18 含 `p_bc`/`q_bc`/`time_offset`)。pocketworld 自己 0 个设备 yaml —— iOS 配置是 `lib/vio/ffi/xrslam_config.dart` 的 `XrslamConfigBuilder` 按 `hw.machine` **运行时生成** `device_config.yaml`(`xrslam_session.dart:183` 写盘);**该文件没有 Android 分支**,`lib/vio/` 下 `Platform.isAndroid` 零处 |

**xrslam 源码树的 Android 支持:**
- `~/Developer/xrslam`(`pw/vio`)**有** `if(ANDROID)` 分支(`CMakeLists.txt:53/70/76-79/82`,
  含 `XRSLAM_ANDROID ON`、Android 侧 `THREADING ON`)+ `cmake/Modules/XRSlamHardening.cmake`(16 KB 页断言、NDK 链接器绕坑);
  `xrslam-interface` 在非 iOS 上建 **SHARED** ⇒ `libxrslam.so` 可产。
  🔴 但**缺 Android toolchain**:`SuperBuildDepends.cmake:41` 指的 `cmake/external/android/` **不存在**,
  无 `build-android.sh`,全机 `find -name 'libxrslam*.so'` 只有 `android_ready/libs/` 那一个。JNI glue 零。
- `~/Developer/xrslam-4beb1a9-thr`(本次构建树)**完全没有 Android 支持**,`if(ANDROID)` 一处都没有。

**鸿蒙 / OHOS:基本不存在。** 全部实体只有
`~/Developer/xrslam/cmake/depends/ceres-solver.cmake:35-36` 里一个 `OHOS` 条件 token + 中文注释;
其余全是 markdown 规划文字(`PORTING_BACKLOG.md:47` 标 Phase 7+ 延后)和 `pubspec.yaml:131/165` 的注释。
无 `ohos/` 目录、无 ArkTS、无 `.hap`、无 SDK、无工具链。

---

## 7. 没做 / 做不到的

1. **没 push** —— 两个 remote 都是第三方项目(§1),等用户的 remote 或一句确认。
2. **没重建历史构建树** `~/Developer/xrslam-4beb1a9-thr/build-nothread` ——
   它是出货档来源的现存唯一物证,不该被 `--clean` 抹掉。
   因此「与 `2c2bc346` 逐字节相同」是**论证充分但未直接执行**:
   53/58 成员实测逐字节相同 + 4 个成员的差异逐字节归因到路径字符串 + 原构建树 `.o` 与出货成员逐字节相同。
3. **没上机**(按约束不碰 iPhone、不开摄像头)。所以新产物**只有链接级证据,没有运行/精度证据**。
   出货回执里那两项 `verification_pending_zh`(真机直播吞吐、EuRoC/回放 ATE 落带)对新产物**同样未做**。
4. **selfcheck 未复跑** —— `sqrt 4804/16384`、`未保护乘加 4655/16384` 那份自检需要真机跑
   `gpu_image.cpp` 的 init 痕迹,本次无法执行。新产物的 GPU 前端伴随库
   (`libpw_gpu_frontend_ios.a`,sha256 `ad0a4abe…`)与出货档用的是**同一个文件**,所以
   那份 selfcheck 结论可以沿用,但**没有重新验证**。
5. **`research_only` 血统没变** —— 新产物同样标 `research_only: true` / `product_selected: false`。
   「全面持平/超越 ARKit 之前不上生产」的铁律不因为可复现而松动;
   本次交付解决的是**谱系**问题,不是**质量**问题。

---

## 附:关键路径速查

| 用途 | 路径 |
|---|---|
| 构建脚本 | `~/Developer/viobench-build/gpufe/build_gpufe_nothread.sh` |
| 新归档 / 收据 | `~/Developer/viobench-build/engine/libxrslam_gpufenothread_8a1cc12.{a,receipt.json}` |
| 源码 commit | `~/Developer/xrslam-4beb1a9-thr` @ `build/gpufe-nothread-20260922` = `8a1cc12` |
| 出货档(未动) | `~/Developer/pocketworld/vendor/xrslam/libs/ios-arm64/libxrslam_gpufenothread_4beb1a9.a` |
| 臂开关 | `~/Developer/arloopbench/ios/Podfile`(已还原;`PW_XRSLAM_ARM=gpufenothread`) |
| 消费层接线点 | `~/Developer/pocketworld/lib/ui/official_capture/ar_capture_page.dart:755` |
| Android 断点 | `~/Developer/pocketworld/android_ready/kotlin/com/pocketworld/capture/PwXrslamTransport.kt`(无人引用) |
