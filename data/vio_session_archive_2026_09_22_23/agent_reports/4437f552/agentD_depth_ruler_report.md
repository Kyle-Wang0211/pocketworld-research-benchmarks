# 研发期米制尺子(LiDAR 深度)—— 子 agent D 交付报告

**日期** 2026-09-22 · **仓** `pocketworld-research-benchmarks`
**worktree** `~/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829`
**分支** `research/basalt-vio-phone-bench-20260829` · **commit `76b8d47`**(已 push 到 origin 同分支)

---

## 🔴 口径(用户 2026-09-22 原话)

**LiDAR 只作研发期量尺,永远不进产品管线、不进提案。**
产品是纯单目 + IMU,这条不变。这次加的深度录制、深度尺子,只用来**校准我们手里的仪器**,
不是产品输入、不是产品兜底、也不是对机型的要求。

这句话不是只写在本报告里 —— 它写在**每一个新增定义点**上:
`DeviceRecordingFileRole.depthStream` 的文档注释、`DeviceRecordingWriter` 的 depth 段、
`appendDepth()`、ARKit 臂开 `.sceneDepth` 的那段、`depth_ruler.py` 文件头、
`synth_depth_verify.py` 文件头,以及两个脚本的 **stdout 第一行**和 JSON 报告的
`bench_only_notice` 字段。想把它读成产品方案,得先删掉七处白纸黑字。

---

## 一、改动清单

### A. 录制器(Swift,`tools/ios_basalt_vio_bench/`)

| 文件 | 改了什么 |
|---|---|
| `Replay/DeviceRecordingTypes.swift` | 新增 3 个 `DeviceRecordingFileRole`:`depth_stream` / `depth_confidence_stream` / `depth_index`;manifest 新增 7 个字段;新增路径常量 `depth.bin` / `depth_conf.bin` / `depth.pwvi` 与 `expectedDepthWidth/Height = 256/192`;新增错误 `depthGeometryChanged` |
| `Replay/DeviceRecordingWriter.swift` | 新增 `appendDepth(depthMap:confidenceMap:timestampNanoseconds:source:)`、`openDepthHandlesIfNeeded()`、`copyTightly(_:bytesPerPixel:)`;`projectedByteCount` 加 `includingDepth:`;`finish()` 落三个文件 + 填 manifest |
| `Replay/DeviceRecordingLoader.swift` | 两条深度流并入 `payloadRoles`(不在 load 时整份重哈希);顺手把 `rejectUnsafePath` 提到对**所有**文件都跑(原来 payload 角色被跳过) |
| `BasaltVIOBench/ARKitReference/ARKitReferenceSession.swift` | 配置里按需 `frameSemantics.insert(.sceneDepth)`,**先查 `supportsFrameSemantics`**;`didUpdate` 里 `frame.sceneDepth` 非 nil 时 `appendDepth`,与 `recordIntrinsics` / `appendFrame` 同一帧同一 `frame.timestamp`;receipt 新增 `sceneDepthSupported` / `sceneDepthRequested` |
| `BasaltVIOBench/Receipts/RunDiagnostics.swift` | `effective_configuration` 打三个键:`scene_depth_supported` / `scene_depth_requested` / `scene_depth_role`(值就是 "bench_only_metric_ruler_not_a_product_input") |
| `BasaltVIOBench/BenchmarkCoordinator.swift` | `record` 臂的空间预检 `includingDepth: true` |
| `BasaltVIOBench/BenchViewModel.swift` | 屏幕上那行「需要 X GiB」跟着含深度,与拒绝用的数一致 |
| `BasaltVIOBench/BenchSelfTest.swift` | `preflight.json` 的 300 s 投影与 `max_recordable_seconds` 含深度 |
| `BasaltVIOBenchTests/ReplayTests/DeviceRecordingTests.swift` | +3 个测试(见第四节) |

**没碰**:`charuco_scale_arbiter.py`、`synth_verify.py`、`_sweep*`、以及
`tools/ios_basalt_vio_bench` 里任何与录制无关的文件。`project.yml` 不用改也不用
`xcodegen generate` —— 它按**目录**收 sources(`Replay` / `BasaltVIOBench` /
`BasaltVIOBenchTests`),而本次没有新增 Swift 文件,全是改存量文件。

### B. 仲裁工具(Python,`tools/scale_arbiter/`)

| 文件 | 作用 |
|---|---|
| `depth_ruler.py`(新,~460 行) | 深度尺子本体。复用同目录 `charuco_scale_arbiter.py` 的 `load_recording()` / `load_intrinsics()` / `load_tum()` / `quat_to_rmat()` |
| `synth_depth_verify.py`(新,~330 行) | 合成验证。**整个场景生成器 import 自 agent 3 的 `synth_verify.py`**(`make_trajectory` / `render` / `K_at` / `write_tum` / `rmat_to_quat` + 全部常量),一行没改它;本文件只补一张解析深度图 |

---

## 二、磁盘布局与 manifest 字段

### 三个文件(与 `frames.bin` / `frames.pwvi` **同一种布局**:append-only 流 + JSONL 索引)

```
depth.bin       float32 小端,米,行优先 w×h,逐帧背靠背
depth_conf.bin  uint8,ARConfidenceLevel(0 low / 1 medium / 2 high)
depth.pwvi      JSONL,每帧一行:
                {"frame":N,"offset":X,"len":L,"t_ns":T,"w":256,"h":192,
                 "conf_offset":CX,"conf_len":CL}
```

`conf_offset` / `conf_len` 是任务书那 6 个键之外**加的**两个:任务书只写了
`{frame, offset, len, t_ns, w, h}`,那样置信度流的偏移只能由读者按帧号推,
一旦中间丢一帧就整体错位。写进索引让它自洽。没有置信度时 `conf_offset = -1`、
`conf_len = 0`,读者据此拒绝(见下)。

写序 **流 → 置信度 → 索引行**,每步 `synchronize()`,与 `frames.bin` 一致:
任何时刻被打断,索引都不会指向流里还没提交的字节。

### manifest 新字段(`recording_manifest.json`)

| 键 | 类型 | 含义 |
|---|---|---|
| `depth_present` | bool | 这次录制到底有没有深度 |
| `depth_width` / `depth_height` | int | 实测的,不是常量 |
| `depth_frame_count` | int | **真正写进流的**帧数 |
| `depth_source` | string | 恒为 `"ARFrame.sceneDepth"`(合成录制写别的值,一眼可辨) |
| `depth_confidence_present` | bool | `ARDepthData.confidenceMap` 在 SDK 头里是 `nullable`,真可能没有 |
| `depth_dropped` | int | 没能留下的深度帧 |

三个设计决定,都写在代码注释里:

1. **全部是 Optional**。Swift 合成的 `init(from:)` **不用**属性默认值,它调
   `decode(_:forKey:)`,缺键就抛。非 Optional 会让**今天之前的所有录制**解不开。
   `nil` = 「这个录制器还不知道有深度这回事」,与 `depth_present == false`
   (「知道,但设备没有」)是两件事。
2. **`depth_dropped` 不并进 `loss_count`**。相机帧丢了 ⇒ 录制作废(每条臂都在这些帧上打分);
   深度丢了 ⇒ 少几个测量点而已。一把 bench-only 的尺子**不能有权作废一次拍不回来的录制**。
   `finish()` 里深度那一段任何错误都不向外抛。
3. **句柄第一帧才开**。没有 LiDAR 的机器不会留下三个 0 字节文件,
   `depth_present: false` 是关于世界的陈述,不是关于三个空文件的陈述。

### SHA256SUMS
自动覆盖,不用改代码:`BenchmarkArtifactFinalizer.finalize()` 是**枚举目录**逐个流式哈希的
(`BenchmarkArtifactFinalizer.swift:65-75`),新文件落在同一目录里自然被收。
另外 manifest 的 `files[]` 里三个文件各带自己的 `sha256`,其中两条流的摘要是**边写边累加**的
(和 `frames.bin` 一样),sealing 不会去重读几百 MB。

### 空间预检
`projectedByteCount(seconds:format:includingDepth:)`:
`256 × 192 × (4 + 1) = 245,760 B/帧`;60 fps × 30 s = 1800 帧 = **422 MiB**(≈442 MB,与任务书的 ≈440 MB 一致)。
`record` 臂**无条件**按有深度算 —— 支持与否要 `session.run` 之后才知道,而
「算多了顶多多要点余量,算少了是录到一半把卷宗撑爆」。

---

## 三、Apple 文档引用(逐字,带 URL)

| 出处 | 原话 |
|---|---|
| https://developer.apple.com/documentation/arkit/ardepthdata (Overview) | "Every pixel in the `depthMap` maps to a region of the visible scene (`capturedImage`), where the pixel value defines that region's distance from the plane of the camera in meters." |
| https://developer.apple.com/documentation/arkit/arframe/scenedepth (Discussion) | "This property is `nil` by default. Add the `sceneDepth` frame semantic to your configuration's `frameSemantics` to instruct the framework to populate this value with `ARDepthData` captured by the LiDAR scanner." |
| 同上 | "Call `supportsFrameSemantics(_:)` on your app's configuration to support scene depth on select devices and configurations." |
| SDK 头 `iPhoneOS26.2.sdk/.../ARKit.framework/Headers/ARDepthData.h` | `depthMap`: "A pixel buffer that contains per-pixel depth data (in meters).";`ARConfidenceLevel` = Low / Medium / High(即 0 / 1 / 2) |
| SDK 头 `.../ARConfiguration.h`(`frameSemantics`) | "An exception is thrown if the option is not supported. Defaults to `ARFrameSemanticNone`." |
| SDK 头 `.../ARConfiguration.h`(`supportsFrameSemantics:`) | "Semantic frame understanding is not supported on all devices." |

**从引文能直接得到的两条**:
① 深度是**相机平面的 z 距离**("distance from the **plane** of the camera"),不是到光心的径向距离
⇒ 可以直接和三角化点的 Z 相除,不需要先换算;
② 深度图每个像素覆盖 `capturedImage` 的一个区域、整张覆盖同一个可见场景 ⇒ 两者同 FOV。

**🔴 一条是我们的推论,不是引文**:像素映射式
`u_d = (u_c + 0.5)·W_d/W_c − 0.5`(像素面积中心对齐)。
我**没有**找到一句 Apple 文档明写「同 FOV」或明写这个缩放公式。它是从上面那句话 + 分辨率比
推出来的,代码和文件头都按「推论」标注,没有伪装成引文。
(顺带:`synth_depth_verify` 的闸①a 把这个公式**实测**到了 0.0437 µm —— 推论是对的,
但「对」和「Apple 说过」是两回事。)

`smoothedSceneDepth` **不用**:它是 ARKit 自己的时域滤波估计,尺子不能是另一个估计器的输出
(同一条理由,`ARKitReferenceSession` 早就拒绝了 `CMDeviceMotion`)。

---

## 四、编译 / 测试输出

解释器:Swift 侧 Xcode(iPhoneOS 26.2 SDK);Python 侧 **`/usr/bin/python3`**
(`cv2 4.13.0` + `numpy 2.0.2`;`/opt/homebrew/bin/python3` 是 3.14,**没有 numpy**,会直接报错)。

```
$ xcodebuild -project VIOReplacementBench.xcodeproj -scheme VIOReplacementBench \
    -configuration Debug -destination 'generic/platform=iOS' \
    -derivedDataPath <scratchpad>/dd-debug -allowProvisioningUpdates build-for-testing
** TEST BUILD SUCCEEDED **        error: 0 处

$ xcodebuild ... -configuration Release ... -allowProvisioningUpdates build
** BUILD SUCCEEDED **             error: 0 处
```

- 测试目标**只能 Debug 编**(Release 的 `ENABLE_TESTABILITY` 关着,`@testable import` 失败)—— 这是既有状况,`d5ab9e9` 的 commit message 里已经记过,与本次改动无关。
- Release 按 `scripts/pw_build_arms.sh:8` 的配方(`-destination 'generic/platform=iOS' -allowProvisioningUpdates`,**没加** `CODE_SIGNING_ALLOWED=NO`)。产物已签名:`Identifier=com.kyle.viobench`,`Mach-O thin (arm64)`。
- 新增的唯一告警是 `init(contentsOf:)` iOS 18 弃用 —— 与文件里已有的另外两处同款,不是本次引入的新问题。
- 产物自证:`nm` 在 app 二进制里找到 `appendDepth` 符号 6 处,字符串表里有 `ARFrame.sceneDepth`。
- 🔴 **测试没有真正跑过**。本台架的 XCTest 目标在这台机器上从来没跑起来过(2026-09-16 的判决:模拟器缺 OpenCV 真机切片 / 真机测试宿主 code 74 早退),而本次不碰 iPhone。所以「测试通过」这句我不说,只能说**测试代码编译通过**。

### 新增的三个测试(编过,未执行)
1. `testDepthStreamsAndIndexAgree` —— 三个文件都在;字节数 = 3×256×192×4 / 3×256×192(**紧致打包,没有行 padding**);逐行索引的 `frame`/`offset`/`len`/`conf_offset`/`conf_len`/`w`/`h`/`t_ns` 全对;manifest 里三条 `files[]` 的 `byte_count` 与 `sha256` 与磁盘逐位相符;`depth_dropped == 0` 且 `loss_count == 0`;第一个像素值 1.0。
2. `testRecordingWithoutDepthDeclaresItAbsent` —— `depth_present == false`,宽高/来源/置信度全 `nil`,三个文件**不存在**,`files[]` 里没有三个角色,且录制**照样能 load**。
3. `testProjectedByteCountIncludesTheDepthStreams` —— `depthBytesPerFrame == 245,760`,30 s 的差值 = `1800 × 245,760`,不含深度那条仍等于 `1920×1440×60×30`(即老的 `testProjectedByteCountMatchesTheContract` 不受影响)。

---

## 五、合成验证数字(**不拍摄、不开摄像头、不碰 iPhone**)

```
$ /usr/bin/python3 tools/scale_arbiter/synth_depth_verify.py --work <scratchpad>/synthdepth --keep
exit = 0        ✅ 深度尺子合成验证通过
```

场景:agent 3 的 ChArUco 合成器原封不动(5×7 板 40 mm 方格、1920×1440、ARKit 内参、
超采样 3×、像素噪声 σ=2、80 帧 @30 fps、扫视 ±35° / 距离 0.45–0.80 m),
外加按**同一套几何**解析出的 256×192 深度(射线-平面求交)+ 置信度
(落在板矩形内 = high 2,板外 = low 0,对应真机上「这块区域 LiDAR 没有可信读数」)。
轨迹先施一个**随机刚体变换**(随机旋转 + 平移),用来证明世界系整体换基对结果无影响。

| 闸 | 结果 |
|---|---|
| ①a 深度几何(**不量化**) | 解析深度 vs `projectPoints` 给出的真实相机系 Z,**最大差 0.0437 µm** ≤ 1 µm ⇒ 射线-平面求交与「按分辨率比缩内参」是精确的,且与 `depth_ruler.sample_depth()` 的公式**互逆** |
| ①b 最近邻取值(尺子真实走的路) | 最大差 **1.2903 mm** ≤ 5 mm。**这不是 bug**,是 256×192 的量化:一个深度像素横跨 7.5 个图像像素,斜看平面时这段距离内深度本来就在变。真机上同样存在 ⇒ 尺子的输出是中位数,不是单点值 |
| ② **轨迹 × 1.10** | 恢复 **k = 1.100178**,偏差 **+0.0162%**(容差 ±1%)。`s = 0.908944`,IQR 3.02e-4,有效帧对 **20/20** |
| ③ 真值轨迹(阴性对照) | 恢复 **k = 1.000162**,偏差 **+0.0162%**。`s = 0.999838`,IQR 3.32e-4,20/20 |
| ④ 阴性:无深度的旧录制 `run-6e2d4b99-896b-4372-ae47-ac0b4679cf18` | **干净拒绝,exit 1**,理由点名缺 `depth.pwvi` 并给出两条出路(换带深度的录制 / 改用印出来的板) |
| ⑤ 阴性:深度全 low 置信度 | **拒绝,exit 1**,理由点名 `--min-confidence` |
| ⑥ 阴性:`--camera-axes` 喂错 | **拒绝,exit 1**(cheirality 全灭)。加这一条是因为轴系搞错**不会报错,只会让三角化全落到相机背后** —— 正是「偷偷偏一点」那类 bug |

其它实测数:每对帧中位 533 个匹配 → 过完四道闸剩 **453 个有效点**;三角化夹角中位 **15.2°**;
基线中位 0.23 轨迹单位;LiDAR 置信度直方图 low/med/high = **13 / 0 / 10831**。

**两个口径互为旁证**:monodepth2 逐字的「中位数之比」k=1.100178,
任务书字面的「逐点比值中位数」k=1.100050,两者差 **−0.0116%**。

**换 ORB**(`--detector orb`):k = **1.099864**(偏差 −0.012%),IQR 9.7e-4(比 SIFT 宽 3 倍),20/20 仍全过。

### 抄自哪里(零自研)
| 环节 | 出处 |
|---|---|
| 特征 + 匹配 | SIFT/ORB + `BFMatcher.knnMatch(k=2)` + Lowe 比值检验 0.8 —— Lowe, IJCV 60(2):91-110, 2004 §7.1;OpenCV 官方教程 https://docs.opencv.org/4.x/dc/dc3/tutorial_py_matcher.html(SIFT 自 OpenCV 4.4 起在主仓 features2d,Apache-2.0,不需要 contrib) |
| 三角化 | `cv2.triangulatePoints`(DLT,Hartley & Zisserman §12.2) https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html — **位姿不估**,直接用被测轨迹给的相对位姿,否则会把尺度自由度重新引进来 |
| 尺度对齐 | monodepth2 `evaluate_depth.py` **逐字**:L207 `ratio = np.median(gt_depth) / np.median(pred_depth)`、L218 `med = np.median(ratios)` https://github.com/nianticlabs/monodepth2/blob/master/evaluate_depth.py(已 curl 下来核过行号与原文);更早见 Zhou et al. CVPR2017 SfMLearner https://arxiv.org/abs/1704.07813;「单目深度只能定到未知尺度、评测前要对齐」的源头是 Eigen/Puhrsch/Fergus NIPS2014 §3.2 https://arxiv.org/abs/1406.2283 |
| 录制读取 | 复用 `charuco_scale_arbiter.py`(它又复用 `pwvi_to_euroc.py`);内参**按时间戳**最近邻配对,不按下标 |

---

## 六、怎么接 `tools/scale_accept/accept_scale.py`

`accept_scale.py` 吃两条 `.tum`,判的是「我们的轨迹 vs ARKit 参照」的**相对**尺度 —— 它不知道米。
深度尺子给的是**每条轨迹各自对米的 s**。接法:

```bash
# 1) 各算一次(同一份带深度的录制)
/usr/bin/python3 tools/scale_arbiter/depth_ruler.py \
    --recording ~/Developer/viobench-recordings/run-XXXX \
    --traj est=<run>/poses.tum --traj ref=<run>/arkit_poses.tum \
    --camera-axes arkit --ref-y-up --out /tmp/dr
# 工具会直接打印 s_est / s_ref

# 2) 与 accept_scale 对照
/usr/bin/python3 tools/scale_accept/accept_scale.py \
    --pair phoneX <run>/poses.tum <run>/arkit_poses.tum --ref-y-up
```

* `s_est / s_ref` 应当 ≈ `accept_scale.py` 报的那个相对尺度 —— 这是对它的**米制核对**;
* 而 **`|1 − s_est|` 才是「对真实尺寸的偏差」**,也就是 ±5% 估算型容差真正要管的量。
  `accept_scale.py` 自己的文件头已经承认它做不到这件事(「真实尺寸的验收必须用外部尺子」)—— 这把尺子就是补那一格。
* `--ref-y-up` 语义与 `ate.py` 相同(声明世界系是 ARKit 的 y-up),但**对本工具数值无影响**:
  三角化只用相对位姿 `R_b^T R_a` / `R_b^T(p_a − p_b)`,世界系整体换基在里面约掉。收它只为写进 provenance。
  **真正会改数值的是 `--camera-axes`**(ARKit 相机本体系是 x右/y上/z后,OpenCV 是 x右/y下/z前)。

---

## 七、产物路径

| 东西 | 路径 |
|---|---|
| Release `.app`(**未装机**,等用户要录时再装) | `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad/artifacts/VIOReplacementBench-depth.app` |
| 合成验证 JSON 报告 | `<同上>/artifacts/synth_depth_ruler_report.json` |
| 合成验证完整 stdout | `<同上>/artifacts/synth_depth.log` |
| 本报告 | `<同上>/agentD_depth_ruler_report.md` |

DerivedData(Debug 241 MiB + Release)已建在 scratchpad 并**用完删掉**。
起跑时数据卷只剩 2.0–3.5 GiB,过程中一直在 100% 容量线上跑,现回到 4.0 GiB。

---

## 八、真机第一次录制要看什么(按顺序)

1. **`diagnostics.json` → `effective_configuration`**
   - `scene_depth_supported` 必须 `true`(不是 true 就说明这台机器没 LiDAR,后面都别看了);
   - `scene_depth_requested` 必须 `true`(是 false 而 supported 是 true ⇒ 配置那段没生效)。
2. **`preflight.json`** 起录**前**看:`max_recordable_seconds` 现在已含深度,若它比上次小了约 8%,说明预检生效了。
   若开录就被「存储空间不足」挡回来,是预期的 —— 30 s 现在要 **5.13 GiB(luma)+ 0.42 GiB(深度)+ 0.5 GiB 余量**。
3. **`recording_manifest.json`**
   - `depth_present: true`、`depth_width/height` = **256 / 192**(不是这个数就记下来,逐机型可能不同);
   - **`depth_frame_count` vs `frame_count`**:ARKit 文档说 sceneDepth 与 `capturedImage` 是**每帧**配的,所以两者应当接近。差得多 ⇒ 要么设备降频给深度,要么 `depth_dropped` 在涨;
   - **`depth_dropped` 必须是 0**。不是 0 就看 `peak_in_flight`:深度队列是 120 格、240 KiB/格,理论上不该满;
   - `loss_count` **不受深度影响**(设计如此),若它涨了那是相机侧的老问题。
4. **文件大小自检**:`depth.bin` 应当正好 `depth_frame_count × 256 × 192 × 4`,
   `depth_conf.bin` 正好 `× 256 × 192`。对不上就是索引/流不同步。
5. **置信度直方图**:跑一次 `depth_ruler.py` 看 `lidar_confidence_histogram_low_med_high`。
   真机室内近距离应当以 high 为主;若 high 极少(远景、强光、大片白墙),尺子会**拒绝给数**而不是给个坏数 —— 这是设计,不是故障。
6. **第一次拿 s 的读法**:`--camera-axes arkit`(ARKit 位姿)。
   对 `arkit_poses.tum` 自己跑一遍,得到的 `k` 就是「**ARKit 自己**比米制大多少」——
   这是本次交付最有价值的一个数:**它会第一次告诉我们 ARKit 那把尺子自己偏多少**,
   而我们过去所有的 2.60 cm / 4.13% 都是相对它测的。
7. 🔴 **别把 s 当真值**。LiDAR 自带误差(公开独立测试对 iPhone LiDAR 给到 ±4.6% 量级)、
   深度图 7.5× 下采样在物体边缘会混前景/背景、小视差下三角化本身病态。
   这把尺子的用处是**量级和排序**,不是标称精度;真要标称精度还得回到印出来的 ChArUco 板。

---

## 九、如实报告:没做的 / 做不了的

1. **测试没执行,只编过**。理由见第四节(XCTest 目标在这台机器上从来没跑起来过,且本次不碰设备)。
2. **零真机数据**。所有数字来自合成。真机上深度的时间戳与相机帧是否严格同帧、
   `depth_frame_count` 会不会显著少于 `frame_count`、`depth_dropped` 会不会涨 —— 都**未验证**。
3. **`--camera-axes arkit` 这条路径没有端到端验过**。合成数据是 OpenCV 约定,
   `arkit` 分支只验到了「喂错会被拒绝」(闸⑥),没验到「喂对会给出正确的 s」。
   第一次真机录制要专门核这一条。
4. **深度与相机帧的配对容差 20 ms 是拍的**,没有真机证据。若真机上深度是 30 Hz 而相机 60 Hz,
   这个值要重定(现在配不上的帧会被静默跳过,只反映在「可用帧」那行计数上)。
5. **`smoothedSceneDepth` 没试过**,按「不要另一个估计器的输出」直接排除了,没有实测对照。
6. **像素映射公式是推论不是 Apple 原文**(第三节已标)。合成上它精确到 0.0437 µm,
   但那验的是「我们的两段代码互逆」,不是「Apple 就是这么定义的」。
7. **`depth_present` 只反映「有没有写成」,不反映「设备支不支持」** —— 后者在
   `diagnostics.json` 的 `scene_depth_supported` 里,两处要一起读。
