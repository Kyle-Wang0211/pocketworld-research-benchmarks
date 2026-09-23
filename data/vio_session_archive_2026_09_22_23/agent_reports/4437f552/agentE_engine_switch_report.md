# 构建层引擎臂开关 `PW_XRSLAM_ENGINE` —— 交付报告

日期 2026-09-22 · 仓 `~/Developer/pocketworld` · 分支 `feat/engine-arm-switch`(已推 origin)
commit **`ebf92de`**(父 `bc71409` = 别人那条 pbxproj 修复的 cherry-pick,父父 `f0b3a40`)

---

## 0. 一句话

产品工程现在能**按一个构建开关**链到可复现的 `gpufenothread` 引擎;
**默认构建与加这段之前的产物逐字节相同**(`cmp -l` 差异 0 字节,LC_UUID 也相同);
换臂**不可能静默沿用旧臂** —— 三道闸,其中一道是在**产物二进制**里核指纹。
🔴 血统仍 `research_only`,本次只解决「能不能按开关链上」,不解决质量。

---

## 1. 开关用法

```sh
# 默认(不设环境变量)= 出货 generic,和以前一模一样
flutter build ios --release --no-codesign

# 切到研究臂
ios/scripts/select_xrslam_engine.sh gpufenothread -- flutter build ios --release --no-codesign

# 切回默认
ios/scripts/select_xrslam_engine.sh generic -- flutter build ios --release --no-codesign
```

`PW_XRSLAM_ENGINE` 取值:`generic`(默认)/ `gpufenothread`。写错名字 `pod install` 直接 raise。

**为什么要那个包装脚本**:`ios/Podfile` 只在 `pod install` 跑的时候被求值,而 flutter 只在
Podfile 比 Podfile.lock 新时才跑 `pod install`。光 `export PW_XRSLAM_ENGINE=…` 不动 Podfile,
`pod install` 不跑 ⇒ xcconfig 里还是上一条臂。脚本就干一件事:`touch ios/Podfile` 把那步逼出来。
**绕过脚本也不会跑错臂**,会构建失败(见 §3 负对照)。

Release 构建还需要三个既有的环境变量(不是我加的,原来就没文档):
```sh
PW_PRODUCT_SOURCE_MANIFEST_SHA256=$(sh tool/product_source_manifest.sh)
PW_DIAGNOSTIC_BUILD_ID=<短标签>
PW_VIO_SHADOW_MODE=off   # on|off
```

---

## 2. 交付物落位

| 东西 | 路径(仓内) |
|---|---|
| 引擎归档 | `vendor/xrslam/libs/ios-arm64/libxrslam_gpufenothread_b9b14814.a` |
| 收据(全文) | `vendor/xrslam/libs/ios-arm64/libxrslam_gpufenothread_b9b14814.receipt.json` |
| 符号表 | `vendor/xrslam/libs/ios-arm64/libxrslam_gpufenothread_b9b14814.a.syms.txt` |
| **伴随库(必需)** | `vendor/xrslam/libs/ios-arm64/libpw_gpu_frontend_ios_ad0a4abe.a` |
| 开关(构建层) | `ios/Podfile` 的 `post_install` 段 |
| 切换脚本 | `ios/scripts/select_xrslam_engine.sh`(新) |
| 运行期身份 | `ios/scripts/stamp_runtime_identity.sh`(改) |

- 引擎 sha256 `b9b14814349eb945287b06ac6f5732e9c0a939e572ed46a073e597d59ea54cd2`(与
  `~/Developer/viobench-build/engine/libxrslam_gpufenothread_8a1cc12.a` **同一个文件**,拷进来前后 sha 核过)
- 伴随库 sha256 `ad0a4abe0e7ea7678780ec4a450ec91d6dc404ab1b33a44a265638437caf253d`
- 源码 `github.com/Kyle-Wang0211/xrslam` @ `build/gpufe-nothread-20260922` = `8a1cc1213af541dc6a1f4e1b89e0ff3629205c91`
  (`git ls-remote mine` 现场核过:refs/heads/build/gpufe-nothread-20260922 就是这个 sha)
- 配方 `~/Developer/viobench-build/gpufe/build_gpufe_nothread.sh`
- 🔴 **出货 `.a` 一个字节没动**:`libxrslam_generic_4beb1a9.a` 与
  `libxrslam_gpufenothread_4beb1a9.a` 都没被覆盖、没被重命名,只是新增了文件。

收据里记了:源码 commit / fork URL / cmake 开关全列 / 工具链(cmake 4.2.3、ninja 1.13.2、
Apple clang 17.0.0、Xcode 26.2、iPhoneOS SDK 26.2、eigen 3.3.7、OpenCV 4.0.1、ceres `e809cf0c`)/
`nm -g --defined-only` 的 17 个导出 API(出货 generic 那 5 个的**严格超集,一个不缺**)/
可复现性与「构建目录路径敏感」那条注意 / **selfcheck 未复跑**(见 §6)。

---

## 3. 换臂为什么不可能静默沿用(三道闸)

1. **Podfile 的幂等判据换掉了。** 原来是 `next if contents.include?('libxrslam_generic_4beb1a9.a')`
   —— 换臂时 xcconfig 里旧臂原样留着,一声不吭(memory 09-20 教训)。
   改成:**先剥掉上一轮我们自己追加的那一段,再重建**。剥的是以
   `-force_load "$(PODS_ROOT)/../../vendor/xrslam/libs/ios-arm64/libxrslam_` 开头到行尾的部分,
   碰不到 `aether3d_ffi` 写在同一行前半段的东西;在新装的 xcconfig 上剥是空操作
   ⇒ 默认档输出与改动前**逐字节相同**。
2. **请求 vs 实际对账。** Podfile 把结果写成构建设置
   `PW_XRSLAM_LINKED_ENGINE` / `_SHA16` / `_LIB` / `_FINGERPRINT`,
   `stamp_runtime_identity.sh` 在**所有 configuration** 下与进程环境里的
   `PW_XRSLAM_ENGINE` 对账,对不上 `exit 70`。
3. **二进制指纹。** Release 下再在产物 Runner 里核:本臂的指纹字符串**在场**、
   另一条臂的**不在场**,否则 `exit 71`。指纹是两条臂各自的 OpenCV 构建目录绝对路径
   (`CV_Assert` 的 `__FILE__` 烤进 `__TEXT,__cstring`),别处造不出来:
   - generic:`/private/tmp/opencv-official-c9ad577-b49/…/mat.inl.hpp`
   - gpufenothread:`/private/tmp/claude-501/…/scratchpad/build-run1/_deps/depends-opencv-build/…/mat.inl.hpp`
   旁证判据:`nm Runner | grep GpuImage`,generic 0 / 本臂 31。

**负对照实测**(只 `export PW_XRSLAM_ENGINE=gpufenothread`,不动 Podfile):
```
Error (Xcode): PW_XRSLAM_ENGINE=gpufenothread 但 xcconfig 里链的是 generic;
               换臂后必须重跑 pod install(ios/scripts/select_xrslam_engine.sh)
```
构建**失败**,不是跑成旧臂。

---

## 4. 三次构建的证据

判据取的是**同一时刻背靠背**的对照(理由见末尾那条)。基线 = 本分支父提交 `bc71409`,
即「只带 pbxproj 修复、没有引擎开关那个 commit」。全部用同一个
`PW_DIAGNOSTIC_BUILD_ID=engineswitch-20260922`、同一个 worktree。

### (a) 默认构建不变

| | Runner sha256 | 大小 |
|---|---|---|
| 基线(bc71409,默认) | `b3eb7871b72b7342b421e7a0369b0e668c051b7b659621c08c25f6dac22edeca` | 83061888 |
| **改动后默认** | `b3eb7871b72b7342…` **相同** | 83061888 |

第二对(换臂再换回来之后,同一环境):

| | Runner sha256 |
|---|---|
| 换回默认(build D) | `dc05ed2da65574a5f6dcb12ced5a0b4d5662d2921591235daceaafc2eeb41a4f` |
| 同环境重建基线(build A2) | `dc05ed2d…` — `cmp -l` 差异 **0 字节**,LC_UUID 同为 `C13C8348-0B22-3CE9-A5C7-9EDEA0A7B0F8` |
| 再跑一次改动后默认(build B2) | `dc05ed2d…` — `cmp -l` 差异 **0 字节** |

链接标志层面:默认档 `OTHER_LDFLAGS[sdk=iphoneos*]` **整行 sha 与基线逐字节相同**
(`9dd442a5395e13f2c78b0226b53df6f53282b7957e2afba1d76446fdbbc62d92`);
xcconfig 的唯一差异是 4 行纯信息性构建设置(`PW_XRSLAM_LINKED_ENGINE*`),不进链接。

🔴 **要说清的一件事**:两对之间,基线自己从 `b3eb7871` 漂到 `dc05ed2d`。
这个漂移在**不带引擎 commit 的纯基线上同样出现**(`pod install` 的插件清单 churn —— 
`image_picker_ios` 在 Podfile.lock 里进进出出,会改 `GeneratedPluginRegistrant`),
**与引擎开关无关**。所以我没有跨时刻比 sha,而是每次都做同一时刻的背靠背对照,
两对都得到「逐字节相同」。

### (b) `PW_XRSLAM_ENGINE=gpufenothread`

```
Runner sha256  b98d5e196b0a1ea3b63965ad18817ca3249ab59bda39c4a65a26d55f2740da27  (83294520)
xcconfig       PW_XRSLAM_LINKED_ENGINE = gpufenothread
               PW_XRSLAM_LINKED_ENGINE_SHA16 = b9b14814349eb945
               PW_XRSLAM_LINKED_ENGINE_LIB = libxrslam_gpufenothread_b9b14814.a
指纹命中        1   (…/scratchpad/build-run1/_deps/depends-opencv-build/…)
另一条臂指纹     0   (opencv-official-c9ad577-b49 —— 互斥成立)
五个生产符号     全在(t _XRSLAMCreate / Destroy / GetResult / PushSensorData / RunOneFrame)
GpuImage 符号   31
pw::gpufe 符号  81
wgpuDevice/Queue 39   ⇒ Dawn 已链
Info.plist      PWXrslamEngineArm=gpufenothread / EngineSHA16=b9b14814349eb945 /
                EnginePedigree=research_only / GpuFrontendLinked=true /
                AlgorithmBranch=gpufe_nothread /
                PWXrslamSHA256=b9b14814349eb945287b06ac6f5732e9c0a939e572ed46a073e597d59ea54cd2
```

### (c) 切回默认,痕迹消失

```
指纹命中 0 / GpuImage 0 / pw::gpufe 0
五个生产符号恢复为 T(全局)
Info.plist 回到 EngineArm=generic / EnginePedigree=shipping /
           PWXrslamSHA256=fdc75c99358014d9485bea36667547825465a85562847548d02a582da38c8011
Runner 二进制与同环境的纯基线 cmp 差异 0 字节
```

全部原始日志与证据落在
`/private/tmp/claude-501/…/scratchpad/engine_switch/`(`build*.log`、`evidence_build*.txt`、
`ldflags_segment_{generic,gpufenothread}.txt`、`xcconfigA_baseline.txt`)。

---

## 5. 路上发现/修掉的两件事

### (a) HEAD 的 iOS 构建本来就是坏的(不是我引入的)
`f0b3a40` 上 `ios/Runner/PwCameraSlot.swift` 引用 `PwXrslamLive`,但
`ios/Runner/PwXrslamLive.swift` 虽然入了库却**从来没进过 `project.pbxproj`**:
```
Swift Compiler Error (Xcode): Cannot find 'PwXrslamLive' in scope
ios/Runner/PwCameraSlot.swift:126:8 / :273:8
```
我一开始自己补了一份;协调者指出另一位 agent 已经在 `4433da1` 修了同一处,
于是我**丢掉自己那个 commit、cherry-pick 了 `4433da1`**(成为本分支的 `bc71409`),
两边 pbxproj 内容完全一致 ⇒ 合并时不会冲突。
**所以本报告里的「基线」是「f0b3a40 + 4433da1」,不是干净的 f0b3a40** —— 干净的 f0b3a40 编不过。
我自己的引擎 commit(`ebf92de`)**一行 pbxproj 都没动**,`-Wl,-exported_symbol` 白名单没碰。

### (b) `ld: 24 duplicate symbols`
第一版把伴随库也 `-force_load` 了,实测 24 个重复符号**全是**
`aether::tools::DawnKernelHarness::*` —— `aether3d_ffi` 那条 `-force_load` 已经带了同名实现。
伴随库只有两个成员(`pw_gpu_frontend.o` / `dawn_kernel_harness.o`),所以改成
**按普通归档挂着**:链接器只为引擎那个未定义符号拉 `pw_gpu_frontend.o`,
`dawn_kernel_harness.o` 因为符号已定义而不被拉,两边共用 aether 那份 harness。
代价已记进收据:harness 实现取自 `aether3d_ffi` 的编译版本,不是编这个前端库时的那份。

---

## 6. 遗留 / 没做到的

1. 🔴 **血统仍 `research_only`。** 收据自标 `product_selected: false`。
   本次交付的是**构建层接线**,不是质量结论。「没全面持平/超越 ARKit 之前绝不上生产」不因此松动。
2. 🔴 **真机 selfcheck 未复跑。** GPU 前端那份数值自检(`sqrt 4804/16384`、
   未保护乘加 `4655/16384` 与 CPU 差最后一位)要真机跑 `gpu_image.cpp` 的 init 痕迹。
   伴随库与出货 `gpufenothread` 归档用的是**同一个文件**(sha 相同),所以结论可沿用,
   但**没有重新验证**。本次不碰 iPhone、不开摄像头。
3. 🔴 **Dawn 口径与台架不同。** 产品工程复用 `aether3d_ffi` 已链的 **Debug** Dawn;
   arloopbench 台架链的是 Release Dawn(实测快约 10%)。
   ⇒ **台架上那些 fps 数不能直接搬到产品工程上**,要在产品工程里重测。
4. 🔴 **本臂下五个生产符号是 `t` 不是 `T`。** 归档用 `ENABLE_VISIBILITY=0`(`-fvisibility=hidden`)
   编,`-Wl,-exported_symbol` 提升不了隐藏符号。生产的原生 transport
   (`vendor/xrslam/transport/PwXrslamTransportCore.cpp`)是静态直调,**不受影响**;
   但 Dart 侧 `DynamicLibrary.process().lookup('XRSLAMCreate')`
   (`lib/vio/ffi/xrslam_bindings.dart`,今天零生产调用者)在本臂下会拿不到。要用得先解决可见性。
5. **未跑**:真机直播吞吐、EuRoC/回放 ATE。链接级证据齐全,运行级证据为零。
6. `ios/Podfile.lock` 里夹带了一条与我无关的环境漂移(`image_picker_ios` 出现)。
   它在主工作树里本来就是未提交的改动,我为了 `PODFILE CHECKSUM` 对得上把 Podfile.lock 一起提了;
   `pubspec.lock` 的 `thermion_dart` 漂移我 **revert 掉了**,没进 commit。

---

## 附:两条臂的链接标志(实测导出)

**generic(默认,与改动前逐字节相同)**
```
-force_load "$(PODS_ROOT)/../../vendor/xrslam/libs/ios-arm64/libxrslam_generic_4beb1a9.a"
"…/libceres_official_1_14.a" "…/libopencv_generic_4_0_1.a"
-Wl,-u,_XRSLAM{Create,Destroy,RunOneFrame,PushSensorData,GetResult}
-Wl,-exported_symbol,_XRSLAM{Create,Destroy,RunOneFrame,PushSensorData,GetResult}
```
**gpufenothread**
```
…同上,但归档换成 libxrslam_gpufenothread_b9b14814.a,并在末尾追加:
"…/libpw_gpu_frontend_ios_ad0a4abe.a" -framework Metal -framework IOSurface -framework QuartzCore
（注意:伴随库**没有** -force_load,理由见 §5(b)）
```
