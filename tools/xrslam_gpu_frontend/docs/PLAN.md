# XRSLAM detection on the GPU — plan (2026-09-04)

Owner's bar: not worse than production ARKit on the same device, metric by metric; every speed-up
lossless (replay ATE/scale not worse than the CPU baseline: Sim3 2.11–2.54 cm, scale 2.4–4.1 %).
Measured on 2026-09-03: at 1920×1440 the CPU front end is 27.9 ms/frame of which GFTT is 20.3 ms
(73 %), CLAHE 3.3, pyramid 2.0, KLT 2.3; the device reaches `serious` within a minute; XRSLAM 1.8–1.9
cores vs ARKit 0.8. Parameter levers are exhausted (tracker_frequent 2 costs +0.8 cm ATE; 640×480
costs scale). The only lossless lever left is compute placement.

## Rules
- Copy, don't invent: port OpenCV 4.0.1 (revision c9ad5779, Apache-2.0) OpenCL kernels to WGSL —
  `corner.cl` (Harris), `gftt.cl` (threshold + NMS + corner list), `clahe.cl`, `pyr_down.cl`,
  `pyrlk.cl` — and keep OpenCV's CPU numerics (Sobel ksize 3 REFLECT_101, unnormalised 3×3 box,
  float32, scale = 1/(2^(ksize-1)·block·255)) as the reference. Sources are frozen in `ref-4.0.1/`.
- Same algorithm, same parameters as XRSLAM's `OpenCvImage`: Harris k = 0.04, qualityLevel 1e-3,
  minDistance 20, blockSize 3, then XRSLAM's own sort + PoissonDiskFilter(keypoint_distance) + 20 px
  border (those stay on the CPU, they are cheap).
- Cross-platform: WGSL on Dawn (Metal on iOS/macOS, Vulkan on Android), the same host as the
  matcher line in `aether_cpp` (`include/aether/render/dawn_gpu_device.h`, baked WGSL).
- FTO: Harris 1988 / CLAHE 1994 / LK 1981 / Gaussian pyramids — no live patents; do NOT implement
  "selective image pyramid" (US 12148128).
- Lossless gate per milestone: (1) Mac: per-frame keypoint set vs OpenCV CPU on EuRoC 752×480 and a
  1920×1440 frame — identical positions and responses within float tolerance, documented; (2) device:
  bench replay of the shared recording, ATE/scale not worse than the CPU baseline; (3) live-soak
  600 s vs ARKit with `pw_relative_verdict.sh`.

## Milestones
- M1 Harris + GFTT candidate selection on Dawn (kernels: sobel_dxdy, harris_box, gftt_max,
  gftt_find). Probe tool dumps eig and corners from both paths and diffs them. Target: ≤1e-5 relative
  on eig, identical corner set after XRSLAM's own selection.
- M2 CLAHE (`clahe.cl`: per-tile histogram + clip + LUT, bilinear interpolation) and the LK pyramid
  (`pyr_down.cl` + the 21×21 border padding of `buildOpticalFlowPyramid`).
- M3 Pyramidal LK (`pyrlk.cl`), forward + reverse, USE_INITIAL_FLOW, 30/0.01 criteria.
- M4 `xrslam::Image` implementation in `xrslam-extra` (`GpuImage`) behind a CMake option, zero-copy
  from the camera buffer where possible; device gates (2) and (3).
Deliverable of each milestone is a receipt-style report in `docs/`.

## Numerics pinned (2026-09-04, from c9ad5779 filter.cpp / box_filter.cpp / corner.cpp)
- Sobel 3×3 small-filter forms: Dx row `S[+1]-S[-1]`, Dx col `(S0+S2)*f1 + S1*f0` (f0=2s,f1=s); Dy row `S0*k0+(S[-1]+S[+1])*k1`, Dy col `S2-S0`. scale = 1/(2^(ksize-1)·block·255) = 1/(4·3·255).
- boxFilter on CV_32FC3: `sumType = CV_64F` → RowSum<float,double> then ColumnSum<double,float>. WGSL has no f64 → eig cannot be bit-exact; gate = corner set identity after threshold/NMS/grid, eig tolerance reported.
- calcHarris: `a*c - b*b - k*(a+c)*(a+c)` in float. findCorners: strict `val == max3x3`, threshold `maxEig*quality`, interior only. Selection: sort desc (ties → later raster address first, `greaterThanPtr`), grid cell = cvRound(minDistance), reject if any accepted point within minDistance² in the 3×3 neighbouring cells, stop at maxCorners.

## M1 结果 (2026-09-04)
- 752×480: candidates 634 → selected 94 = CPU 94, ordered-match 94/94; eig maxabs 7.9e-9, maxrel 3.7e-5 (31 px >1e-5 of 361k)
- 1920×1440: candidates 1406 → selected 200 = CPU 200, ordered-match 200/200; eig maxabs 1.2e-9, maxrel 3.0e-4 (163 px of 2.76M)
- eig 残差来源 = CPU boxFilter 用 double 累加、GPU f32;角点集合/顺序逐一相同 ⇒ 门按"选点一致"判过。
- GPU 时间(M3 Max, 含 2 次回读): 4.95 ms / 9.28 ms。

## M2/M3 数值钉死 (源: OpenCV c9ad5779 = 4.0.1, iOS 真链版本已核 receipt opencv_version=4.0.1, -ffp-contract=off)
XRSLAM 调用序 (xrslam-extra/opencv_image.cpp): preprocess = CLAHE(clip 6.0, tiles 8×8) 原地 → buildOpticalFlowPyramid(win 21×21, maxLevel 3, withDerivatives=true, pyrBorder=REFLECT_101, derivBorder=CONSTANT);
detect = GFTTDetector(150, 1e-3, minDist 20, block 3, harris k=0.04) **在 CLAHE 后的图上** → 按 response 降序 std::sort → PoissonDiskFilter(20) 留 CPU;
track = LK(win 21×21, level 3, COUNT+EPS 30/0.01, USE_INITIAL_FLOW) 正向 + 反向; 接受 = status && 20px 内边框 && |flow| ≤ rows/4 && 反向 status && |curr − reverse| ≤ 0.5.
### CLAHE (clahe.cpp, CPU 路径)
- 尺寸不整除 tiles ⇒ copyMakeBorder 右/下 REFLECT_101 到整除 (1920×1440 / 8 整除, 无需); tileSize = W/8 × H/8; tileSizeTotal = 面积。
- clipLimit = max(int(6.0 * tileSizeTotal / 256), 1); lutScale = 255.f / tileSizeTotal。
- 每 tile: 直方图 int[256]; 裁剪: clipped += h[i]-clip, h[i]=clip; redistBatch = clipped/256; residual = clipped − batch*256; h[i]+=batch; residualStep = max(256/residual,1); for(i=0; i<256 && residual>0; i+=step, residual--) h[i]++。
- LUT: sum 累加, lut[i] = saturate_cast<uchar>(sum * lutScale) (float 乘, cvRound 到最近偶数规则 = saturate_cast 用 cvRound)。
- 插值: txf = x/tw − 0.5f; tx1 = floor, tx2 = tx1+1; xa = txf − tx1(clamp 前算), xa1 = 1−xa; tx1 = max(0), tx2 = min(tilesX−1); 同理 y; res = (L1[ind1]*xa1 + L1[ind2]*xa)*ya1 + (L2[ind1]*xa1 + L2[ind2]*xa)*ya; dst = saturate_cast<uchar>(res) (cvRound)。
### 金字塔 (pyramids.cpp PyrDownNoVec<int,uchar>, pyrDown_ cn=1)
- dsize = ((w+1)/2, (h+1)/2); 边界 REFLECT_101 (borderInterpolate)。
- 横向: row[x] = s[2x]*6 + (s[2x−1]+s[2x+1])*4 + s[2x−2] + s[2x+2] (int); 纵向: dst = (r2*6 + (r1+r3)*4 + r0 + r4 + 128) >> 8 (FixPtCast shift 8)。纵向源行 sy = 2y−2..2y+2 经 borderInterpolate(sy, h, REFLECT_101)。
- buildOpticalFlowPyramid: 每层 copyMakeBorder 21px REFLECT_101|ISOLATED; 下一层尺寸 ≤ win 则截断 (返回实际 level)。1920×1440: 4 层 (1920,960,480,240)。
### Scharr 导数 (lkpyramid.cpp calcSharrDeriv, deriv_type = short, 交错 dx,dy)
- 纵向: t0 = (s[y−1]+s[y+1])*3 + s[y]*10, t1 = s[y+1] − s[y−1]; 行边界 y−1→max(…,1 反射), y+1→rows−2 (REPLICATE 式反射 101)。
- 横向: dx = t0[x+1] − t0[x−1]; dy = (t1[x+1]+t1[x−1])*3 + t1[x]*10; 列边界 x−1→1, x+1→cols−2。
- 导数图外框 21px CONSTANT 0 (derivBorder)。
### LK (LKTrackerInvoker, 定点)
- prevPt = pts/(1<<level); nextPt: 顶层 = initial/(1<<level), 其它 = nextPt*2; halfWin = 10; iprev = floor(prevPt − halfWin); 出界判据 iprevPt.x < −21 || ≥ cols (等价 winSize) ⇒ level0 时 status=0。
- W_BITS=14: iw00 = cvRound((1−a)(1−b)*16384), iw01, iw10 同; iw11 = 16384 − 其余。
- 补丁: ival = CV_DESCALE(I*iw…, 14−5) (即 (v + (1<<8)) >> 9), ixval/iyval = CV_DESCALE(d*iw…, 14); A 累加 int; A11 = iA11 * 2^−20 (float)。
- minEig = (A22+A11 − sqrt((A11−A22)² + 4A12²)) / (2*21*21); minEig < 1e−4 || D < FLT_EPSILON ⇒ level0 status=0, 跳过。
- 迭代 ≤30: inext = floor(nextPt); 出界 ⇒ level0 status=0 break; diff = CV_DESCALE(J*iw…, 9) − Iptr; ib1 += diff*dIx, ib2 += diff*dIy (int); b = ib*2^−20; delta = ((A12*b2 − A22*b1)*D, (A12*b1 − A11*b2)*D), D=1/(A11A22−A12²); nextPt += delta; 写回 nextPt+halfWin; |delta|² ≤ 0.01² 停; j>0 且 |delta+prevDelta| < 0.01 两轴 ⇒ nextPts −= delta*0.5 停。
- err (level0, status=1): 平均 |diff| / 32 (再除 21*21) — XRSLAM 不用 err。
- 注意 pts 在每层被就地更新 (nextPts[ptidx] = nextPt 在层入口先写回)。
### 参照工具: tools/lk_cpu_ref.cpp (dump CLAHE / 各层含 pad / 导数含 pad / gftt / 正反 LK); 门 = 链接 4.0.1 (~/Developer/opencv-401-build-mac), brew 5.0 仅冒烟。

## 09-04 M2/M3 结果与 fast-math 定罪
- cpu-l0 模式(CPU CLAHE 上传, GPU 做 pad+pyrDown+Scharr+LK): 4 层 img/deriv 全 0 差; LK 正反向 150/150 逐位一致(复刻 NEON 累加顺序)。
- 只剩 CLAHE 插值 ±1 (1012/2.76M px): LUT 与 CPU 0 差; 未取整 res 有 32% 像素差 1 ulp; 108 种 FMA/取整变体都不完全匹配。
- 根因: Dawn Metal 后端 `fastMathEnabled = !strictMath`(ShaderModuleMTL.mm:523) ⇒ 默认 **fast-math 开**, 编译器可任意合并/重排; 微内核实测 a*b+c*d 全部编成 fma(c,d,a*b), 嵌套式为 pattern(1,1,1), 但 a*b-0.5 有 1744/65536 两种候选都不中 ⇒ 不可建模。
- 出路: `wgpu::ShaderModuleCompilationOptions{strictMath=true}`(需 device feature ShaderModuleCompilationOptions) 挂到 ShaderModuleDescriptor; LK 内核虽已逐位一致也应在 strict 下复验(其 A12*b2-A22*b1 也可能被合并只是本例没炸)。

## 09-04 M1–M3 关闭 (Mac 数值门全过, 参照 = 4.0.1 本机构建, carotene OFF, -ffp-contract=off)
| 段 | 门 | 结果 |
|---|---|---|
| CLAHE(6,8×8) | 逐字节 | 0 差 (1920×1440) |
| pyrDown ×3 + 21px REFLECT_101 pad | 逐字节 | 0 差, 4 层 |
| Scharr 导数 + 0 pad | 逐字节 | 0 差, 4 层 |
| GFTT(150,1e-3,20,3,harris) 在 CLAHE 图 | 角点集合+顺序 | 150/150 (原图 200/200, EuRoC 94/94) |
| LK 21×21 L3 正向+反向 | 逐位 | 150/150, status 全同 |
- 规则: **Metal 在 strict(safe) 模式下仍合并 a*b+c 为 FMA**; 唯一可靠护栏 = 每个喂进加减的浮点乘积写成 `fma(x,y,0.0)`(+0.0 不会被折叠成 fmul); 权重表(CLAHE txf/xa/ya)在主机按 CPU 原样算好上传(主机 TU 必须 -ffp-contract=off)。护栏后 fast/strict 两模式结果相同。
- harness 新增 AETHER_STRICT_MATH=1 / set_strict_math()(ShaderModuleCompilationOptions.strictMath), 可选非必需。
- 残余风险: Harris eig 用 f32 求和(CPU boxFilter 用 double 累加) ⇒ eig 相对差 ≤ 6e-5; 四个场景角点集合全同, 但阈值/NMS 临界像素理论上可翻转; 由设备端回放 ATE 门兜底。
- Mac(M3 Max) 时间: CLAHE+金字塔+Scharr 两帧 ≈ 25–35 ms 含首帧开销; GFTT 链 6–8 ms(含 2 次回读); LK 150 点 3.3–5.7 ms 含回读。设备上要重测。

## 09-04 M4 装机件 (gpufe 臂)
- `aether_cpp/tools/pw_gpu_frontend.{h,cpp}` + `pw_gpufe_wgsl.h`(由 wgsl/ 生成) → iOS 静态库 `~/Developer/viobench-build/gpufe/libpw_gpu_frontend_ios.a`(脚本 build_gpufe_ios.sh, 照 vendor/aether_ffi/build_gpu_extract_archive.sh 的编法, pw_gpu_frontend.cpp 用 -ffp-contract=off)。Mac 自测 aether_gpufe_selftest: CLAHE 0 差 / detect 150/150 / LK 150/150。
- xrslam-extra `GpuImage : OpenCvImage`(gpu_image.{h,cpp}, CMake 选项 XRSLAM_GPU_FRONTEND, 默认 OFF ⇒ 默认构建零改动), XRSLAMManager.cpp 在 `#ifdef XRSLAM_GPU_FRONTEND` 下用 `GpuImage::create_image()`; 运行期 `PW_XRSLAM_GPU_FRONTEND=1` 才走 GPU, 任何 GPU 失败逐帧回退 CPU 并计数。审计痕迹: `$HOME/Documents/xrslam_gpufe_stats.json`(每 50 帧 + 每次回退写: frames/fallbacks/各段平均 ms)。
- 臂 = thrbp 配方(threading ON + 背压闸, -Dceres=pw_xrslam_ceres_1_14 -ffp-contract=off -fno-fast-math -fchar8_t) + XRSLAM_GPU_FRONTEND=ON, 在 build-cleanA 原地重配(复用 _deps 免下载); 归档 libtool -static(interface+core+extra×2+localization+yaml-cpp, 58 members); `vendor/xrslam/libs/ios-arm64/libxrslam_gpufe_4beb1a9.a` sha 7b3050ba… + receipt; 其它三臂 sha 未动。
- bench: project.yml XRSLAMEngine OTHER_LDFLAGS 末尾加 `$(PW_XRSLAM_EXTRA_LDFLAGS)`(默认空), `scripts/pw_build_gpufe_arm.sh` 传 `-force_load gpufe.a + Debug libwebgpu_dawn.a(668 MB, 产线同款) + Metal/IOSurface/QuartzCore/CoreVideo` → bench-dd-gpufe, engine 38 MB, sha16 0fd10283。启动旗 `-PWXrslamGpuFrontend` → setenv, 回执 app.backend="gpu_frontend"。
- 门: `scripts/pw_chain_gpufe_replay.sh` = 装机 → 回放(无旗对照) → 回放(有旗) → ATE 对 freq-1 基线 2.11–2.54 cm + 拉 stats。

## 09-04 提速刀 (数值不变, Mac selftest 逐位门仍全过)
帧缓冲池(不每帧 alloc) + 每阶段一次 submit(begin/dispatch_batched/end) + u8 打包上传(memcpy) + CLAHE 打包回读(pack_u8 内核, 2.7 MB) + 正反 LK 一次提交(track_fwd_rev, 反向 prevPts 直接用 GPU 上的正向结果) + LK workgroup-per-point(lk_track_wg: 256 线程并行取样/整数乘积, thread 0 串行 NEON 序浮点链, workgroupUniformLoad 控流)。
Mac(M3 Max) 稳态: preprocess 10.1 ms(含 CPU 打包) / detect 2.1 / track(正+反) 2.1 —— 之前 16.9 / 3.4 / 7.6×2。
首次上机(未优化版): preprocess 54 / detect 12 / track 18.5×2 ms, 9.1 fps; CPU 1.73→0.53 核, 热态 nominal 全程。

## 09-04 凌晨 设备上的两个语义/数值坑
1. GFTTDetector 4.0.1 给所有角点 response=0 → XRSLAM 的 std::sort 是对等键排序(确定性打乱) → PoissonDiskFilter 依赖顺序。GPU 路径原先按 eig 排 ⇒ ATE 系统性 +0.9 cm。已按原样复刻(同 cv::KeyPoint 序列 + 同 std::sort)。
2. 设备端审计(每 50 帧 CPU 复算逐位比): CLAHE/检测 0 差, **LK 帧帧有差**; iOS OpenCV LK 与 Mac 参照同为 NEON 路径(反汇编指令计数一致, 无 fma) ⇒ 差在 A16 GPU 侧(fast-math 的 reciprocal/sqrt 精度是首嫌); 库内已改 strict math, 审计加逐点计数/最大差/样例, 首个不一致帧落盘 Documents/xrslam_gpufe_dump 供 Mac 复现。
3. bench 轮询用 devicectl 文件列表会失效(两次把 50 s 的 run 报成 +600/+895 s), 已加直接拷 diagnostics.json 兜底。

## 09-04 03:xx 检测段最后三处数值坑 (全部钉死, Mac 逐位 0 差)
1. Sobel 列滤波 SymmColumnSmallVec_32f 用 v_muladd = **vfmaq_f32 (融合)** on arm64, 与 -ffp-contract=off 无关 ⇒ Dx = fma(S0+S2, s, fl(S1*2s)); Sobel 行滤波(8U→32F 通用 RowFilter)是标量序 ((k0*S0+k1*S1)+k2*S2)。numpy 穷举定案, dx/dy 逐位 0 差。
2. boxFilter 32F 用 double 累加再转 float ⇒ GPU 用 96 位定点精确 9 项求和再一次取整(exact_sum9), eig 逐位 0 差 (1920×1440 两图; 754×480 也要用 4.0.1 参照)。
3. GPU sqrt/div 不保证正确取整(M3 sqrt 26% 差 1 ulp, strict 也一样) ⇒ sqrt_rn/div_rn 用整数中点判定修正硬件结果(64 位乘法 2×u32 模拟), 自检 0 差。
- 残余(接受): CPU boxFilter 的 ColumnSum 是**沿列的滑动 double 累加**, 含极小项(如 3e-21)的列会留下持久的 1e-21 级误差, 在恰好平局的像素把取整翻 1 ulp(1920×1440 CLAHE 图 24 像素, 全在 eig<1e-7 远低于阈值); 逐位复刻要写软件 double 加法器沿列串行, 收益≈0(阈值以上翻转概率~2^-30), 不做。

## 09-04 上午 设备端审计全绿 (M4 数值门关闭)
iPhone 14 Pro 上每 50 帧 CPU 复算逐位对比: CLAHE 33/33、检测 33/33、金字塔+Scharr 32/32、LK 正反向 32/32 全部一致。
教训: v4–v15 追了一夜的"设备 LK 差异"是审计自己的错——XRSLAM 把 IMU 预测位置作为 LK 初值(frame.cpp), CPU 对照用了 curr。**对照必须复刻调用方的全部输入, 包括初值。**
剩余: (1) 设备 detect 15 ms(exact_sum9 太慢)要优化; (2) 直播下 GPU 各段慢 3× 待查; (3) 回放 ×3 + 白天 600 s 直播 vs ARKit。
- 09-04 12:xx 设备上开 AETHER_GPU_TIMESTAMPS=1 后第一帧 detect 的 batch 再没回来(app 挂在第 1 帧, 无 run 目录), Mac 上正常。每内核 GPU 时间只在 Mac 量(harris 4.55 / lk 1.3×2 / scharr 0.75 / sobel 0.57 / pyrdown 0.47 ms), 设备上按阶段总量推。

## 09-04 中午 两刀提速 (数值门不变: CLAHE 0 差 / detect 150/150 / LK 150/150 / eig 逐位同前)
1. 金字塔+导数打包存储(4 px/u32, 导数 2×i16/u32), 所有写内核改"每线程拥有整字"(interp/pad/pyrdown/unpack 按 padded word 分线程, 边界字节由 pad 内核重建)。
2. exact_sum9 加 TwoSum 误差无损快路径(两级级联, 第二级零误差才算数, 否则回退 64/96 位整数路径)。
Mac(M3 Max, 时间戳): harris 4.55 → 3.2(打包) → 0.50 ms(TwoSum); lk_fwd 1.3 → 0.38; scharr 0.75 → 0.17。
- 13:xx 第三刀(LK wg64 + 5 条累加链分线程, 顺序不变): 设备 7.4/5.6/6.2 = **19.3 ms/帧**(原 35.8), 回放 44.7 fps(CPU 臂 36), 审计仍全 0 差, ATE 2.40。设备上 LK 慢的真因是串行链占用率(每 256 线程组只 1 线程在算), 不是算术。
- 18:44 600 s 直播(起步有运动): 1.87 s 初始化, 18 位姿/s, serious 从 102 s 起; **时间桶证明直播慢 2–3× = 热降频**(nominal 23.5 ms/帧 → serious 57 ms), 非唤醒延迟(空提交 1.04 ms)非回退(0)。GPU 臂已优于 CPU 臂(位姿/s 18 vs 10.4, p95 1081 vs 1596, serious 102 s vs 54 s, CPU 0.61 vs 1.9), 对 ARKit 仍 2/9。候选上限 65536→262144(暗场景溢出回退 503 次→0)。
- 20:27 混合切分(GPU 只做 CLAHE+GFTT 且随相机帧预提交; CPU 做金字塔+上游 LK): 直播 29.6 位姿/s(=通道 30 fps 上限), p95 33 ms(优于 ARKit 55), 丢帧 6875→185, 回放 74 fps; 代价 CPU 0.5→0.82(ARKit 0.80), serious 从 265 s 起。跟踪线程 ≈10 ms/帧。用户: 产品拍摄上限 5 分钟 ⇒ 直播测试改 300 s。
