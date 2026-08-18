# A4 端上打点:iOS / Android 共用一份 bench

⚠️ **本目录的代码未经真机运行验证**(2026-08-18 写就时手头无 Android 设备,
iOS 侧 ORT 构建亦未完成)。任何"跑通"的结论必须以真机输出为准。

## 为什么这样设计

| 决定 | 理由 |
|---|---|
| **一份 `bench_main.cc` 两端共用** | 只有取峰值内存那一个函数按平台分支。同一把尺子量两端,数字才可比 |
| **原生可执行,不做 APK / 完整 App** | bench 只回答"多快、多大",不需要 Activity/权限;也**不碰产品 app 与采集数据** |
| **输入预先打包进二进制** | 端上不依赖设备上任何采集数据,自给自足 |
| **参考深度也打进包里** | 端上直接对拍,不用把大数组回传主机 |

## 三个必须同时看的数字

| 指标 | 口径 | 为什么 |
|---|---|---|
| 峰值内存 | iOS `phys_footprint` / Android `VmHWM` | 🔑 **iOS 的 jetsam 判定用 phys_footprint,不是 resident_size**。20ms 采样取峰 —— 采样太疏会漏掉帧内峰值 |
| 稳态延迟 | 中位数,**丢弃首帧** | 首帧含 shader 编译与预热 |
| 数值一致性 | 与打包的 host 参考逐像素比 | 🔴 **必须验** —— 08-18 已吃过一次亏:WebGPU 不报错、速度正常、结果全 NaN |

⚠️ Android 的 LMKD 判定与 iOS jetsam **不是同一口径**,`VmHWM` 只作可比的上界。

## 🔴 必须设的一件事

```cpp
so.SetGraphOptimizationLevel(ORT_ENABLE_BASIC);
```
`ORT_ENABLE_EXTENDED` 及以上会让 WebGPU EP **静默**产生非有限值
(已上报 https://github.com/microsoft/onnxruntime/issues/32145)。不设它就是在量 NaN。

## 用法

```bash
# 1. 打包输入(主机上)
python3 pack_inputs.py --fixture .../fx_official \
    --ref .../bench_baseline/EXTNF --out inputs8.bin --frames 8

# 2. Android
export ANDROID_NDK_HOME=~/Library/Android/sdk/ndk/<ver>
MODEL=.../casdiffmvs_v5.onnx INPUTS=inputs8.bin ./build_android.sh

# 3. iOS —— 需先解决 #32147 的 ARC 阻断(补丁见 ../ort_issue/)
#    打包脚本复用 apde_wgsl_port_2026-08-14/tools/build_ios_bench.sh 的模式
#    🔴 .app 必须打在 /private/tmp:File Provider 卷会自动打 com.apple.FinderInfo
#       导致 codesign 拒签,且 xattr -c 清掉会立刻回来
```

## 输入包格式(`PWMVSB02`)

v01 曾把每帧 10 个视图各存一份 f32 三通道 ⇒ 8 帧 **443 MB**,推不进设备。
病根两个:灰度被复制成 3 通道存了;相邻帧共用大量视图却各存一份。
v02 改成"唯一图 fp16 灰度存一次 + 每帧只存索引" ⇒ **41.6 MB(降 10.7×)**,
26 张唯一图而非 80 个视图副本。

## 判据

```
预算       1500 MB
对照       07-31 的 A16 CoreML 实测:896×512 = 710 ms / 485 MB
           峰值经验式 ≈ 87MB + 870MB/Mpx(CoreML 口径,ORT-WebGPU 未必适用)
host 参考  ORT-WebGPU on Mac/Metal:538 ms/帧,相对差 p50 2.5e-7
```

## 已知未解

- iOS:ORT 构建卡在 #32147(补丁已验证有效,但完整构建未跑完)
- iOS:静态库能否链进手搓 `.app` / Dawn Metal 后端能否在真机起来 / iOS 的
  `maxStorageBuffersPerShaderStage` 是否比 Mac 更紧 —— **三条都没验过**
- Android:无设备,全链路未验
