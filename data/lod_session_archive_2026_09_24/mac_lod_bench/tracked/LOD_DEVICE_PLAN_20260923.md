# LOD 真机测量方案(B 线)—— 3,600 万 / 2.17 亿点能否在 A16 上稳定 30 fps、有没有丢细节

**日期**:2026-09-23 **状态**:方案定稿、台架已编好、数据已备好;**未装机、未启动任何 App**,等用户批准
**设备**:iPhone 14 Pro(A16,iPhone15,2,iOS 26.6.1,UDID `<device-coredevice-id>`)
**台架**:`~/Developer/pw_splat_ab_bench`(git,见 §9 的提交),bundle **`com.kyle.PWSplatAB`**(台架自己的,不是生产包)
**LOD 库**:Aether3D `feat/pointcloud-lod-core` @ `d89b74f34081904f2ece5b9bccca4c3384d4da28`,原样拷进 `third_party/aether_pointcloud_lod/`(`PROVENANCE.txt` 有逐文件 sha256)

> 本文件在看到任何真机数据**之前**写定。§5 的阈值、§6 的停止规则,事后不许改;要改就另起一版并写明原因。

---

## 1. 要回答的问题

1. **帧率**:用 PR #98 的 LOD(选择 + 流式 + 控制器),A16 上 36,232,793 点和 216,655,968 点两朵云,沿同一条相机轨迹,能不能**稳定 30 fps**。
2. **细节**:30 fps 下画面比「全细节参考图」丢了多少;拉近到一个最深层叶节点时,它的点是不是真的画在屏幕上。
3. **消融**:控制器驱动 `minimumNodePixelSize`(臂 C)对比 Potree 固定 150 px(臂 F)。

不回答:手机端建树(另一条线);Adreno/Mali/Maleoon(本轮只有一台 A16,跨端靠「代码无平台专属」,见 §8)。

## 2. 被测系统(什么是抄的,什么是接线)

| 部分 | 来源 | 本台架做了什么 |
|---|---|---|
| 选择 `selectVisible` | PR #98(Potree updateVisibility) | 原样调用,`cam.viewProj` 行主序 + WebGPU 裁剪空间 z∈[0,1],相机构造抄库自己的 `tests/pointcloud_lod/test_select.cpp` |
| 流式 `NodeLoader` / `NodeCache` | PR #98 | 原样调用;**同步**加载(库只提供同步 API),加载时间计入帧时间 |
| 控制器 `QualityController` | PR #98(Cesium ×1.02 / ÷1.02,D10) | 原样调用;输入 = **上一帧真实测得的壁钟耗时**(选择+加载+上传+编码+提交+等 GPU 完成) |
| 点渲染 | 台架 `bench_cloud.mm` 的 `kWgslCloud` | 顶点展开 quad、透视半径 `r = 1.5 × camDist / depth`、不透明 + 深度写;唯一改动:view-projection 换成**每节点 uniform** `VP × T(节点 origin)`(双精度相乘后再转 float,Potree 每节点 modelViewMatrix 的做法) |
| 接线(自己写的,只是管道) | `Sources/lod/pw_lod_bench.cpp` | 每节点一个 GPU buffer(首次画时建、超预算时按最久未画逐出)、每节点一次 draw、轨迹、A/B 排程、探针 |

- 点预算硬顶 **3,630,000** = (33.3 − 0.20) / 9.12 ms/百万点(A16 实测成本线,`cloud_run1_fit.json`)。
- `NodeCache` = 3 × 下限 = 3 × 15 B × 3.63M = **163,350,000 B**;GPU 侧按 16/15 同比例 = 174.2 MB。库的「缓存不足会静默少画节点」由每帧 `dropped = 选中节点数 − 返回节点数` 直接计数,必须恒为 0(§5.1 闸)。
- 离屏渲染 1179×2556 RGBA8 + Depth32Float,每帧提交后等 `OnSubmittedWorkDone`(与成本线同口径);**每帧按 33.3 ms 节拍补睡**(模拟 30 Hz 显示),睡眠不计入帧时间。

## 3. 相机轨迹(按帧号确定,不按时间 ⇒ 每条臂看到逐帧相同的位姿)

每块 900 帧(30 Hz 下 30 s)。**c / R 取「内容框」而不是根立方体**:每个节点的点数记到它的第 4 层祖先上,c = 这些祖先盒心按点数加权的逐轴中位数,R = 按点数加权的 90 分位(到 c 的距离 + 祖先盒半径)。只用 hierarchy,不读点,不影响选择。
(原因:216M 的根立方体被离群点撑大,R 22.9 vs 同场景 36M 的 16.2,按根立方体取景时 orbit/pan 几乎全对着空处,「保住细节」会平凡成立。内容框:36M c=(−0.036, 1.135, 3.438) R=4.90;216M c=(1.026, 1.045, 3.607) R=5.48。)
目标叶 = 最深层中点数最多的叶:36M `r61216727`(第 8 层,3,090 点);216M `r2563722301`(第 10 层,1,516 点),两者在同一个物体上。

| 帧区间 | 段 | 位姿 |
|---|---|---|
| 0–10% | hold_overview | eye = c + (0,0,2R),看 c |
| 10–30% | push_in | 对数距离 + smoothstep,从 2R 推到叶前 3 r_leaf(S2 的姿态) |
| 30–40% | hold_leaf | 停在叶前 |
| 40–48% | pull_out | 退到 0.6R |
| 48–73% | orbit | 绕 +y 转 360°,半径 0.6R |
| 73–78% | to_pan | 过渡 |
| 78–93% | pan | 在 z = c+0.35R 沿 +x 平移 1R,朝 −z |
| 93–100% | back_to_overview | 回总览 |

## 4. 指标

### 4.1 每帧记录(JSON 里逐帧数组)
壁钟总耗时(= 控制器输入)、GPU 时间戳、选择/加载/上传/渲染四段耗时、画出的点数/节点数、当前 `minimumNodePixelSize`、选中最深层级、本帧解码节点数/读字节数/上传节点数、`dropped`、`truncated`、`hitBudget`、目标叶是否被选中/画出。每 30 帧一次外壳探针:热状态(0–3)、`phys_footprint`、`os_proc_available_memory`。

### 4.2 画面(`mode=correct`,单独一次启动)
四个位姿(overview / leaf / orbit_mid / pan_mid)各渲染:
- **参考图**:px = 1、预算 2,000 万点(本身是否撞预算会记录);
- **抖动底噪**:参考图相机横移 0.25 px 再渲一次 —— 「肉眼看不出变化」的像素差上限;
- 固定 150 / 60 / 30 px;控制器在该位姿用**真机帧时间**跑 150 帧后的画面;
- 叶节点检查(leaf 位姿):被选中、被画出、「全画 − 去掉该叶」改变的像素数 > 0(**真的可见**)、只画该叶的覆盖像素;阴性对照:「去掉该叶」自比 = 0 像素、**忘记加回 origin** 的画面必须与参考不符。
- 每张图报 sha(FNV-64)、覆盖率、**平均饱和度**、**三通道标准差**、对参考的差异像素比例、全分辨率 PSNR、4×4 块平均后 PSNR。

## 5. 判定口径(预注册)

### 5.1 有效性闸(任一不过 ⇒ 本次运行作废,不下结论)
- `wgpu_errors` 为空;适配器不是 Null 后端;
- **阳性对照**:同一静态位姿、px=1,预算 N 对 N/2,GPU 时间比 ∈ **[0.35, 0.70]**(量不出「活儿少一半」的尺子不配报任何数);
- 全部帧 `dropped == 0`、`truncated == 0`;
- 热状态从未到 3(critical);
- **噪声底**:C2 与 C 是同一条臂换轮内位置,逐轮 p50 壁钟比 |C2/C − 1| 的中位数 **≤ 5%**。任何 C 对 F 的差异小于 2× 噪声底一律报「分不开」。

### 5.2 「稳定 30 fps」—— 分两个口径各下一次结论
- **首次飞行**(`FIRST` 块:进程里第一次沿轨迹飞,磁盘基本是冷的,= 用户第一次打开模型时的体验);
- **重复飞行**(A/B 轮里的 C 与 C2 合并:已做过顺序预读,页缓存尽量热)。

两个口径都去掉每块前 30 帧(块内缓存清空后的冷启动,单独报)。**全部**满足才算稳定:
1. 壁钟 p95 ≤ 33.3 ms;
2. 超过 33.3 ms 的帧 ≤ 5%;
3. p99 ≤ 50 ms;
4. 单帧最大 ≤ 100 ms;
5. C 臂各块热状态始终 < 2(serious)—— 到过 serious 就只能报「短时达标、未证明可持续」;
6. **不是靠什么都不画换来的**:px 中位数 < 4000(控制器没被顶到上限)。

每块前 30 帧(块内冷启动,缓存已清空)单独报:首帧耗时、首帧读盘量、到「完整细节」的时间。

### 5.3 「到达完整细节」的时间
在静止段(hold_overview、hold_leaf、COLD 块)内:从段首到「画出的点数稳定在段末值 ±1% 且之后再无上传」的那一帧,按节拍折算成 ms。(不用 px 判稳:预算撞顶后控制器会继续降 px 而画面不变。)

### 5.4 细节判据(能失败)
一帧**保住了细节** ⇔ 它与参考图的差不超过抖动底噪:差异像素比例 ≤ max(1.25×底噪, 底噪+0.5pp) **且** PSNR ≥ 底噪 PSNR − 1 dB。
🔴 旧判据「饱和度与标准差在参考的 [0.8, 1.25] 倍内」**已证明看不见细节损失**(Mac 上 px=150 在 orbit_mid 通过了它,但全分辨率裁图肉眼可见盒子上的印刷糊了),只保留作「同一场景、不是平灰」的健全性检查;平灰图阴性对照必须被「非平凡」判据拒掉。

### 5.5 I/O 卡顿
加载 > 8 ms 的帧数、最大加载耗时;「I/O 造成的掉帧」= 帧 > 33.3 ms 且(加载+上传)> 该帧一半。

### 5.6 消融 C vs F
逐轮配对:p50/p95 壁钟比、超 33.3 ms 比例之差、平均点数比、各段点数与最深层级;在 4 个位姿上两臂的细节判据结果。

## 6. 运行顺序与停止规则

**每朵云三次启动,顺序固定**(先测帧率,因为任何整读都会预热页缓存):
1. `perf`:COLD 块(90 帧,总览静止,控制器开)→ **FIRST 块**(控制器臂整条轨迹,首次飞行)→ **顺序预读整个 octree.bin**(计时,顺带得到手机顺序读吞吐)→ 3 轮 × {C, F, C2}(轮内次序按轮号旋转,热漂移对所有对比平衡)→ 阳性对照。约 7 分钟。
2. `correct`:四位姿画面判据 + 叶节点检查 + 阴性对照。约 1–2 分钟。
3. `lodverify`:外壳用 CryptoKit 对容器里三个文件算 sha256,与 Mac 端比对(放最后:整读 3.9 GB 会灌满页缓存)。

先 36M 全套,冷却 ≥ 10 分钟(手机摸着不热、上一次 JSON 里末尾热状态为 0)再 216M 全套。

**停止规则**
- 热状态到 3:引擎在块边界自停,本次作废;冷却后最多重跑 1 次。
- 阳性对照失败或噪声底 > 5%:作废,冷却 10 分钟重跑 1 次;再失败就停,报告「这台机当天测不准」,不换口径硬测。
- App 崩溃 / 30 分钟拿不到结果 JSON:停,报告,不擅自重试。
- 每朵云每个 session 最多 2 次 `perf`。
- 设备状态:不充电、亮度固定、App 保持前台(台架已钉住不锁屏);**用户说「在了」之前不启动**。

## 7. 数据

| | 点数 | octree.bin | hierarchy.bin | Mac 路径 | sha256(octree.bin) |
|---|---:|---:|---:|---|---|
| 36M | 36,232,793 | 652,190,274 B | 543,466 B | `~/Developer/pw_lod_data/oct_prod/` | `d12f7eb3…c9cb6` |
| 216M | 216,655,968 | 3,899,807,424 B | 2,662,154 B | `~/Developer/pw_lod_data/oct_216M/` | `3b8c87ec…f53dd` |

全部文件已与服务器两端 sha256 比对一致(见报告)。**仅研发期**:树在服务器上用 PotreeConverter 建,不进产品(产品铁律「永远没有云端」,设备端建树是另一条线)。

**进台架容器**:装好台架后 `devicectl device copy to --domain-type appDataContainer --domain-identifier com.kyle.PWSplatAB`,目录拷贝到 `Documents/lod/oct_prod/`、`Documents/lod/oct_216M/`(不加 `--remove-existing-content`,不动容器里原有的 `cloud.bin` 与历史结果)。

**手机空间**:需要 0.65 + 3.90 GB 数据 + 约 0.3 GB 结果图 ≈ **5 GB 可用**。iPhone 容量 512 GB,但 `devicectl` 不报剩余空间、`ideviceinfo` 连不上这台机 ⇒ **剩余空间我查不到,需要用户在「设置 › 通用 › iPhone 储存空间」确认 ≥ 5 GB**。

**内存**:perf 约 160 MB(CPU 缓存)+ 175 MB(GPU)+ 树结构 < 25 MB;correct 的 2,000 万点参考图约 330 MB + 320 MB。远低于 6 GB 机的前台上限。

## 8. 跨端自证
- `Sources/lod/pw_lod_bench.{h,cpp}` 剥注释前后 grep `__APPLE__|TARGET_OS|Metal|MTL` 均为 **0**;只 include 标准库、`webgpu/webgpu.h` 与 LOD 库;适配器用**默认后端**请求(不写死任何后端)。
- 同一份引擎源码已用 **Android NDK r29 交叉编译并链接**成 arm64 `.so`(`-Werror -fno-exceptions -fno-rtti`,`--no-undefined` 链 Android 版 Dawn):编得过、链得上,**没在安卓上跑过**。
- iOS 专属的只有外壳 `Sources/App.swift`(SwiftUI 窗口、热状态、内存、CryptoKit 校验)与 Xcode 工程。

## 9. 已知局限 / 未知
1. **加载是同步的**(库只给同步 API)⇒ 运动中新节点的读盘+解码+上传直接进帧时间。Mac(M3 Pro)上的管道试跑里,控制器臂已出现 I/O 引起的超时帧而固定 150 px 臂没有 —— 真机上这很可能是主要失败模式。异步化属于库的改动,只作建议。
2. **离屏 + 每帧等 GPU**:不含合成器/上屏开销,也没有 CPU/GPU 流水重叠;与成本线同口径,但不等于 App 里的真实帧。
3. **页缓存不可控**:iOS 没有 drop-caches;拷贝进容器本身就会预热。COLD 块报的是「新进程第一帧」,不保证是冷盘;用首帧读盘量辅助解读。
4. **GPU 侧逐出是镜像不是同一份账**:库的 `NodeCache` 没有 `contains()` / 逐出回调,台架只能按同比例预算 + 最久未画来镜像;Mac 试跑两边节点数差 < 0.4%(1615 vs 1609)。
5. 参考图本身受 2,000 万点预算限制(orbit/pan 位姿会撞顶),所以「丢细节」是相对这个参考说的。
6. 只有一台 A16;数字不得当三端数字引用。

## 10. 修订记录(都在任何真机数据之前)
- **r1(初稿)** → **r2**:三处改动,全部来自 Mac 管道试跑,没有一处来自真机数据:
  1. **细节判据**:原「饱和度/标准差比值」在 Mac 上放行了肉眼可见糊掉的帧 ⇒ 改成 §5.4 的抖动底噪判据,旧判据降为健全性检查。
  2. **取景**:根立方体 → 内容框(§3)。216M 按根立方体取景时 orbit/pan 对着空处。
  3. **I/O 混杂**:Mac 上 216M 第 0 轮第一块 p95 123 ms,同一条臂两块后 27 ms,差别来自页缓存冷热而不是臂 ⇒ 加 `FIRST` 块(单独下「首次飞行」结论)+ 顺序预读,A/B 轮只比臂。

## 11. 装机与运行清单(🔴 每一步都要用户先批准;由主会话执行,台架线不执行)

```bash
UDID=<device-coredevice-id>
BID=com.kyle.PWSplatAB                      # 台架 bundle;全流程没有 uninstall、没有 flutter
APP=~/Developer/pw_splat_ab_bench/build_lod/Build/Products/Release-iphoneos/PWSplatAB.app
# 0) 预检(不碰手机):必须输出 com.kyle.PWSplatAB 且签名有效
/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' $APP/Info.plist
codesign --verify --deep --strict $APP && shasum -a 256 $APP/PWSplatAB
# 1) 装机 = 原地更新手机上已有的台架 App(容器保留)
xcrun devicectl device install app --device $UDID $APP
# 2) 数据进台架容器(逐文件、显式目的路径;不加 --remove-existing-content)
for D in oct_prod oct_216M; do for f in metadata.json hierarchy.bin octree.bin; do
  xcrun devicectl device copy to --device $UDID --domain-type appDataContainer \
    --domain-identifier $BID --source ~/Developer/pw_lod_data/$D/$f --destination Documents/lod/$D/$f
done; done
xcrun devicectl device info files --device $UDID --domain-type appDataContainer \
  --domain-identifier $BID --subdirectory Documents/lod        # 只读核对:大小逐字节对上
# 3) 用户说「在了」之后(手机解锁、不充电、App 前台),按 §6 顺序:
./run_lod.sh results_dev/lod_36M_perf.json    oct_prod perf      d36p1
./run_lod.sh results_dev/lod_36M_correct.json oct_prod correct   d36c1
./run_lod.sh results_dev/verify_36M.json      oct_prod lodverify d36v1
./run_lod.sh results_dev/lod_216M_perf.json    oct_216M perf      d216p1 600   # 冷却 10 分钟
./run_lod.sh results_dev/lod_216M_correct.json oct_216M correct   d216c1
./run_lod.sh results_dev/verify_216M.json      oct_216M lodverify d216v1
python3 analyze_lod.py results_dev/lod_36M_perf.json; python3 analyze_lod.py results_dev/lod_216M_perf.json
```
verify JSON 里的 sha256 必须等于 §7 的值;不等 ⇒ 该云的全部结果作废。

## 12. r3(2026-09-24):修完之后的方案增补 —— 仍在任何真机数据之前

### 12.1 载体变了
用户已定:**真机测帧率合进 `~/Developer/arloopbench`(唯一台架)**。`pw_splat_ab_bench` 的 iOS 外壳冻结,不再为它准备装机包,§11 的装机清单作废;本仓只作 Mac 上的验证工具。引擎侧 `Sources/lod/pw_lod_bench.cpp` 零平台代码,可以原样作为「测量内核」带过去;怎么进 arloopbench 见报告里的接入调查。

### 12.2 被测系统变了
LOD 库换成本地分支 `feat/pointcloud-lod-async`(`d251451`):照抄 Potree 的异步加载 + 每帧上限(≤2 次 GPU 上传、≤4 个加载在途)+ 父节点顶替;另有 Potree `PointSizeType.ADAPTIVE` 自适应点大小(WGSL 转写,偏离 P1–P6)。

### 12.3 新臂(同一进程、轮内轮换、每臂带 2 号噪声底)
| 臂 | 加载 | 控制器 | 点大小 |
|---|---|---|---|
| S / S2 | 同步(PR #98 原样) | 开 | 生产公式 |
| A / A2 | 异步 + Potree 限流 | 开 | 生产公式 |
| AP / AP2 | 异步 + Potree 限流 | 开 | Potree ADAPTIVE |
| (F) | 同步 | 固定 150 px | 生产公式,可选 |

COLD/FIRST 块用 `first=S` 或 `first=A` 各跑一次进程(两次启动之间冷却,页缓存状态照 §9.3 如实记录)。

### 12.4 新指标
- **I/O 可消除的超时帧**:帧 > 33.3 ms 且「去掉本帧加载+上传时间就 ≤ 33.3 ms」。原来的「I/O 占一半以上」口径严重低估(Mac 36M 同步:191 帧 vs 2 帧),**降为辅助**。
- 帧内 I/O(加载+上传)的 p95 / p99 / 最大值。
- **异步的细节滞后**:每帧待加载点数占比、有待加载节点的帧占比、静止段到达完整细节的时间、hold_leaf 段内目标叶被选中的帧占比。
- 异步正确性:每帧 `dropped == 0`、每帧上传 ≤ 2、在途 ≤ 4;画面判据模式下收敛图与同步图逐位相同,并带「少画一个可见节点必须不同」的阴性对照。
- **透视到后面**:对参考图覆盖的像素,洞 + 深度远 5% 以上的像素占比;底噪 = 参考图横移 0.25 px。getLOD 三方核对(CPU 对 brute force、GPU 对 CPU、清零掩码阴性对照)。

### 12.5 判定(预注册)
1. **异步治好 I/O 卡顿** ⇔ A 的 I/O 可消除超时帧 ≤ S 的 10%,**且** A 的帧内 I/O p99 < S 的 1/3,两者都超过 2× 噪声底。
2. **「稳定 30 fps」** 仍按 §5.2 的六条,对 S、A、AP 各判一次(再加首次飞行)。
3. **异步的代价**如实报数,不设通过线:画得少多少、到达完整细节慢多少。多慢算能接受是产品决定,交用户拍板。Mac 参考值:216M 少画 17%,叶前完整细节晚 2.27 s。
4. **自适应点大小**:「透视到后面」在 4 个位姿上低于底噪算改善;AP/A 的 p95 比值落在 2× 噪声底之内算「不花钱」。

### 12.6 Mac(M3 Pro)上的参考结果(不是真机数字)
| | 216M 同步 S | 216M 异步 A | 216M 异步+自适应 AP |
|---|---:|---:|---:|
| 壁钟 p95 / p99 / 最大 | 33.4 / 41.7 / 77.0 ms | 24.8 / 27.7 / 33.3 ms | 24.7 / 27.6 / 32.8 ms |
| 超 33.3 ms | 5.2% | 0.0% | 0.0% |
| 帧内 I/O p99 / 最大 | 19.0 / 47.8 ms | 2.9 / 9.4 ms | 2.7 / 6.3 ms |
| I/O 可消除超时帧 | 221 / 272 | 0 | 0 |
| 平均点数 | 3.07M | 2.54M | 2.54M |

- 216M 的有效性闸全过:噪声底 S2/S 3.3%、A2/A 2.3%,阳性对照 0.491。
- 36M 同向:I/O 可消除 191 vs 2、超 33.3 ms 4.14% vs 0.06%。但 36M 的 S2/S 噪声底 7.9% 超过 5%,按 §5.1 那一跑的 S 对 A 只能报「方向」。
- 「透视到后面」(216M pan_mid):生产公式 23.2%(洞 20.9% + 远 2.3%),自适应 0.05%,底噪 0.28%。

### 12.7 库层面可调但**未调**的东西
滞后的直接原因是 Potree 的 `loadedToGPUThisFrame < 2`(`Potree_update_visibility.js:300`),30 fps 下每秒最多 60 个节点上 GPU。库里它已是参数(`Residency::maxPromotionsPerFrame`),改它就是偏离 Potree,要用户拍板后再加一条臂,本轮不动。
