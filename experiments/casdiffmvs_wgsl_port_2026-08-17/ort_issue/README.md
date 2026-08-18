# ORT WebGPU EP:EXTENDED 级图优化产生非有限值

## 材料
- `model.onnx`(84 KB,8 个节点:Split / Conv×3 / Relu×2 / Tanh / Constant)
- `input.npz`(一个 `(1,36,288,384)` float32 张量)
- `repro.py`(单文件,无外部依赖)

## 现象
```
graph_optimization_level    非有限%   与 CPU 最大差
ORT_DISABLE_ALL              0.000%      2.695e-06   ✅
ORT_ENABLE_BASIC             0.000%      2.695e-06   ✅
ORT_ENABLE_EXTENDED          0.414%      1.000e+00   🔴
ORT_ENABLE_ALL(默认)        0.414%      1.000e+00   🔴
```
最大差恰为 1.000 = `tanh` 的饱和值 ⇒ 进 `tanh` 前已是 ±Inf。

## 环境
ORT v1.29.0 源码构建(`--use_webgpu`),macOS 26 / Apple M3 Pro / Metal。

## 定位过程中被证伪的三个假设(供参考,避免重复排查)
1. **通道数非 2 的幂**(hidden_dim=20)—— 否。随机权重下 20 通道链完全正常。
2. **分辨率相关** —— 否。同链在 144×192 与 288×384 上随机权重均正常。
3. **BatchNorm 方差过小致放大** —— 否。`running_var` 最小 4.07,`1/sqrt(var+eps)` 最大仅 0.50。

**真正的判据是图结构而非数值**:把中间量暴露成图输出后(阻止融合),bug 消失;
只有 EXTENDED 及以上才复现 ⇒ 指向 Conv+BN / Conv+Activation 融合后的 kernel。

⚠️ 需真实权重 + 真实输入同时具备才触发(2×2 隔离:真权重+随机输入 ✅,
随机权重+真输入 ✅,随机+随机 ✅,真+真 🔴)⇒ 与融合后常量的具体数值有关。

## 绕行
`sess_options.graph_optimization_level = ORT_ENABLE_BASIC`
—— 实测整模型(97 帧)恢复正常,相对差 p50 2.5e-7。
