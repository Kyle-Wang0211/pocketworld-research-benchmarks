# 采集期局部 BA 的无损提速(2026-09-07)

## 为什么打这里
匹配器在 WGSL 层三端到顶后(见 `wgsl_matcher_parity_speed_2026-09-03/tools/android_probe/README.md`
09-07 段),生产每帧实测账(build 102,未命名(4),29 帧/候选均 10)是:

| 段 | ms/帧 | 占比 |
|---|---|---|
| 提取 | 573 | 39.7% |
| 匹配器 | 560(GPU 521) | 38.8% |
| **局部 BA** | **268–277** | **18.5%** |
| 几何验证 / 三角化 | 41 / 3 | 3.0% |

局部 BA 从没被碰过(七月只动过 finalize 全局 BA 与采集期**线程数**)。

## 生产遥测里本来就有段账(`frame_split` 的 `ilr_*`,零探针)
`ilr_*` 由 vendored COLMAP `sfm/incremental_mapper.cc` 的 `IterativeLocalRefinement` 打点。
build 102 那场(28 帧有局部 BA):

| 段 | ms/帧 | 占局部 BA |
|---|---|---|
| ilr_find(FindLocalBundle) | 1.15 | 0.4% |
| **ilr_setup**(ba_config 构建 + adjuster 构造) | **21.63** | **7.8%** |
| **ilr_pre**(Ceres 预处理器 = Schur ordering 搜索) | **17.59** | **6.3%** |
| **ilr_min**(Ceres 最小化) | **214.69** | **77.5%** |
| └ ilr_lin / ilr_jac / ilr_res | 126.12 / 45.46 / 18.63 | 45.5% / 16.4% / 6.7% |
| ilr_merge / ilr_filter / ilr_post | 5.31 / 6.84 / 0.45 | 4.6% |
规模 `nres 72558 / npar 23966`;**rounds 2 / solves 2 / iters 31 / conv 1 / nocnv 1**
(每帧两次求解,一次收敛一次撞 15 帽)。
⇒ **77.5% 在 Ceres 最小化里(逐字节约束下动不了),可动的是那 22.5%。**

## Host 回放链(零装机)
`third_party/glomap_vendor/build-host-fullbench/official_replay_bench_exe`
(走**出货代码路径** official_pipeline,不是 vendored colmap):
```
official_replay_bench_exe <official_sfm_live.db> <official_sfm_fed_frames.jsonl> <out_dir> --k=12
```
夹具 = 设备备份里的一场真实采集 `cap_1788764232382558`(40 帧,今日 14:58)。
out_dir 必须**先 mkdir**,否则 `AETHER_SFM_ERR_DB`。
Host 段账与设备**同形**(min 73.8% vs 77.5%、setup 11.2% vs 7.8%、pre 7.2% vs 6.3%)⇒ Mac 是这条的有效代理。

## 🔴 逐字节闸的阳性对照:先证夹具可复现,再拿 sha 当判据
零改动跑两遍:

| 产物 | run1 | run2 | |
|---|---|---|---|
| **cloud.ply**(交付云) | `4056b277fe9062a4` | `4056b277fe9062a4` | ✅ 可当判据 |
| cameras.bin | 同 | 同 | ✅ |
| points3D.bin | `614b8ab6…` | `bd73aef3…` | 🔴 **零改动也不复现** |
| images.bin | `9c5a66f0…` | `75998d19…` | 🔴 同上 |
RESULT 全同(n_reg 39 / n_points 39616 / track3plus 14481 / n_obs 117823 / reproj 1.0267)。
两个 .bin 是哈希表迭代序,**不能当判据**;**合法闸 = cloud.ply 的 sha + RESULT 行**。

## 两把刀(都逐字节,都有一手出处,都是 env 臂:不设 env == 出货路径)
### BA-ORDERING(`OFFICIAL_AETHER_BA_ORDERING=1`)
COLMAP 的 BA **从不设** `linear_solver_ordering`(全仓 grep:只有 glomap `global_positioning.cc:277` 设了),
所以每次 `Solve()` Ceres 都自己重推 Schur 消元顺序 —— 那正是 `ilr_pre`,而且每帧付两次(2 轮)。
**出处:Ceres 自己的 `examples/bundle_adjuster.cc` 的 `SetOrdering()`**(点=消元组 0、相机=组 1),
同款写法本仓已有先例(`global_positioning.cc:277`)。同样的数学,只是把 Ceres 本来要搜的答案递给它。
实现在 `official_pipeline/src/official_bundle_adjustment_ceres.cc` 的 `SolveWithGpuFallback`;
自证行 `[AETHER BA-ORDERING] blocks=4407 pts(g0)=4398 cams(g1)=3`。

### BA-NOSAFETY(`OFFICIAL_AETHER_BA_NOSAFETY=1`)
`ceres::Problem::Options::disable_all_safety_checks`(Ceres 文档的性能开关):跳过 36k 次
`AddResidualBlock` 的逐次校验。实现在同文件 `DefaultBundleAdjuster` 构造处。

## 结果(host,配对交替 ×3,全部 ply sha `4056b277fe9062a4`、RESULT 全同)
| 臂 | 局部 BA/帧 | setup | pre | min | 采集期总墙钟 |
|---|---|---|---|---|---|
| REF ×3 | 144.1 / 145.9 / 145.4 | 15.36 / 15.82 / 15.53 | 10.33 / 10.37 / 10.42 | 106.8 / 108.2 / 107.7 | 12315 / 12377 / 12352 |
| **两刀 ×3** | **138.2 / 137.4 / 136.1** | **13.27 / 13.37 / 13.97** | **5.65 / 5.73 / 6.10** | 105.7 / 104.9 / 102.4 | **12123 / 12167 / 11963** |
两组**完全不重叠**。逐段 Δ:setup **−2.45**、pre **−4.64**、min **−3.34**(三轮一致,非噪声)、
find/post/merge/filter 不变 ⇒ **局部 BA −8.6 ms/帧(−5.9%),采集期总墙钟 −1.8%,逐字节无损。**
换算到设备:局部 BA 277 → ≈262 ms/帧,整帧约 −1%。**未上机(需一次构建+一次装机)。**

## 🔴 踩的坑:平行同名实现(08-05 那条又中一次)
两把刀第一轮打在 vendored 的 `colmap-src/colmap/estimators/bundle_adjustment_ceres.cc` 上,
而出货编的是 `official_pipeline/src/official_bundle_adjustment_ceres.cc`。
**第一轮"NOSAFETY 零收益"是假的 —— 那一臂根本没跑。**
是和刀一起写进去的**计数自证行没打出来**当场抓到的(pre 也纹丝不动)。
定则不变:**env 驱动的臂必须自带进程内自证输出,并且先确认自证真的出现。**

## 未做/判死
- `ilr_min` 76%:Ceres 内部,逐字节约束下无手可伸(解析 Jacobian 早已生效;LAPACK/混合精度/solver 换型/外部库七月全判死)。
- `ilr_setup` 剩下的 13.4 ms 主要是**每观测 new 一个 cost function**(≈15 万次分配/帧),
  要碰就得自管生命周期 = **自研,不做**。
- `ba_local_function_tolerance = 0`(COLMAP 上游默认)⇒ 每帧 2 次求解里 1 次撞 15 帽不收敛。
  全局侧同一缺陷 06-24 改 0→1e-6 值 **−30% 墙钟、代价 ±0.003 reproj(已出货)**。
  旋钮 `OFFICIAL_AETHER_LIVE_LBA_FTOL` 早已建好 —— **但它改的是解,不是无损**,需用户签质量取舍。
- 线程数:07-29 已出货(`LiveBaThreads()=min(6,hw-2)` + MT 地板 6000,host −26.2%,逐字节)。
  注释留着"Device must still confirm the optimum on 6 cores",但**跑局部 BA 的设备只有 iPhone 一台**
  (安卓两台只装了匹配器/提取器探针,没有 SfM/BA),**一台机验不出跨端公式** ⇒ 按"今天无法跨端验证"关闭。
