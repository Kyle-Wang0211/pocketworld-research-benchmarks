#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🔴 **bench-only ruler v2** —— 用同一份录制里的 LiDAR 深度,给 ARKit / XRSLAM 各自的轨迹定**绝对米制尺度**。

══ 口径(用户 2026-09-22 / 09-24 / 09-25)══════════════════════════════════════════════
LiDAR 只作研发期量尺。永不进产品代码、产品管线、产品提案。用户 09-25:「我只信任深度相机」⇒ 本尺子是台架
**唯一**的米制参照;加计双积分等只作诊断辅助,不作参照。

══ 输出口径 ═══════════════════════════════════════════════════════════════════════════
  k = 轨迹尺度 / 米          k > 1 ⇒ 轨迹比真实世界**大**;带符号报 (k−1)。
  每条结论都带 95% 区间 = 「按时间分块 bootstrap」∪「方法选择范围」(见下「误差模型」)。

══ v2 相对 v1(research @76b8d47 的 depth_ruler 编排 + 09-24 rec30 版)改了什么 —— 09-25 审计七项 + 焦距 ══
  ① 帧对间隔名实相符、不重复计数:--pair-dts 可给多档;每档报**实际**间隔(中位/最小/最大),同一帧对只算一次,
     某档选出的帧对与前一档完全相同时明写「与 X 档相同」。(v1 在 0.3 s 间隔的子集帧上把标称 0.5/0.75 s 都取成 0.6 s,
     汇总脚本当成两组求均值 ⇒ 重复计数。)
  ② 判定同时看噪声底阳性对照:verdict = G1–G4 ∧ 深度洗牌被拒 ∧ ×1.03/×1.05(无噪声)恢复 ∧(非参照轨迹)噪声底 ×1.03/×1.05 恢复。
  ③ 所有轨迹在**同一批帧对、同一批点**上比较:点掩码 = 各条轨迹几何掩码(正深度 / 重投影 / 三角化角)的**交集**
     ∧ 深度掩码 ∧ 画面中心掩码。v1 按各自轨迹筛点筛对,ARKit 49 对 vs XRSLAM 55–58 对,headline k 不同基。
     轨迹两两之比在同一批点上逐对直接量(LiDAR 在比值里逐对精确约掉),不经任何常数。
  ④ 畸变:录制里**没有**官方畸变数据(ARKit 的 ARCamera.intrinsics 官方定义就是无畸变针孔、不给畸变系数;录制器没存
     AVCameraCalibrationData.lensDistortionLookupTable,单摄视频流也拿不到它 —— 见 PwVioCapability.swift 文件头)。
     按用户要求不自己拟合 ⇒ 只用画面中心 --max-radius-px(默认 600 px,a、b 两帧都要在圈内)。
     09-25 审计实测:半径 ≥800 px 处 LiDAR/三角化比值系统性低 1–2.5%,只用中心/只用边缘的 k 最多差 2.7 pp。
  ⑤ G4 换判法:v1 的 G4 用「相邻深度行」(±100 ms 步长)只能查粗错位。v2 的 G4 直接**估计深度相对图像的时间偏移 δ**:
     参照轨迹给相机线速度/角速度,预测每个点的深度变化率 ż = −(v + ω×X)_z(X 用 LiDAR 反投影),
     帧对内去均值后 log(d_LiDAR/z_三角化) 对 ż/d 做回归,斜率 = δ(ms 级分辨率),时间分块 bootstrap 给区间;
     闸 = 把深度按 δ 校正后参照轨迹的 k 变化 ≤ --g4-max-dk(默认 0.25%)—— 只关心时间偏移对尺度有没有影响。
     v1 的相邻行曲线保留为诊断(coarse_alignment_curve),不再作闸。
  ⑥ 用全部深度帧:--depth-dir 可让深度来自 ruler_subset/ 而图像来自整份录制(整份 896 帧灰度都在,子集只存了 99 帧灰度,
     却有 296 张深度)⇒ 可用帧 99 → ~290。
  ⑦ 链式换算不再依赖单次运行的常数:报告里直接给每条轨迹对 LiDAR 的 k 与两两同点比值(同一批帧对)。
  ⑧ 焦距敏感度:ARKit 报的焦距是否偏小尚无定论(09-25 诊断:固定 ARKit 相对位姿拟合对极误差 ⇒ 真焦距 ≈ 报的 ×1.015–1.027;
     陀螺版 ×1.006–1.017 且对外参 ±0.68° 敏感 ±1%;纯图像 F 矩阵自标定分辨不了)。尺子把 fx、fy 同乘 α 重三角化,
     报 dk/dα,并把 α ∈ [1, --focal-alpha-hi](默认 1.03)计入方法范围。只用画面中心 + 前后向基线占比越大越不敏感。
  ⑨ 95% 区间 = 按时间分块 bootstrap(块长 --block-s,默认 3 s;写法同 vendored/scale_eval.block_bootstrap)
     ∪ 方法选择范围(估计器 × 置信度 × 中心半径 × 深度段 × 焦距 α × 深度时间校正,见 method_variants())
     ∪(非参照轨迹)噪声底带 k × [NC 2.5%, NC 97.5%]。

══ 尺子本体:逐字复用 09-22 的 depth_ruler.py(research @ 76b8d47,vendored/ 下原样)════════
  特征 + 匹配   SIFT + BFMatcher.knnMatch + Lowe 比值 0.8(IJCV 2004 §7.1;OpenCV py_matcher 教程)
  三角化       cv2.triangulatePoints(DLT,H&Z §12.2),**位姿不估**:两帧相对位姿取自被测轨迹
  深度取值      depth_ruler.sample_depth():u_d = (u_c+0.5)·W_d/W_c − 0.5 最近邻
  尺度对齐      monodepth2 evaluate_depth.py L207 `ratio = np.median(gt)/np.median(pred)`(逐帧对),
               L218 `med = np.median(ratios)`(跨帧对)
方法地图:exact_upstream = 上面四行 + block bootstrap(scale_eval.block_bootstrap 同写法)+ 噪声底(noise_floor.py 同法);
product_adapter = 编排(多档帧对、共同点掩码、中心掩码、方法范围、G4 时间偏移回归、深度来自子集目录);
not_implemented = 镜头畸变校正(没有官方数据,见 ④)。

══ 已知局限(照实报)═════════════════════════════════════════════════════════════════════
  · LiDAR 自己不是真值:公开逐帧 sceneDepth 实测(high 置信)系统偏差约 −2%…+0.5%(Zea & Hanebeck, JAIF 17(2) 2022
    图 8:1–4 m 恒为负、1–2%;Tondo 等 Sensors 2023 表 1:0.3/0.4/1.0 m 处 −0.3/−0.75/+0.1%)⇒ **LiDAR 的系统偏差原样进 k**,
    本尺子的区间不含它(合成 T9 自证),读结论时要再加这一项。
  · ARKit 在有 LiDAR 的机型上是否用了 LiDAR 做跟踪,Apple 没说 ⇒ ARKit 的 k 与 LiDAR 不一定独立;XRSLAM 不受影响。
  · 深度图 256×192 对 1920×1440 是 7.5× 下采样;sceneDepth 是 LiDAR(约 15 Hz)+RGB 融合上采样到 60 Hz 的稠密图。

vendored/(只读取用的原件拷贝):depth_ruler.py / charuco_scale_arbiter.py / synth_verify.py / synth_depth_verify.py
  ← 研究仓 research/basalt-vio-phone-bench-20260829 @ 76b8d47;scale_eval.py / noise_floor.py ← 09-24 真值审计;ate.py。

用法:
  /usr/bin/python3 lidar_ruler.py --recording <run-…> --depth-dir <run-…>/ruler_subset \
      --arkit --camera 名字=相机位姿TUM(OpenCV 轴,按录制帧 t_ns)… --out <dir>
  老用法(--xrslam-camera / --xrslam + --xrslam-ledger / 子集目录直接当 --recording)照旧可用。
  (要能 import cv2 + numpy 的解释器;本机 /usr/bin/python3 = cv2 4.13.0 + numpy 2.0.2。)
"""

