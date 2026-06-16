# DiffMVS 桌面验证结果 — 能否「替掉 DA3」做 PocketWorld 上游几何

> 任务见 [`DIFFMVS_TEST_BRIEF.md`](DIFFMVS_TEST_BRIEF.md)。本机真实数据(414 张 3840×2160 室内拍摄:蓝凳+地球仪+木地板+窗口强光),ARKit 位姿,纯 MVS(丢弃 DA3 深度)。
> 日期 2026-06-16。环境:`/opt/homebrew/bin/python3.11` + torch 2.12(MPS)+ open3d 0.19。

## TL;DR 总判断

**DiffMVS 作为「逐帧深度源」验证通过 —— 快、度量一致、无纹理地板不塌。但「靠原生置信度免融合」这条具体设计被证伪,且要在物体细节上追平 DA3,缺的不是深度而是一个像样的几何一致性融合器(当前朴素融合还差)。**

一句话:**换 DA3 这条路立得住,但赢点在「快 + 多视天生一致」,不在「置信度自动兜无纹理」。需要补一个 COLMAP 式融合器,而不是 conf 阈值 + Poisson。**

---

## 逐条回答 6 条成功判据

### 1. 置信度假设成立吗?——**否(按原文表述被证伪)** ❌→重要修正
原假设:`photometric_confidence` 在无纹理木地板上塌下去,可用于 mask 兜洞。
**实测(367 万像素跨 8 帧定量):**
- Pearson r(局部纹理, 置信度) = **−0.148**(负相关,纹理越高 conf 略越低)
- 最低纹理桶 mean conf = **0.602**,最高纹理桶 = **0.439**,比值 1.37
- **结论:光照良好的无纹理木地板 → 置信度 HIGH(不塌)。** 置信度真正塌的地方是:**窗口强光/过曝、地球仪的高光曲面、遮挡边界、以及整帧匹配失败的坏帧**(见 `DELIV1_confidence_montage.png`)。
- 机理:DiffMVS 的 conf 是 GRU sigmoid **学出来的**,平滑代价体 → 学成「平=自信」,不是经典光度置信度。
- **战略含义:** 「用 conf 找无纹理洞 → mask → Poisson 补」这个**具体免融合设计不成立**。但好消息是——无纹理地板**根本不需要兜**(见判据 4,MVS 自己就把光照良好的地板做对了)。conf 仍有用,但用途变成**剔除过曝/高光/遮挡/坏帧**,不是剔除无纹理。

### 2. 多视一致吗?——**是,而且这是最大的赢点** ✅
- 33 窗 × 2 参考 = 66 帧逐帧深度,**不做任何 FixB/BA**,直接反投影融合。
- **主平面(地板)RANSAC:法向 = [0.01, 1.00, 0.00](正确水平,Y-up),厚度 RMS = 5.7mm。**
- 对比 DA3:必须 FixB(每窗单尺度,地板~22mm)+ BA(尺度+位移联合,~18mm,对齐下限)。
- **DiffMVS 5.7mm vs DA3 18mm,且零对齐。** 纯 MVS 靠匹配天生一致,这正是 brief 预期的核心收益,**实锤了**。

### 3. 薄结构保住了吗?——**逐帧在;朴素融合后丢了(融合问题,非深度问题)** ⚠️
- **逐帧深度是干净的、3D 连贯的**:把单帧点云从另一视角渲染(`single_w0_fromv5.png`),木地板纹理清晰、凳面平整、几何正确(黑洞只是单帧遮挡)。
- 但 66 帧 **朴素 conf≥0.6 + Poisson** 融合后,凳子/地球仪糊成一团,横杠基本没了(`cmp2_diffmvs_w0.png`)。
- 原因:**这不是对等比较** —— DA3 基线用了 COLMAP 式几何一致性(深度 1% + 重投影 2px 跨窗确认),我这边只是阈值堆点。薄结构需要好融合器,不是 DiffMVS 做不出。

### 4. 无纹理被兜住了吗?——**是(且不靠 Poisson 兜,MVS 直接做对)** ✅
- 光照良好的无纹理木地板:**逐帧深度直接正确**(纹理脆、平整、单层 5.7mm)。
- 真正的敌人是**窗口强光/高光反射/过曝**,不是「无纹理」本身。那些区域 conf 低 → 可剔除;剔除后 Poisson 全局插值补平没问题。

### 5. 速度?——**是,~100–200ms 级,彻底碾压 DA3 的几小时** ✅
- 512×896, N=5(1 参考 + 4 源),实测:**MPS 暖 0.204s/帧**(min 0.196s);CPU 暖 1.13s/帧。
- 参数量 **0.754M**(确认 ~0.75M,比 DA3-BASE 410M 小 ~540×)。
- 手机外推:M 系 GPU 0.2s/帧 → 手机 GPU/ANE 同级;phone 目标 N=2-3 / 256-384px 更便宜 → **百毫秒级逐帧**。对比 DA3 K=3@252 单窗 517ms 且整体几小时、K=4 NaN。**速度税一次性消掉。**

### 6. 最终对比 DA3 最优?——**地板相当/更好(更薄无 BA);物体当前更差(朴素融合所致)** ⚠️
- 对比页:`~/Desktop/expF2_easy_clouds_2026_06_12/diffmvs_vs_da3_compare.html`(切 1=DA3最优 / 2=DiffMVS d10 / 3=d9,同视角)。
- 同视角静图:`diffmvs_out/cmp2_diffmvs_w0.png`(DiffMVS) vs `cmp_da3_w0.png`(DA3)。
- DA3 凳子+地球仪+横杠+柜子清晰;DiffMVS 物体糊(朴素融合)。**地板 DiffMVS 更薄更干净。**

---

## 手机可行性 & CoreML 拦路(deliverable 3)
- 模型 0.75M 参数,~3MB,RAM 可忽略(3072MB 预算内)。
- 逐帧 0.2s(Mac GPU)→ 手机百毫秒级可期;**逐像素可框选**(MVS 本性)。
- CoreML 拦路(移植时):`grid_sample`(单应 warp + GetCost 两处)、一个很小的 3D-CNN 代价体正则(base_channels=8)、GRU/DDIM 静态循环要展开。比 MonoMVSNet 干净一个量级(见 memory `diffmvs-mobile-assessment`)。
- DDIM 确认空操作(`sampling_timesteps [0,1,1]`),真计算是 ConvGRU 迭代——不慢。

## 还差什么(下一步,按性价比)
1. **几何一致性融合器**(最关键):把 `expAT_geomcons_tsdf.py` 的 COLMAP 式跨帧深度确认(深度1% + 重投影2px)接到 DiffMVS 逐帧深度上,替掉朴素 conf 阈值。这一步大概率把物体细节追平/超过 DA3——因为逐帧深度本就是干净的。
2. **conf 用途重定向**:从「兜无纹理」改成「剔过曝/高光/遮挡/坏帧」。
3. **源帧选择**已修(要求基线 ≥6cm;纯最近邻会选到 1.2cm 共址帧 → 近物三角化崩)。N=5 优于 N=3。
4. 商用权重重训(DTU/BlendedMVS 学术条款;~1M 参数重训便宜)——上线前,非本验证范围。
5. 用 CasDiffMVS(更准)再跑一轮对比(本轮用轻量 DiffMVS)。

## 交付物清单
- **判据1 置信度热力图**:`diffmvs_out/DELIV1_confidence_montage.png` + 每帧 `diffmvs_out/win*/conf_overlay.png`
- **判据2 地板单层**:floor RMS 5.7mm(见上);`diffmvs_out/fused_diffmvs_conf0.6.ply`
- **判据3/6 对比页**:`~/Desktop/.../diffmvs_vs_da3_compare.html`;静图 `cmp2_diffmvs_w0.png` / `cmp_da3_w0.png` / `single_w0_fromv5.png`
- **网格**:`diffmvs_out/mesh_diffmvs_d{9,10}_c0.6.ply`(已复制到 Desktop poisson/ 供对比页)
- **代码**:`pw_diffmvs_common.py`(模型/IO)、`pw_diffmvs_run.py`(适配器+逐帧)、`pw_diffmvs_batch.py`(置信度定量测试)、`pw_diffmvs_fuse.py`(融合+地板)、`pw_mesh.py`(Poisson,n_threads=1 修复段错误)、`pw_splat.py`(无头渲染)

## 关键工程坑(避免重走)
- `models/module.py:7` 硬编码 `device="cuda:0"` 的 warmup → 已改 MPS/CPU 自适应。
- `test.py` 硬编码 `.cuda()` / DTU 文件格式 → **没复用**,自写逐帧驱动直接喂 npz 张量。
- 输入 H,W 必须能被 32 整除(3D 代价体 U-Net):504 → 渲染到 **512**(K 的 y 行按 512/504 缩放)。
- **Open3D Poisson 在噪声点云上硬崩**(`Failed to close loop`,进程级 exit 绕过 try/except)→ **`n_threads=1` 解决**。
- depth_values 是**逆深度** linspace(1/dmax→1/dmin, 384);度量范围从 SfM anchors 取(DA3 深度未对齐位姿,不能直接用)。w2c/K 方向用 anchor 重投影自检 = **0.6px**。
