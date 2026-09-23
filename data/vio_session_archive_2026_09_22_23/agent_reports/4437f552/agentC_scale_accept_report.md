# ±5% 尺寸容差:验收台架 + 整体等比缩放机制

日期 2026-09-22。两件事都做完了。两个 commit 都已 push。

---

## 🔴 读这张表之前必须先接受的前提

**参照是 ARKit,不是真值。** 下面所有「通过 / 不通过」都是**与 ARKit 的尺度差**,
不是与真实尺寸的差。ARKit 自身带约 **3.5%** 的尺度不确定度(2026-09-20 的尺子
分析:我们用来锚定的那把尺自带 3.45%;同日 COLMAP 仲裁另测 ARKit 自身 ATE 量级
约 11 mm)。这里直接当已知引用,没有重新测。

推论:一场哪怕报 4.9%「通过」,对真实尺寸也可能已经越界;反过来,报 5.2% 的也
不能断言真的超了。**要对「真实尺寸 ±5%」下结论,必须有外部尺子(卷尺 / 标定板),
本台架做不到,也没假装能做。**

---

## 第一件:±5% 验收台架

### 指标选择

判定量 = **Sim3 对齐解出的尺度因子 s 与 1 的偏差**(`|1−s|`),它就是整体尺度本身。

数学上它与 `ate.py` 打印的「尺度偏差」是同一个数,但读法必须改:09-22 的 td 二维
扫描已证明该统计量**随 td 非单调、有假极小**(+20 ms 处 0.21% 比真值点还低,而
同点 ATE 已烂 3.7 倍)。所以它**不能用来挑参数**(挑参数必须用 ATE);但在参数
已经定死之后,它就是 ±5% 容差要管的那个量。脚本因此固定参数、只报尺度,并同时
打印 **SE3 − Sim3 的 ATE 差**(= 释放「尺度」这一个自由度买到的 ATE 改善,即尺度
对总误差的贡献),免得单看一个数。

### 三场结果(全程)

| 场次 | 录制 / 轨迹 | 配对 | 时长 | 尺度因子 s | \|1−s\| | Sim3 ATE | SE3 ATE | 尺度贡献 | ≤5% |
|---|---|---:|---:|---:|---:|---:|---:|---:|:--:|
| phone1 | `run-6e2d4b99` ↔ `_sweep_phone/p_td+8_ba0.tum` | 1644 | 27.40 s | 1.002218 | **0.22%** | 1.98 cm | 1.99 cm | 0.00 cm | **通过** |
| phone2 | `run-5966aec0` ↔ `_sweep_phone2/p_td+8_ba0.tum` | 1577 | 28.80 s | 1.052120 | **5.21%** | 3.64 cm | 3.92 cm | 0.28 cm | 不通过 |
| c4ad6e500 | `run-4ad6e500` ↔ `_sweep_c_4ad6e500/p_td+3_ba0.tum` | 1628 | 28.70 s | 1.178544 | **17.85%** | 6.67 cm | 8.41 cm | 1.74 cm | 不通过 |

s > 1 一律表示**我们的轨迹偏小**(要放大才能对上 ARKit)。三场同向。

**全程口径:1/3 通过。**

### 分段(按时间等分 4 段,各自独立 Sim3)

估算型容差看**最坏段**不看均值 —— 全程的单个 s 会把段间不一致平均掉。口径照
09-20(同场四段,当时实测跨度 0.73%–10.80%)。

| 场次 | 段 | 配对 | 尺度因子 s | \|1−s\| | Sim3 ATE | ≤5% |
|---|---:|---:|---:|---:|---:|:--:|
| phone1 | 1 | 410 | 1.105848 | 10.58% | 1.28 cm | 不通过 |
| phone1 | 2 | 411 | 0.980704 | 1.93% | 1.31 cm | 通过 |
| phone1 | 3 | 411 | 0.926491 | 7.35% | 1.01 cm | 不通过 |
| phone1 | 4 | 412 | 1.020783 | 2.08% | 0.61 cm | 通过 |
| **phone1 段间** | | | **0.9265–1.1058** | **1.93%–10.58%**(极差 8.66 pp) | | **最坏段不通过** |
| phone2 | 1 | 432 | 1.167471 | 16.75% | 1.77 cm | 不通过 |
| phone2 | 2 | 432 | 1.001888 | 0.19% | 1.40 cm | 通过 |
| phone2 | 3 | 432 | 1.094713 | 9.47% | 1.07 cm | 不通过 |
| phone2 | 4 | 281 | 1.085255 | 8.53% | 0.86 cm | 不通过 |
| **phone2 段间** | | | **1.0019–1.1675** | **0.19%–16.75%**(极差 16.56 pp) | | **最坏段不通过** |
| c4ad6e500 | 1 | 430 | 1.058720 | 5.87% | 0.51 cm | 不通过 |
| c4ad6e500 | 2 | 430 | 1.096900 | 9.69% | 2.75 cm | 不通过 |
| c4ad6e500 | 3 | 431 | 1.260338 | 26.03% | 1.04 cm | 不通过 |
| c4ad6e500 | 4 | 337 | 1.132289 | 13.23% | 2.33 cm | 不通过 |
| **c4ad6e500 段间** | | | **1.0587–1.2603** | **5.87%–26.03%**(极差 20.16 pp) | | **最坏段不通过** |

**最坏段口径:0/3 通过。** 三场的段间尺度相对极差都在 **16.5%–19.4%**。

### 这张表说明的三件事

1. **全程 s 会骗人。** phone1 全程 0.22%「漂亮通过」,而它的四段是 10.58% / 1.93%
   / 7.35% / 2.08% —— 前后两段方向相反(1.106 vs 0.926)正好抵消。**0.22% 是抵消
   出来的,不是准出来的。** 这正是「估算型容差要看最坏段」的实证。
2. **段间不一致(16.5%–19.4%)在三场上高度一致**,而全程 s 在三场上差了 80 倍
   (0.22% / 5.21% / 17.85%)。也就是说 VIO 的尺度问题有两个独立成分:一个是
   段内随激励变的抖动(稳定在 ~17%),一个是全程的系统性偏置(场间不稳)。
   09-20「同场四段 0.73%–10.80%」的现象在这三场上复现且更大。
3. **尺度贡献列很小**(0.00 / 0.28 / 1.74 cm)。也就是说这三场的 ATE 主要不是
   尺度造成的 —— 尺度错了,但轨迹形状对。这与「等比缩放是正确的修复手段」自洽:
   一个全局标量就能把尺度按回去,不需要动形状。

### 自证

脚本每场都把 `ate.py` 当子进程跑同一对轨迹,断言 **配对数 / Sim3 ATE / 尺度偏差
/ SE3 ATE 四个数全部对得上**(容差 0.005,即 ate.py 打印精度的一半),对不上就
退出码 2。三场全绿:

```
phone1     ✓ 与 ate.py 一致 (配对 1644 / Sim3 1.98 / 尺度 0.22% / SE3 1.99)
phone2     ✓ 与 ate.py 一致 (配对 1577 / Sim3 3.64 / 尺度 5.21% / SE3 3.92)
c4ad6e500  ✓ 与 ate.py 一致 (配对 1628 / Sim3 6.67 / 尺度 17.85% / SE3 8.41)
```

### 零自研

脚本**不实现任何对齐算法**:它把 `~/Developer/viobench-recordings/ate.py` 的源码
读进来、在 `ARGS=[a for a in sys.argv` 那一行处截断、只 `exec` 前面的函数定义段
(纯 import + def,零副作用),然后直接用它的 `load()` / `umeyama()` /
`align_position_yaw()`。唯一**抄进本文件**的是 ate.py 顶层那 4 行时间配对(它不是
函数,没法 import),逐字对照并在注释里标了来源 —— 上面的自证就是为了防止这 4 行
抄漏。

出处:
- Umeyama 1991, IEEE TPAMI 13(4):376-380 — https://doi.org/10.1109/34.88573
- Zhang & Scaramuzza, IROS 2018 / https://github.com/uzh-rpg/rpg_trajectory_evaluation (commit `8c8ceec`)

### 复现命令

```
R=~/Developer/viobench-recordings
/usr/bin/python3 tools/scale_accept/accept_scale.py \
  --pair phone1    "$R/_sweep_phone/p_td+8_ba0.tum"      "$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum" \
  --pair phone2    "$R/_sweep_phone2/p_td+8_ba0.tum"     "$R/run-5966aec0-cbf1-4abc-af0e-c1fc559da44c/arkit_poses.tum" \
  --pair c4ad6e500 "$R/_sweep_c_4ad6e500/p_td+3_ba0.tum" "$R/run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa/arkit_poses.tum" \
  --ref-y-up
```

未录制、未开摄像头、未碰 iPhone;`_sweep*` 目录全程只读。

---

## 第二件:整体等比缩放机制(库函数,无 UI)

### 🔑 先 grep 了自己的仓 —— 缩放原语已经有了

`lib/official_capture/gravity_align.dart` 已有:
- `scaleAnchoredPoints(Float32List xyz, double s)` → `x' = s·x`(:343)
- `scaleAnchoredPosesPacked(Float64List poses, double s)` → `t' = s·t`(:331)
- `scaleAnchorFactor(...)`(:231)—— 从 **ARKit 相机中心**自动估 s,带 15% 带外拒绝门

而且这条 SCALE-ANCHOR 臂是**生产开启**的(env `OFFICIAL_AETHER_SCALE_ANCHOR=1`)。

所以**没有新写缩放**。新函数是它的推广,补的是三样既有实现没有的东西:
Open3D 的 `center` 参数、**用户输入**这条 s 来源、provenance 记录。
单测逐位断言:`center == 原点` 时新旧两条路径结果**完全相同**,不分叉。

### 放置位置

**`lib/official_capture/metric_rescale.dart`**(新文件,264 行)

选这里的理由:`official_capture/` 是生产血统那一支;几何输出层(`SfmLiveSnapshot`
的 `xyz` + `posesPacked`)在 `official_capture/sfm_live_recon.dart` 里成形,而它调用
的纯函数层就是同目录的 `gravity_align.dart` —— 新文件正贴着它,并沿用它「零 Flutter
依赖、纯 Dart、可用 VM 断言脚本直接驱动」的约定。

**未接 UI,未改任何现有输出路径**:新文件是纯增量,目前没有任何生产代码 import 它。

### 函数签名

```dart
// s = realDistanceMeters / ‖pointA − pointB‖,按 Open3D ScalePoints 语义作用
MetricRescaleResult rescaleToKnownDistance({
  required Float32List xyz,
  required List<double> pointA,          // 缩放前坐标
  required List<double> pointB,
  required double realDistanceMeters,    // 用户输入的真实距离
  Float64List? posesPacked,              // 9 double/帧,可选
  List<double>? center,                  // Open3D 语义;默认原点(= 既有原语的隐含 center)
  ScaleObservabilitySample? vioScaleConfidence,  // 缩放前 VIO 自己的尺度可信度
  DateTime? timestampUtc,
  double maxRelativeDeviation = kMetricRescaleMaxRelativeDeviation, // 0.50
});

// 「两点索引」入口 —— UI 上点中的是点云里的点,拿到的是索引不是坐标
MetricRescaleResult rescaleToKnownDistanceByIndex({
  required Float32List xyz,
  required int indexA,
  required int indexB,
  required double realDistanceMeters,
  Float64List? posesPacked, List<double>? center,
  ScaleObservabilitySample? vioScaleConfidence, DateTime? timestampUtc,
  double maxRelativeDeviation = kMetricRescaleMaxRelativeDeviation,
});

// 底层两个原语(也单独导出,便于复用)
Float32List scalePointsAbout(Float32List xyz, double s, List<double> center);
Float64List scalePosesPackedAbout(Float64List poses, double s, List<double> center);
List<double> anchorPointAt(Float32List xyz, int index);

class MetricRescaleResult { Float32List xyz; Float64List? posesPacked; MetricRescaleProvenanceV1 provenance; }
class MetricRescaleException implements Exception { String code; String message; double? value; }
enum MetricRescaleSource { userEnteredDistance }
```

### 语义出处(MIT,可商用)

Open3D `Geometry3D::ScalePoints`(约 79–83 行):
https://github.com/isl-org/Open3D/blob/main/cpp/open3d/geometry/Geometry3D.cpp

```cpp
void Geometry3D::ScalePoints(const double scale,
                             std::vector<Eigen::Vector3d>& points,
                             const Eigen::Vector3d& center) const {
    for (auto& point : points) {
        point = (point - center) * scale + center;
    }
}
```
Python 侧 `open3d.geometry.PointCloud.scale(scale, center)` 同样**要求 center 显式给**,
不替调用方猜。本文件保持同一约定(默认原点,并注明常见取值是 `get_center()`)。
https://www.open3d.org/docs/release/python_api/open3d.geometry.PointCloud.html

**位姿**(相似变换,旋转不变):COLMAP CamFromWorld `p_cam = R·x + t`、`C = −Rᵀt`,
世界 `x' = s(x−c)+c` ⇒ `C' = s(C−c)+c` ⇒
```
R' = R,  t' = s·t + (s−1)·R·c
```
`c = 0` 时退化成 `t' = s·t`,与既有 `scaleAnchoredPosesPacked` 逐字一致。未注册帧
(`packed[i+1] == 0`)原样透传,同既有契约。

### provenance(`MetricRescaleProvenanceV1`,schema v1)

抄两个建筑测量标准的**声明制思想**(抄思想,不抄文本):
- **USIBD** "Level of Accuracy (LOA) Specification Guide"(C120):区分
  **Measured Accuracy**(实地量到的)与 **Represented Accuracy**(模型里画出来的),
  要求交付物写明两者及其来源。https://usibd.org/
- **ANSI Z765**(Square Footage — Method for Calculating):面积必须声明所用方法,
  数字本身不构成结论。https://www.homeinnovation.com/services/standards/ansi_z765

对我们的含义:用户输入的那一段距离既是**输入**也是**唯一的米制权威** —— 缩放后
整个模型的尺寸都由它背书。所以必须能事后回答「这个 1.73 m 是谁说的」。

字段(`toJson()` 全集,单测断言了 key 全集,一个不许缺):

| 字段 | 含义 |
|---|---|
| `schema_version` | 1 |
| `scale_factor` | s |
| `source` | `userEnteredDistance` |
| `anchor_point_a` / `anchor_point_b` | **缩放前**两点坐标(与 `measured_distance` 自洽) |
| `center` | Open3D 语义的 center |
| `measured_distance` | 缩放前模型里量到的距离 |
| `real_distance` | 用户输入的真实距离(米) |
| `point_count` / `pose_count` | 受影响的点数 / 帧数 |
| `timestamp_utc` | ISO8601 UTC |
| `vio_scale_verdict` | 缩放**前** VIO 自评(`ScaleObservabilityVerdict` 的 name) |
| `vio_relative_scale_sigma` | σ_s/s;匀速段是 Infinity,JSON 里转成 `"inf"` 而不是丢掉 |
| `vio_sample_t_sec` | 该结论的会话内时刻 |

最后三项接的是既有的 `lib/vio/quality/scale_observability.dart`(零 Flutter 依赖,
可直接 import)。**为什么要记**:若 VIO 当时自评 `sufficient` 而用户仍然量出 20%
的修正,那要么用户量错了、要么我们的可观测性判据在撒谎 —— 两种都必须事后可查。

### s 异常:一律显式报错,不静默施加

`MetricRescaleException` 带稳定的机器可读 `code`:

`invalid_real_distance`(≤0 / NaN / ±Inf)、`degenerate_measured_distance`(两点重合)、
`non_finite_scale`、`non_positive_scale`、`scale_out_of_band`(|s−1| > 50%)、
`point_index_out_of_range`、`malformed_point_buffer`、`malformed_poses_buffer`、
`malformed_anchor_point`、`malformed_center`。

**为什么门是 50% 而不是 5%:** ±5% 是**交付容差**,而本函数是**修复手段** —— 用户
来量尺寸,正是因为 VIO 已经偏了(上面三场里有一场偏 17.85%,5% 的门会把它直接
拒掉,那就等于修不了)。既有 SCALE-ANCHOR 的 15% 带外门管的是「ARKit 自动估的 s,
可疑就别用」,权威低于用户亲手量的,所以这里放宽。但**仍要有门**:>50% 几乎只能是
**单位搞错**(厘米当米、英寸当米)或点选错,静默通过会把一次录入错误变成整模型的
永久损坏。

### 测试输出

`test/metric_rescale_test.dart`,**17 个全绿**:

```
00:00 +0: rescaleToKnownDistance — 语义 缩放后两点距离 == 用户输入的真实距离(±1e-9)
00:00 +1: rescaleToKnownDistance — 语义 非轴对齐的体对角线也整体等比(相对误差在 float32 量级内)
00:00 +2: rescaleToKnownDistance — 语义 Open3D ScalePoints 语义:center 本身不动
00:00 +3: rescaleToKnownDistance — 语义 输入缓冲区不被修改
00:00 +4: 与既有原语等价(center == 原点) 点:与 scaleAnchoredPoints 逐位相同
00:00 +5: 与既有原语等价(center == 原点) 位姿:与 scaleAnchoredPosesPacked 逐位相同,未注册帧透传
00:00 +6: 与既有原语等价(center == 原点) 位姿:center 非原点时相机中心按 C' = s(C−c)+c 走
00:00 +7: provenance 字段齐全、自洽、可 JSON 序列化
00:00 +8: provenance 没喂 VIO 可信度时三个字段为 null,其余照常
00:00 +9: s 异常必须显式报错,不静默施加 真实距离 ≤ 0
00:00 +10: s 异常必须显式报错,不静默施加 真实距离非有限(NaN / Infinity)
00:00 +11: s 异常必须显式报错,不静默施加 两点重合 ⇒ 量得距离为 0,s 无定义
00:00 +12: s 异常必须显式报错,不静默施加 s 偏离 1 超过 50%(典型成因:厘米当米)
00:00 +13: s 异常必须显式报错,不静默施加 边界:刚好 ±50% 通过,越一点就拒
00:00 +14: s 异常必须显式报错,不静默施加 点索引越界
00:00 +15: s 异常必须显式报错,不静默施加 缓冲区畸形
00:00 +16: s 异常必须显式报错,不静默施加 锚点 / center 畸形
00:00 +17: All tests passed!
```

合成立方体:边长 20(模型单位),沿 x 量顶点 0↔1 得 20,用户输 21 ⇒ **s = 1.05**。
21 在 float32 上精确可表示,所以 **1e-9 的断言是实打实的**,不是把 float32 误差
藏起来算的。

---

## 🔴 如实报告:失败与未做项

### `flutter test` 全量**不是全绿** —— 但与本次改动无关,已证明

全量结果:**1854 passed / 1 skipped / 11 failed**。

我做了阴性对照:把本次两个新文件**移出仓再跑一遍全量**,失败集合**逐行相同**:

```
test/opencv_autocapture_vision_contract_test.dart: both mobile builds compile the same C++ source and pin 4.0.1
test/opencv_autocapture_vision_contract_test.dart: native ABI is a narrow OpenCV 4.0.1 contract
test/opencv_autocapture_vision_contract_test.dart: receipt freezes dependency, toolchain, ABI, and license identity
test/opencv_autocapture_vision_validation_test.dart            ← 整文件编译失败,不加载
test/social_profile_models_test.dart
test/staging_upload_rls_contract_test.dart: an already-landed staging object still proceeds to finalize
test/staging_upload_rls_contract_test.dart: staging upload does not request upsert without a SELECT policy
test/vio/ffi/xrslam_build_profiles_contract_test.dart: current Android identity tells the observed debug and strip truth
test/vio/ffi/xrslam_build_profiles_contract_test.dart: profile builder verifies identities and never installs artifacts
test/vio/ffi/xrslam_intrinsics_test.dart: 官方复刻臂逐项使用 OpenXRLab iPhone 配置值
test/vio/ffi/xrslam_official_replica_contract_test.dart: Android core has a reproducible, artifact-bound build receipt
test/zz_post_delivery_probe_test.dart                          ← 整文件编译失败,不加载
```

⇒ **12 条全是基线 `f0b3a40` 上已有的缺陷**,本次改动新增 0 条。其中两个文件在
`flutter analyze` 上就是 `undefined_identifier` / `creation_with_non_type`,即在
base commit 上就编译不过。**我没有修它们**(超出本次范围,且都属于构建收据 /
OpenCV ABI / Supabase RLS 三块不相干的领域)。

### `flutter analyze` 全量 **910 issues** —— 同样是基线,本次新增 0

对本次两个文件单独 analyze:`No issues found! (ran in 2.0s)`。
910 条是仓上既有的(大量 `unused_import` / `unnecessary_brace_in_string_interps`
以及上面那两个编译失败文件)。我没有动它们。

### 没做的事

- **没有接 UI**(按要求;UX 由产品负责人定)。新函数目前**零生产调用者** ——
  这一点必须说破:本仓已经有过「决策层建好了没接线」的先例(09-17 的消费层缺失、
  09-20 的 `lib/vio/quality/`)。这次是刻意的,但如果长期没人接,它就会变成下一个。
- **没有做「真实尺寸」验收**,只做了「与 ARKit 的差」。要对 ±5% 下真结论必须有
  外部尺子,本轮没有这个条件。
- **没有重新确认 td 最优点**。三场用的就是任务给定的 `p_td+8` / `p_td+8` / `p_td+3`,
  我按给定值跑,没有重扫 sweep 去验证它们确实是 ATE 极小。
- **没有把 provenance 落盘**(没有改 `official_sfm_sparse_meta.json` 的写入路径,
  那属于「改现有输出路径」)。`toJson()` 已备好,接的时候直接塞。
- **只落在 `lib/official_capture/`**,没有同步到 `lib/capture/` 那个孪生副本
  (任务说「选一处」)。两边的 `gravity_align.dart` 是双份的,日后若要对齐需补。

### 环境

- 磁盘:开工 5.6 Gi 可用 → pocketworld worktree 637 MB → **已删除 worktree**
  (`git worktree remove --force` + `prune`,目录已不存在),现 3.5 Gi 可用。
  分支 `feat/scale-rescale-mechanism` 保留在本地与 origin。
- `pubspec.lock` 被 `flutter pub get` 改过(thermion 本地 path override),
  **已 `git checkout` 还原**,没进 commit。
- 全程未录制、未开摄像头、未碰 iPhone、未写 `~/.claude/`、`_sweep*` 只读。

---

## 两个 commit

| 仓 | 分支 | sha | 内容 |
|---|---|---|---|
| pocketworld-research-benchmarks | `research/basalt-vio-phone-bench-20260829` | `3a908f5a0cd9d40f4761021be3384c60bdf1359f` | `tools/scale_accept/accept_scale.py` + `results_20260922.json` |
| pocketworld | `feat/scale-rescale-mechanism` | `145d8a63905f0da54ff8aff1a05eaa850ace5449` | `lib/official_capture/metric_rescale.dart` + `test/metric_rescale_test.dart` |

两个都已 `push origin`。
