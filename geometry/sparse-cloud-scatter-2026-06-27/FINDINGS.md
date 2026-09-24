# 稀疏点云"球壳厚度/深度散"研究 + 稠密图全批突破 (2026-06-27)

环绕一个地球仪(背景含蓝色塑料凳/抛光木桌)拍 414 帧(iPhone @4224, ARKit pose),
研究"为什么稀疏 SfM 的物体表面是一层模糊壳(地球仪不圆)",以及能否做得**更薄 + 更密 + 更高置信**。

## 问题
稀疏 SfM 点云的物体表面铺成一层 **~7% 半径厚(≈0.5% 场景尺度)的模糊壳**,地球仪看着不是精准的圆。
直觉怀疑是参数没调好。

## 穷举证伪 —— 球壳厚度是不可约的"深度散地板"
用同一 fixture、控制变量,逐个测每个 SfM 旋钮对球壳厚度(scatter.py 窄带 span 指标)的影响:

| 杠杆 | 结果 | 判定 |
|---|---|---|
| K 邻居 8→12→20 | 壳厚不变 | 无效 |
| 分辨率 2112→4224 | 壳厚不变 | 无效 |
| 互检 mutual on/off | 壳厚不变(治整块漂移,不治壳) | 无效 |
| 全局 BA 单次 / 跳过 / 迭代(BA→retri→BA)| 7.9%→7.6%→7.5% | 几乎无效 |
| 点过滤 tri-angle / track-len / reproj | 零相关(r≈0.03),过滤不塌壳 | 无效 |
| 单一共享 focal → 每帧独立相机 | 薄 5-8% | 次要 |
| ARKit 位姿软先验(use_prior_position + CAUCHY)| 净 wash(地球仪薄 6%,地板厚 14%)| 无效 |
| 畸变模型(SIMPLE_PINHOLE vs SIMPLE_RADIAL)| ARKit 帧已采集层校正,残留≈0 | 无效 |

**根因 = 手持 iPhone 环绕的不可约深度散** = 关键点亚像素定位噪声(~0.25% @ 8-14° 三角化角) +
次要卷帘(iPhone ~5ms 读出 + ARKit VIO 已在位姿层补偿)+ 环绕几何深度条件数。
**不是管线 bug,没有 SfM 参数能把球壳压到"视觉清爽"。真正的薄表面是 dense MVS 的活。**

## 突破方向 —— 稠密匹配图 + 全批 = 更密 + 更高置信(2 of 3)
关键区别在**匹配图密度**,不在 BA。`dev_real414.db`(396 帧,完整描述子,**78210 匹配对 = 穷举全连**,
14-17k 特征/帧,全分辨率 SIMPLE_RADIAL)跑全批 mapper(`colmap_bench_exe`):

| 云 | 点数 | 地球仪球壳(%span)| 地板(%span)| track_len | 置信度 |
|---|---|---|---|---|---|
| 流式 K12(2112/SIMPLE_PINHOLE/GPU)| 78461 | 0.67% | 0.47% | ~4 | 低 |
| 稀疏图 224k(3215匹配/每帧相机/全分辨率)| 224587 | **0.48% 最薄** | 0.40% | 5.91 | 中 |
| **稠密图 242k(78210匹配/共享相机/全分辨率)** | 242217 | 0.61% | 0.38% | **6.87 最高** | **高** |

- ✅ **更多空间成点**:稠密图 242k,地球仪内点 27994 vs 224k 的 11644(密 2.4×)
- ✅ **更高置信度**:track_len 6.87(每点被更多相机看到)
- ❌ **更薄**:稠密图球壳 0.61% > 稀疏图 0.48% —— 多出的边缘点把壳撑厚(密度 vs 精度权衡);
  紧过滤(reproj≤0.75 + track≥6)只能压 ~11% 且丢 90% 点,坐实壳厚是地板不是过滤问题。

## 复现 recipe
```
colmap_bench_exe /tmp/dev_real414.db <photos> --out=/tmp/batch_dense   # 全批 mapper, 78210 匹配
python3 scripts/batch_color_measure.py /tmp/batch_dense out.ply         # 上色 + 全量散厚
```
全批耗时 ~16 分钟(957s)/ 396 帧 / 1.66M 观测 / reproj 1.19。

## 结论
- **稀疏 SfM 能给"更密 + 更高置信",不能给"更薄"**(球壳 ~0.5% span 是深度散地板)。
- 242k 稠密图全批 = 当前最密最高置信的稀疏云(本目录 `clouds/cloud_dense242k.ply`)。
- "登峰造极的薄"超出稀疏阶段,需 dense MVS / featuremetric refine(PixSfM)/ 更强特征(ALIKED+LightGlue)—— 见后续。

## 文件
- `clouds/cloud_dense242k.ply` — 稠密图全批 242k 全量彩色(本研究主结果)
- `clouds/cloud_batch224k.ply` — 稀疏图全批 224k 全量彩色(最薄对照)
- `scripts/scatter.py` — 球/平面 RANSAC 散厚测量(支持 PLY + COLMAP points3D.txt)
- `scripts/batch_color_measure.py` — COLMAP recon → 彩色 PLY(track→图→JPEG 采样)+ 全量散厚
- `viewer.html` — Three.js 多云对比 viewer(键切换流式/224k/242k 等)
