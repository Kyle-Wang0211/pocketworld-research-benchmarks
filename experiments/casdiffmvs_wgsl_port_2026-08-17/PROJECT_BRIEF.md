# CasDiffMVS → WGSL 移植:立项书(2026-08-17)

用户拍板:**"把代价体的融合 kernel 走 WGSL 立项"**。
调研家底后,项目性质比"一个提速 kernel"大 —— 说明见 §1。

---

## 1. 为什么这个项目存在

08-14 的 `apde_wgsl_port` HANDOFF §1.2 列了把 CasDiffMVS 逼下台的**三条阻断**。
今天(08-17)的状态:

| 阻断 | 08-14 | 今天 |
|---|---|---|
| ① 权重许可(三个 ckpt 全带 DTU 血统,DTU 无许可声明) | 🔴 未解 | ✅ **已解** —— `casdiffmvs_C_long_ep31.ckpt` 纯 BlendedMVS(CC BY 4.0)从头训,32 轮,与官方差 0.2pp、肉眼无差别 |
| ② **跨端** | 🔴 未解 | 🔴 **仍未解 ← 本项目要解的** |
| ③ 推理不可复现(扩散噪声) | 🔴 未解 | ✅ **可解** —— 逐帧 `manual_seed(seed+f)` 实测逐比特可复现(4290 万像素零差异) |

### ②的具体形状(引 08-14 调研,未复核)

> 只有 **MNN** 一条路 —— 唯一在 Android GPU 上同时具备 `grid_sample` 和
> (转换期重写成 2D 的)3D 卷积的运行时。ONNX Runtime **无任何移动端 GPU EP**,
> TFLite 210 个 builtin **无 GridSample**,华为 MindSpore Lite 同缺。
> 而 MNN issue #4110 报 **GPU 内存约为 CPU 的 2 倍** ⇒ 485MB×2 + App 1020MB
> ≈ 1990MB,**超出 iPhone 11 的 1700MB 预算**。

⚠️ 这段是二手结论,**本项目开工前应抽查一条**(尤其"TFLite 无 GridSample"与
"ONNX 无移动 GPU EP"两条,生态变化快)。今天已有先例:07-31 报告里的官方参数就是错的。

### 替代品已死

APDe-MVS(曾选中的方案)落在 **Adobe US8571328B2** 宽权项内,有效期至 **2031-10-19**。

⇒ **手写 WGSL 是让 CasDiffMVS 出货的最后一块**:移植后**不需要任何 NN 运行时**,
与 APDe 当初被选中的理由完全相同,而权重和专利两条已经干净。

---

## 2. 范围

**目标**:CasDiffMVS 推理的 WGSL 实现,跑在 Dawn(WebGPU)上,三端同一份 kernel。

模型只有 **0.925 M 参数** —— 小到可以手写。需要的算子:

| 算子 | 用在哪 | 备注 |
|---|---|---|
| **融合代价体**(grid+采样+相关+加权累加) | depthnet / GetCost | 🎯 **核心,也是唯一有量级的提速** |
| Conv2d | FeatureNet / ContextNet / CostRegNet(3D→2D 后) | 最常规 |
| Conv3d | 4 层未融合的(`Cout=1` 与 `stride=2`) | 见 §2.1 |
| ConvTranspose2d | conv6/conv7(已由 3D→2D 融合改写) | |
| GRU + 逐元素 | update_block ×2 | tanh/sigmoid/split |
| softmax / interpolate / 凸上采样 | 各 stage 收尾 | |

### 2.1 已有资产直接接进来

- **`models/conv3d_as_2d.py`**(今天做的):11 个 3D 卷积里 7 个改写成单次 Conv2d,
  **权重重排不重训**,数值等价 ~1e-6。两个 ConvTranspose3d 都在其中
  ⇒ **WGSL 只需实现 4 个真 Conv3d**,不是 11 个。
- **APDe 移植的全套基础设施**:`experiments/apde_wgsl_port_2026-08-14/`
  17 kernel / 2741 行 WGSL / host 侧 `.mm` 驱动 / `gen_binding_map.py` / `build.sh`。
  规模可比,**流程和踩坑清单可直接复用**。

### 2.2 融合代价体要做的事(核心 kernel)

当前 PyTorch 版**每帧物化约 1.72 GB**:

| 张量 | 调用/帧 | 单个 | 小计 |
|---|---|---|---|
| `(1,16,4,288,384)` stage3 warp | 27 | 28.3 MB | 764 MB |
| `(1,48,48,72,96)` depthnet warp | 9 | 63.7 MB | 573 MB |
| `(1,32,4,144,192)` stage2 warp | 27 | 14.2 MB | 383 MB |

且**算网格 108.5ms(22.8%)比 grid_sample 采样 33.1ms(6.9%)贵 3.3 倍** ——
因为网格链上每一步(`rot_depth_xyz` / `+trans` / 除法 / 归一化 / stack)
都物化一个 `[B,3,D,H,W]`。

**融合 kernel 的做法**:一个 workgroup 负责一个 (像素, 深度假设) 格点,
在寄存器里算坐标 → 双线性采样源特征 → 与参考特征做分组相关 → 按 view_weight 累加。
**中间量一个字节都不落内存**,输出只有 `[B,G,D,H,W]`(G=4,是输入通道的 1/4~1/12)。

⇒ 物化量从约 1.72 GB 降到约 0.2 GB 量级。**这是唯一还剩量级的提速。**

---

## 3. 🔴 验证协议(先定,再写代码)

**教训来自 APDe 那次**:2741 行全编译通过、占用率满格、耗时正常,
**深度图与真值相关却只有 0.033**。⇒ 静默 bug 只能靠金标准逐层对拍。

本项目三道门,**每道不过不许进下一阶段**:

### 门 1:逐算子对拍(单元级)
每个 WGSL kernel 对同输入与 PyTorch 版比,**相对差 < 1e-5**。
输入用真机 fixture 的真实张量,不用随机数(随机数掩盖边界/索引错误)。

### 门 2:逐 stage 对拍(集成级)
stage1/2/3 各自的输出深度与 PyTorch 版比。
⚠️ **必须先固定扩散种子**,否则对拍的是噪声(同输入两跑 21.5% 像素差 >1%)。
WGSL 侧需实现与 PyTorch 逐位相同的 RNG,或**由 host 把噪声张量传进去**(推荐:
避开 RNG 复刻,APDe 那次的 `curand` skipahead 就没能逐位复刻)。

### 门 3:端到端 + 肉眼
97 帧 fixture 跑完,与 `bench_baseline/OFFICIAL/` 的深度图逐像素比,
再走官方 `fuse_official.py` 出云,**开网页与 OFFICIAL 并排肉眼过**。
判据:`<1%` ≥ 49.75%、误差中位 ≤ 0.80cm、零视图认同 ≤ 23.80%。

---

## 4. 风险与未知(不粉饰)

| 风险 | 现状 |
|---|---|
| **iOS 上的 Dawn 未通** | `CROSS_PLATFORM_STACK.md` 逐字:"Dawn 的 CMake 没有测试过的 iOS 代码路径",Phase 3.1 显式 `AETHER_ENABLE_DAWN=OFF`。**这是 P0 前置**,不解决则本项目只能在 Mac/Android 验证 |
| 工作量 | APDe 是 17 kernel / 2741 行。本项目算子种类更多(GRU/softmax/凸上采样),**但没有 PatchMatch 的随机传播**。量级相当,**未细拆** |
| fp16 | 07-31 实测整模型 fp16 **67.7% 像素相对差 >1%**,不可用。WGSL 里默认 fp32,显存账要按 fp32 算 |
| 端上数字全是推算 | 今天所有 ms 都是 M3/MPS 的 PyTorch 数,**产品端一个真数字都没有**。A16 上唯一实测是 07-31 的 CoreML 710ms/485MB@896×512 |
| 二手结论未复核 | §1 引的跨端调研是 08-14 的,**至少抽查 TFLite/ONNX 两条** |

---

## 5. 分阶段(每阶段有独立可交付物,可随时叫停)

| 阶段 | 内容 | 门 |
|---|---|---|
| **P0** | 复核 §1 的跨端二手结论(抽查 2 条)+ 确认 Dawn-on-iOS 的真实状态 | 结论成立才继续 |
| **P1** | **只做融合代价体 kernel**,host 侧用 PyTorch 喂输入、收输出 | 门 1 |
| **P2** | 量 P1 的 kernel 在 M3 上 vs PyTorch 的耗时与物化量 | 有量级提速才继续 |
| **P3** | 补齐其余算子,整条推理跑通 | 门 2 |
| **P4** | 97 帧端到端 + 官方融合 + 肉眼 | 门 3 |
| **P5** | 真机(A16)打点:延迟 + 峰值内存 vs 1.5GB 预算 | 出货判据 |

**P1+P2 是最小可证伪单元** —— 如果融合 kernel 在 M3 上拿不到量级提速,
整个项目的经济性就不成立,应当场停,而不是把 20 个 kernel 都写完再发现。

---

## 6. 立项时的既有基线(一切改动对它比)

```
768×576(4:3)· num_view=10 · casdiffmvs_C_long_ep31.ckpt
官方 filter.py 融合(photo [0.3,0.5,0.5] · geo_mask≥3 · geo_pixel 1.0 · 深度平均)
⇒ 22,198,291 点 · <1% 49.75% · 误差中位 0.80cm · 零视图认同 23.80%
⇒ M3/MPS PyTorch:374.3 ms/帧;叠加特征缓存+3D→2D 融合后 311.6 ms(−16.8%,数值等价)
```

深度图裁判存在 `_host_experiments/phone_cap_20260811/bench_baseline/OFFICIAL/`。
