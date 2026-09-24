# LOD 接入 arloopbench 方案(待批)

**日期**:2026-09-24
**性质**:方案，全程只读调查写成。没改产品仓、arloopbench、Aether3D,没装机，没推送，没碰 `com.kyle.PocketWorld`。
**用户已定(本方案不再讨论)**:
1. 每帧上传上限保持 2(照抄 Potree)。
2. 产品规矩改为「全量存盘、任一点拉近可见」。措辞和契约测试在接 LOD 时一起改，现在不改。
3. 接入 arloopbench 先出方案给用户批。

---

## 0. 一页摘要

| 问题 | 结论 | 推荐 |
|---|---|---|
| 目标形态 | 产品仓新开 `feat/lod-viewer`(永不上生产);八叉树在手机上用 PR #100 建;同步到 arloopbench,在台架上真机测 | — |
| 坑 (a):FFI 产物 | **不重编** 8 月 7 日的 `libaether3d_ffi.a`。三份 Dawn 同源(`12ee391c`),导出的 276 个 `wgpu*` 完全一致 ⇒ LOD 单独出一个不含 Dawn 的小库，照 `vendor/xrslam` 的回执格式钉住 | A1(§3a) |
| 坑 (b):主线程死等 GPU | 照官方相机插件：后台线程渲染，交出前先确认 GPU 已完成;3 个缓冲轮转;`textureFrameAvailable` 回主线程发;`copyPixelBuffer` 只返回最新完成的缓冲 | B1(§3b) |
| 分支血统 | `feat/bench-replay` 从分叉点起**没碰**查看器和纹理文件;稠密查看器的改动只在 dense-168 那条线 | LOD 分支从 `feat/bench-replay` 切，数据路径不依赖稠密阶段(§4) |
| 跨端 | 引擎只收一个 `WGPUTexture` 当渲染目标;iOS、安卓、鸿蒙各一层很薄的外壳。官方都有外部纹理 API(`SurfaceProducer`、`OHNativeWindow`),Dawn 也都有对接 API | 不做任何只能 iOS 的设计(§5) |
| 真机测量 | 两级:M1 引擎级(`pwlod_run` 原样带进台架，跑 r3 的 S/A/AP 臂);M2 端到端查看器帧节拍(坑 b 解决后) | 先 M1 |
| 需用户批准 | 本方案;坑 a/b 选项;每次装机;任何推送;改 `CLAUDE.md:14` 和契约测试 | §7 |

---

## 1. 目标形态

- **复看页用 LOD 显示稠密点云**:做在产品仓 `pocketworld` 的功能分支 `feat/lod-viewer` 上。这个分支永不合入生产线，永不装到 `com.kyle.PocketWorld`。
- **八叉树在手机上建**:用 PR #100(`origin/feat/pointcloud-lod-build` @ `d87b5806`)的 `buildFromPly`(`aether_cpp/include/aether/pointcloud_lod_build/build.h:119`)。
  - 输入就是产品稠密阶段输出的 `official_dense.ply`(dense-168 分支 `lib/dense/native_dense_stage_launcher.dart:24`)。
  - 格式正是 `openPly` 接受的格式：binary little-endian,15 B/点(`build.h:113-117`)。
  - 不走云端(`pocketworld/CLAUDE.md:11`)。
- **同步到 arloopbench 再真机测**(`com.kyle.arloopbench`,`ios/Runner.xcodeproj/project.pbxproj:597`)。规矩照台架现有的「改产品仓再同步」(`arloopbench/.sync_from_integration.sh:2-3, :73`)。

---

## 2. 按层改动

每层写三件事：抄谁、改哪些文件、怎么验证(判据都能失败，带阴性对照)。「新文件名」都是建议，仓里还不存在。

### L1 引擎：点云 LOD 渲染 pass(Aether3D,新本地分支 `feat/pointcloud-lod-viewer`)

**抄谁**
- 选择、流式、控制器：原样用 `aether::pointcloud_lod`(`feat/pointcloud-lod-async` @ `d251451`)。
- 四边形点路径：抄台架 `pw_splat_ab_bench/Sources/lod/pw_lod_bench.cpp`(已在 Mac 上验过)。它自己又是抄 `bench_cloud.mm` 的 `kWgslCloud`,渲染状态照生产 splat pass(`scene_iosurface_renderer.cpp:555-585`,台架 REPORT §2)。
- 自适应点大小:Potree `pointcloud.vs @ 5636cd4 :158-254, :301-303, :666-705`,偏离 P1–P6 已记录。
- 与建树合流：把 `feat/pointcloud-lod-build`(8 个提交、22 个文件，只加文件，另改 `CMakeLists.txt` 和 `NOTICE`)合进来。
- **没有现成可抄的只有一样**:对外 C 接口的形状。那就照家里现成的 `aether_scene_renderer_*` 12 个入口的形状写(`include/aether/pocketworld/scene_iosurface_renderer.h:49-190`)。

**改哪些文件**
- 新模块 `aether_cpp/{include/aether,src}/pointcloud_lod_render/`:把 `pw_lod_bench.cpp` 里的 `Pipe`、`LodFrame`、`BuildVisibleNodeTable` 和 WGSL 原样搬过去。
- **渲染目标由调用方给一个 `WGPUTexture`,引擎自己不建 IOSurface。**
- **不动** `scene_iosurface_renderer.cpp`。它有 `#if !defined(__APPLE__) return nullptr` 守卫(`:1487-1489`),而且编在 ffi .a 里(见 §3a)。

**怎么验证(Mac,主机测试，注册进 `foreach(pwlod_test …)` 列表)**
把台架 `mode=correct` 的判据原样搬成 ctest:
- 叶节点可见，带「少画该叶」和「忘加 origin」两个阴性对照。
- getLOD 三方核对，带清零掩码阴性对照。
- 异步收敛后与同步逐位相同，带「少画一个可见节点」阴性对照。
- 透视到后面低于底噪。

Mac 参考值见 `pw_splat_ab_bench/results_mac_20260924_async_adaptive/summary_correct_{36M,216M}.txt`。

### L2 C 接口

**抄谁**:家里 `aether_scene_renderer_*` 的形状(`scene_iosurface_renderer.h:49-190`)。Dawn 关闭时的桩函数照 `scene_iosurface_renderer.cpp:3926-3937`。

**改哪些文件**:新增 `pwlod_viewer.h`,入口建议如下:
- `pwlod_viewer_create(WGPUDevice, WGPUQueue)`
- `pwlod_viewer_load_octree(dir)`
- `pwlod_viewer_set_camera(viewProjRowMajor[16], eye[3], fovY, heightPx)`
- `pwlod_viewer_set_params(budget, psizeMode, asyncMode)`
- `pwlod_viewer_frame(WGPUTextureView target, stats*)`
- `pwlod_viewer_destroy`

**ABI 里不出现任何平台类型**。IOSurface、AHardwareBuffer 都在外壳里导入成 `WGPUTexture`(§5)。

**怎么验证**
- 主机测试：同一个八叉树，走 C 接口和走 C++ 直调的输出图必须逐位相同。
- 阴性对照：把 `set_camera` 的行主序故意传成转置，必须不同。

### L3 FFI 产物

见 §3a。推荐 A1:产物 `vendor/aether_lod/libs/ios-arm64/libpw_lod_<sha8>.a`,外加同名的 `.receipt.json` 和 `.syms.txt`,再加一个 `build_ios_lod.sh --verify-only`。

**抄谁**:产品自己的 `vendor/xrslam/libs/ios-arm64/libxrslam_generic_4beb1a9.receipt.json` 回执格式，包括 artifact sha、成员清单 sha、上游 revision、声明的补丁 sha。以及 `vendor/xrslam/build_ios_generic.sh` 头注释写的「钉死出货件，行为门判替换」纪律(在 bench-replay 工作树)。

**怎么验证**
- `--verify-only` 校验归档 sha、成员清单、导出符号表和 `.syms.txt` 一致。
- 阴性对照：往归档里多塞一个成员，必须报错。

### L4 Dart 绑定

**抄谁**:家里纹理渲染器的做法。Dart 侧用 `MethodChannel`(`lib/aether_view/scene_bridge.dart:10-18, :71`),Swift 侧用 `@_silgen_name` 直接声明 C 函数(`ios/Runner/MetalRenderer.swift:17-92`)。**不走** `DynamicLibrary.process()` 查新符号，免得还要去改导出白名单(台架 `ios/Podfile:155-161` 注释)。

**改哪些文件**:新增 `lib/point_cloud_lod/lod_bridge.dart`,通道名 `pw_lod_texture`,方法有 `create`、`loadOctree`、`setCamera`、`stats`、`dispose`。

**怎么验证**
- Dart 单测把通道 mock 掉，检查参数编组(行主序 16 个 double)。
- 阴性对照：打乱顺序必须被检查到。

### L5 Flutter 视图

**抄谁**
- `Texture(textureId:)` 的用法：`lib/ui/community/aether_cpp_card_demo.dart:612`。
- 手势、轨道相机：`lib/ui/official_capture/sparse_cloud_view.dart`。
- 透视投影照 LOD 库测试里的相机(`tests/pointcloud_lod/test_select.cpp:51-80`)。

**要用户知道的一个变化**:现有查看器默认是正交投影(`sparse_cloud_view.dart:199` `kCloudOrthographic = true`)。而 Potree 的正交可见性上游本身就是 `// TODO ortho visibility`(`Potree_update_visibility.js:382-390`),我们也按 D7 没抄。所以 **LOD 页只能用透视**。

**改哪些文件**:新页 `lib/ui/official_capture/lod_cloud_view.dart`。它不改旧查看器，也不删任何功能：选区、双击拾取仍留在旧页。

**怎么验证**:设备上读回一帧，跑与 Mac 相同的非平凡判据(覆盖率、饱和度、通道标准差)。阴性对照：平灰图必须被拒。

### L6 数据：手机端建树接入

**抄谁**
- PR #100 的 `optionsForBudget(outDir, chunkDir, memoryBudgetMB, numThreads)`(`build.h:85-90`)。
- 手机默认参数：4 线程、64 MiB 环形缓冲、128 MB 积压、100 万点分块上限。桌面实测 36M 用 519 MB / 24.3 s(`src/pointcloud_lod_build/DEVIATIONS.md:241-248`)。**手机上从没测过**(同文件 :248)。

**改哪些文件**
- 原生外壳加一个后台建树入口，放在 L2 那个库里:`pwlod_build_from_ply(ply, outDir, chunkDir, budgetMB, threads, report*)`。
- 输出目录 `Documents/<capture>/lod/`。

**怎么验证**:这正好就是用户改过的新规矩，「盘上点数不少 + 每个叶节点都拉得到」。
- **C1**:树内点数 = PLY 点数，且等于 `octree.bin` 大小 ÷ 18。
- **C2**:节点字节区间铺满 `octree.bin`,无缝隙无重叠。
- **S2**:遍历每个叶节点，相机放到它跟前，必须被选中。
- 这三条都在库里现成(`tests/pointcloud_lod/test_octree.cpp`、`test_select.cpp`),做成台架里的自检即可。
- 再加一条「与 Mac 用同一 PLY、同一参数建的树逐节点相同」:PR #100 在桌面上已证逐节点相同(`DEVIATIONS.md:289-300`),在手机上未验证。
- 阴性对照：截断的 PLY 必须被 `openPly` 拒绝(`build.h:113-117`)。

### L7 同步脚本

**抄谁**:`arloopbench/.sync_from_integration.sh` 自己的写法，包括逐字节 cmp 闸、「多出生产没有的文件」闸、以及显式列出镜像范围(`:73-79, :84`)。

**改哪些文件**
- 镜像加上 `lib/point_cloud_lod/**`、`lib/ui/official_capture/lod_cloud_view.dart`、`ios/Runner/PwLod*.swift`、`vendor/aether_lod/**`。
- 台架自有的文件(`pbxproj`、`Podfile`、桥接头、`main.dart`)照旧不镜像(`:73`)。
- `sync_from_production.sh` 目前在 `:53` 那一行会中止(调查实测),它不在 LOD 的路径上，本方案不碰。

**怎么验证**
- 同步后逐字节 cmp 全过。
- 阴性对照：在台架里改一个镜像文件，下次同步必须报错。

### L8 台架构建

**改哪些文件(都是台架自有文件)**
- `ios/Podfile`:在 post_install 里加 LOD 归档的 `-force_load`,写法照现有的 GPU 前端臂(`ios/Podfile:119-126, :173-182`)。Release Dawn 改为**无条件**以普通归档链入：现在只有 GPU 前端臂才链(`:119`);不能 force_load,否则与任何另一份 Dawn 重复定义(§3a)。不加 ffi pod。
- `lib/main.dart`:加一个 `PW_LOD_BENCH` 开关，写法照 `:54-66` 那串三元表达式。
- 先 `pod install`(调查发现 xcconfig 早于 Podfile,已过期)。

**构建和装机**
- 构建模式有矛盾：产品规矩要求真机包用 `--profile`,因为 debug 脱离调试器即崩(`pocketworld/CLAUDE.md:12`);而台架 `ios/Podfile:160` 的注释说「台架是 debug」。M1 必须 detached 启动，所以用 `--profile`。台架能否用 profile 构建通过，未验证。
- 装机只用 `xcrun devicectl device install app` 装 `com.kyle.arloopbench`。台架目录里**没有构建脚本**,以往的流程只在会话记忆里。

**怎么验证**
- 装机前核对 bundle id 等于 `com.kyle.arloopbench`、深签名有效。
- `nm` 核对 LOD 符号在二进制里。
- 阴性对照：LOD 开关关着时，页面入口必须不可达。

---

## 3. 两个坑

### 3a. FFI 产物：重编 `libaether3d_ffi.a` 会带进一个半月的引擎改动

**事实**(只读取证，证据在 `…/scratchpad/bline/ffi_forensics/`)

*产品 App 里实际跑的是 ffi 自带的那份 Dawn*
- 真机链接顺序(`pocketworld/vendor/aether_ffi/aether3d_ffi.podspec:96`,生成的 `Pods-Runner.release.xcconfig:14` 相同):先 `-force_load libaether3d_ffi.a`,再是 glomap、pwsfm,然后 Debug 版 `libwebgpu_dawn.a` 作**普通归档**,最后 jpeg、ceres、glog、sqlite3。
- ffi 被整个 force_load 进来，已经定义了全部 `wgpu*`,所以 Debug 版 Dawn 一个成员也不会被拉进来。
- 实物印证(Runner-168):ffi 独有的 Dawn 符号 597 个里有 570 个在二进制里;Debug 版独有的 818 个一个都没有。

*三份 Dawn 的 API 名字完全一样*
- ffi 自带的、Debug 版(9 月 7 日)、Release 版(9 月 11 日)三份，导出的 `_wgpu*` 都是 **276 个**,名单的 sha1 相同，差集为 0。
- 与台架编译用的 `webgpu.h`(sha `6d632738…`)里全部导出函数比，差集也是 0。
- Dawn 子模块的 gitlink 在 `b930ab1851`、`849c4d6b01`、HEAD 上都是 `12ee391c`。
- ⇒ ABI 兼容(推断，可信度高)。

*arloopbench 现在不链 ffi*
- `ios/Podfile:88-89` 的注释写明台架没有 `aether3d_ffi`。
- GPU 前端臂只 force_load 前端库，Release Dawn 是**普通归档**(`ios/Podfile:120-126`)。
- 若把两份 Dawn 都改成 force_load,276 个强定义的 `wgpu*` 会重复定义，链接报错。

*8 月 7 日 .a 的来源*
- 合并配方(`~/Documents/progecttwo/_artifacts/gpu_hang_recovery_20260806/source_snapshot_detox/merge_command_record.txt`)和合并中间产物都在。
- 源码 ≈ `849c4d6b01`。
- 但当时的编译产物和编译配置已经没了或被改过：Dawn 断言状态、libc++ ABI 标签都不同。**逐位重建无证据。**

**选项 A1(推荐):LOD 单独出一个小静态库，旧 .a 一个字节不动**
- `libpw_lod_<sha8>.a` 只含纯 C++ 的 `pointcloud_lod` 和 `pointcloud_lod_build`,加上渲染 pass、C 接口。**不含 Dawn**,`wgpu*` 全部留作未定义符号。
- 用 `6d632738` 头文件编译。
  - 在台架里，它绑到台架已有的 Release Dawn。Dawn 要**无条件**以普通归档链入，因为现在只有 GPU 前端臂才链(`ios/Podfile:119`)。
  - 在产品功能分支里，它绑到 ffi 自带的那份 Dawn。三份同源，见上。
- LOD 渲染器**自己建 Dawn instance 和 device**,台架 `pw_lod_bench.cpp` 就是这么做的。原因：ffi 的 C 接口里没有取设备的函数，只有 C++ 内部符号 `dawn_singleton_acquire()` 等，不去依赖它们。
- 单变量成立：旧 ffi 和生产渲染器都不动。

**选项 A2:按 8 月 7 日的配方重编 ffi .a 并加入 LOD**
- 只有一份 Dawn、一个设备。
- 但编译配置已变，逐位重建无证据。家里 xrslam 的经验也是逐字节复现试过并失败(`vendor/xrslam/build_ios_generic.sh` 头注释)。
- 只能用行为门判能否替换，工作量和风险都更大。

**推荐 A1。** 残余风险有两条:
- 进程里会有两个 Dawn device(生产渲染器一个,LOD 一个)。在台架里没有这个问题。
- 在产品里，死代码剥离开着(`Runner.xcodeproj/project.pbxproj:665` `DEAD_CODE_STRIPPING = YES`)。LOD 的入口要靠 `-Wl,-u` 或 force_load 保住。不要用 `-exported_symbol`,台架 `ios/Podfile:155-161` 记录过它会让 debug 包启动即崩。

### 3b. IOSurface→FlutterTexture:主线程每帧死等 GPU

**事实**
- 纹理由 `CADisplayLink` 驱动，挂在主线程(`ios/Runner/AetherTexturePlugin.swift:485-487`)。
- 每帧提交后用 `wgpuInstanceWaitAny(…, UINT64_MAX)` 死等(`scene_iosurface_renderer.cpp:3897-3914`)。
- 只有**一个** IOSurface,Dawn 写、Flutter 读的是同一块(`MetalRenderer.swift:121, :165-177`)。

**Flutter 官方契约**(以下简写:F=`flutter/flutter@104d0fbc5acf`,P=`flutter/packages@fbc80a62002`;本地副本在 `…/scratchpad/bline/flutter_src/`)
- `copyPixelBuffer` 在 **raster 线程**上被调用(`FlutterTexture.h:57`)。引擎把返回值当作 +1 引用接管，并一直采样最近拿到的那个缓冲(`FlutterDarwinExternalTextureMetal.mm:84-88`)。
- **iOS 引擎对缓冲不做任何 GPU 同步**:没有 fence、事件或等待(同文件 :235-243 只把 IOSurface 包成纹理)。⇒ 只能交出 GPU 已经写完的缓冲(推断)。
- `textureFrameAvailable:` 必须在**平台线程**调用(`FlutterTexture.h:53-59`;引擎在 `shell.cc:1335` 用 DCHECK 强制)。本机锁定的 3.47.1 头文件里没有这句，但引擎的强制仍按上游对待。
- 相机插件的做法：采集放后台串行队列(`CameraPlugin.swift:38`,`DefaultCamera.swift:196`);「最新缓冲」由另一个专用串行队列保护(`DefaultCamera.swift:28-31`);生产者写入后通知(:1283-1296);通知时 `DispatchQueue.main.async { textureFrameAvailable }`(`CameraPlugin.swift:297-303`,`QueueUtils.swift:17-25`);`copyPixelBuffer` 取出最新缓冲，retain 后返回，从不等待(`DefaultCamera.swift:1518-1529`)。
- 视频插件的做法：display link 回调里**只调通知，不渲染**(`FVPFrameUpdater.m:15-18`);`copyPixelBuffer` 非阻塞地拉帧，没有新帧就重发旧帧(`FVPTextureBasedVideoPlayer.m:145-154, :204-206`)。
- 官方从未明写「copyPixelBuffer 不得阻塞」(未验证);但它在 raster 线程上被同步调用，阻塞会直接顶住 raster 线程。

**选项 B1(推荐):照相机插件的形状**
- 专用渲染线程(std::thread,引擎侧)负责：选择、编码、提交。
- 完成信号用 `wgpuQueueOnSubmittedWorkDone` 的回调，不死等。Dawn 有这个 API(`dawn@b6f5965:src/dawn/dawn.json:3063`),尚未实测。
- 用 **3 个** IOSurface 轮转，因为引擎会一直持有并采样最后给它的那个。
- GPU 写完后，在锁或串行队列里把它设为「最新」,再 `DispatchQueue.main.async { textureFrameAvailable }`。
- `copyPixelBuffer` 只返回最新完成的那个并 retain,不等任何东西。
- 主线程只做手势，把相机参数原子地写给渲染线程。

**选项 B2:仍由主线程的 display link 驱动**
- 把死等换成回调，加双缓冲。
- 选择、编码的 CPU 时间仍压在主线程上。官方两个插件都没这么做：视频插件的 display link 只发通知。

**推荐 B1。**

**怎么验证**
- 在台架里记录主线程每帧占用、`copyPixelBuffer` 耗时、交出的帧号。
- 判据：主线程每帧 p99 < 2 ms;`copyPixelBuffer` p99 < 0.5 ms;交出的缓冲都已完成 GPU 工作(用完成回调的计数对账)。
- 阴性对照：打开「渲染线程每帧 sleep 50 ms」,`copyPixelBuffer` 仍须立即返回旧帧，而帧号停滞必须被检出;打开「不等完成就发布」,对账必须报警。

## 4. 分支血统

**事实**(产品仓只读 git 实测)
- 分叉点 `59e8f5ba`(2026-09-07)。`feat/bench-replay` 领先 98 个提交，`feat/review-cloud-cache-on-dense-stage-168` 领先 235 个。
- 从分叉点起，**bench-replay 对这些文件的改动都是 0**:`sparse_cloud_view.dart`、`sparse_cloud_viewer_page.dart`、`lib/point_cloud_display/`、`lib/aether_view/`、`AetherTexturePlugin.swift`、`MetalRenderer.swift`、`vendor/aether_ffi/`。
- dense-168 对这些的改动:`sparse_cloud_view.dart` +167 行、`sparse_cloud_viewer_page.dart` +105 行、`lib/point_cloud_display` +16 行、`lib/dense` +1388 行。
- bench-replay 只改了 `ios/Podfile`(104 行)。

**推荐做法**
- `feat/lod-viewer` **从 `feat/bench-replay` 切**。这样满足同步脚本对源工作树的要求(`.sync_from_integration.sh:8-11`)。
- LOD 页是**新文件**,不改旧查看器，所以不需要 dense-168 在查看器上的任何改动。
- 台架上的数据从 PLY 推进容器、在手机上建树开始，**不依赖稠密阶段代码**。
- 等以后产品真要把「稠密 → 建树 → LOD 页」串成一条链，再单独出一个合流分支。只拣选 `lib/dense` 那组提交，交用户批，本方案不做。
- 防混入：同步脚本只镜像 §2 L7 列出的路径。「多出文件」闸会把任何范围外的文件点名。

---

## 5. 跨端

**现状**
- 纹理通路只有 Apple:IOSurface 加 `SharedTextureMemoryIOSurface`(`include/aether/render/dawn_gpu_device.h:125-160`),另有 `scene_iosurface_renderer.cpp:1487-1489` 的 Apple 守卫。
- 产品没有 `android/` 这个 Flutter 宿主。

**本方案的做法：不做任何只能 iOS 的设计**
- **引擎(L1、L2)只接收调用方给的 `WGPUTexture` 或 `WGPUTextureView`**。零平台类型、零平台分支。渲染线程是 std::thread。延续新增代码剥注释后 grep = 0 的自证。
- **iOS 外壳**:IOSurface → `SharedTextureMemoryIOSurface` 导入(本机 Dawn 头 `webgpu.h:2741`),按 §3b B1 交给 FlutterTexture。
- **安卓外壳**(以后做，但接口现在就按它设计)
  - 官方 API:`TextureRegistry.createSurfaceProducer()`,由 `getSurface()` 给出绘制目标 Surface(F `…/android/io/flutter/view/TextureRegistry.java:20-30, :137-139`),并有 `setCallback` 和清理回调(:159-166, :215-246)。
  - 迁移文档:https://docs.flutter.dev/release/breaking-changes/android-surface-plugins(3.22 落地、3.24 稳定)。
  - 消费端自带 fence 等待(`FlutterRenderer.java:789-791, :895-903`)。
  - 我们这边:Dawn 从 `ANativeWindow` 建 surface(`WGPUSurfaceSourceAndroidNativeWindow`,`webgpu.h:3037`;`dawn.json:4005-4012`),渲染线程直接呈现到这个 Surface。
  - 另一条路:`AHardwareBuffer` 共享纹理(`webgpu.h:2657`,特性位 `:622`)。
- **鸿蒙外壳**(以后):官方 OpenHarmony Flutter 有外部纹理 API。
  - `registerTexture` 返回的对象可取 `OHNativeWindow*`,注释写明可用于创建 VkSurface(`openharmony-sig/flutter_engine@586a3d4:shell/platform/ohos/flutter_embedding/flutter/src/main/ets/view/TextureRegistry.ets:18, :50-60`)。
  - 引擎自己会回到平台线程标记新帧(`platform_view_ohos.cpp:603-633`)。
  - Dawn 的 Vulkan 后端能否吃 `OHNativeWindow`,**未验证**。
- 引擎这一层已证过能跨编：台架 `pw_lod_bench.cpp` 用 Android NDK 编译并链接了 Android 版 Dawn,严格旗标通过，但没在安卓上跑过。

## 6. 真机测量(在 arloopbench 上)

分两级。**先做 M1**。

### M1 引擎级：回答「A16 上 S/A/AP 三臂能否稳定 30 fps」
- 把 `pw_lod_bench.cpp` 和 `pwlod_run` 原样作为台架的原生测量模式带进 arloopbench。代码也走产品仓功能分支，再同步。
- 离屏渲染，与 Mac 同口径，按 r3 方案跑:`pw_splat_ab_bench/LOD_DEVICE_PLAN_20260923.md` §12。
  - 同一进程里 S / A / AP 三臂轮内轮换，每臂带一个重复臂当噪声底。
  - 有效性闸：阳性对照、丢节点 0、热状态。
  - 判据：可消除超时帧、帧内 I/O p99、异步的细节滞后、「稳定 30 fps」六条。
  - 分析直接用现成的 `analyze_lod.py`。
- 启动方式照 `pocketworld/CLAUDE.md:13`:detached 启动，结果写 App 容器，事后 `devicectl device copy from` 拉回。
- 用户说「在了」之前不启动。

**数据**
- 36M 的 PLY 推进容器，**在手机上建树**,记录耗时和峰值内存。这是 L6 的判据，也补上 PR #100 缺的手机实测。
- 216M 的 PLY 有 3.25 GB,加上树 3.9 GB,**需要约 7.5 GB 手机空间**。先只做 36M,216M 等用户确认空间后再做。

### M2 端到端：查看器里的帧节拍
坑 3b 解决后再做。它测 Flutter raster 线程取帧的间隔、主线程占用，以及 `copyPixelBuffer` 的耗时。

---

## 7. 顺序、并行、工作量、批准点

| # | 步骤 | 位置 | 可并行 | 工作量(估) | 需用户批准 |
|---|---|---|---|---|---|
| 0 | 批本方案，选定 3a / 3b 的选项 | — | — | — | **是** |
| 1 | (已完成)Dawn 版本对账：三份同源，可以用 A1 | 只读 | — | — | 否 |
| 2 | L1 + L2:合入建树分支，渲染 pass 与 C 接口，Mac 主机测试 | Aether3D 本地 | 与 1 并行 | 1.5–2 天 | 否(推送要批) |
| 3 | L3:构建 iOS 归档，回执、符号表、`--verify-only` | Aether3D + 产品分支 | 2 之后 | 0.5 天 | 否 |
| 4 | L4 + L5 + L6(iOS 外壳，按 B1):渲染线程、三缓冲、`MethodChannel`、LOD 页、后台建树 | 产品 `feat/lod-viewer` | 与 3 可并行(先用桩) | 2 天 | 否(推送要批) |
| 5 | L7 + L8:同步、`pod install`、`--profile` 构建、核对 bundle id | arloopbench | 3、4 之后 | 0.5 天 | 否 |
| 6 | **装机**(只装 `com.kyle.arloopbench`),推 36M 的 PLY | 手机 | — | 0.5 天 | **是**,且要手机剩余空间确认 |
| 7 | M1 真机测(建树 + S/A/AP) | 手机 | — | 0.5 天加用户在场 | **是**(用户说「在了」) |
| 8 | M2 端到端 | 手机 | 7 之后 | 1 天 | **是** |
| 9 | 改 `CLAUDE.md:14` 措辞和契约测试(改成「盘上点数不少 + 每个叶节点可达」) | 产品仓 | 在 LOD 真正进复看页时 | 0.5 天 | **是** |

- 相互不耦合、可以并行的：3 与 4(4 先用 C 接口的桩);L6 建树入口与 L1 渲染 pass。
- 每步都在本地小步提交。任何推送都要用户逐次批准。

---

## 8. 未验证清单(方案成立前或实施中要补的)

1. 三份 Dawn 在 ABI 上逐字节相同(导出名一致、同一个 gitlink,但 8 月当时的 `webgpu.h` 没留下来)。本地 Dawn 工作树的 Metal 补丁 `[PW-MIXED-MMA 2026-09-03]` 是否也在 ffi 那份里：只改实现，不改接口。
2. 产品里同一进程存在两个 Dawn device(生产渲染器一个,LOD 一个)会不会出问题。台架里没有这个问题。
3. `wgpuQueueOnSubmittedWorkDone` 回调模式在 iOS 上的行为，以及 3 缓冲轮转够不够(官方源码只支持「要轮转」,没给数)。
4. 官方从未明写「`copyPixelBuffer` 不得阻塞」。本机 3.47.1 头文件里也没有「`textureFrameAvailable` 必须在平台线程调用」这句(上游新版有，引擎有 DCHECK)。
5. 安卓侧「原生渲染器从自己的线程往 `SurfaceProducer` 的 Surface 画」:官方文件没有明说，只能从插件把 Surface 交给 ExoPlayer、CameraX 推知。鸿蒙 `OHNativeWindow` 能否接 Dawn 的 Vulkan 后端。
6. PR #100 建树器在**手机上**的耗时和峰值内存(`DEVIATIONS.md:248` 明写没测过);手机建出的树与 Mac 建出的逐节点相同。
7. 台架的构建和装机流程(目录里没有脚本，只在会话记忆里);台架能否用 `--profile` 构建通过(`ios/Podfile:160` 注释说台架是 debug)。
8. arloopbench 的 post_install 另起一行 `OTHER_LDFLAGS[sdk=iphoneos*]`(`ios/Podfile:173-182`),是否会覆盖 pod 自带的同名行。
9. 正交投影下 LOD 选择的行为(库里没实现，上游也没实现)。
10. A2 的前提：8 月 7 日 .a 能否逐位重建。已查明做不到逐位：配方和中间产物都在，但编译配置已变。
11. **顺带发现，不在本方案范围**:产品 `lib/aether_ffi.dart:109` 用 `DynamicLibrary.process()` 查 `aether_version_string`,而 168 release 包的导出白名单(`ios/Podfile:242`、`Runner.xcodeproj/project.pbxproj:700-705`)只导出 5 个 XRSLAM 符号，所以这个查找在 168 里失败。实际影响未验证，只报告，不改。
