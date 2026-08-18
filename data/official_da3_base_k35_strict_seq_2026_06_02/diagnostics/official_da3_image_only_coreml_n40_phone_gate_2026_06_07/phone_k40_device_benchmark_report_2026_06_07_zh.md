# DA3-BASE K40/20 手机单 window benchmark

日期：2026-06-07

设备：Kyle's iPhone，iPhone 14 Pro，iOS 26.3.1

测试范围：只跑一个 `K40@280x504` DA3-BASE image-only CoreML window。40 帧复用同一个零 CHW float32 tensor。这个测试只回答“手机能不能承受 K40 单 window 的模型加载和推理”，不代表真实照片质量，也不包含 Sim3、loop、fusion。

CoreML computeUnits：`cpuOnly`

结果：通过。

关键数字：

- 模型加载：9307.6 ms
- 单 window 推理：18452.3 ms
- 峰值 RSS 近似：2191.4 MB
- 设备物理内存：5662.1 MB
- 推理后 jetsam available：3692.4 MB
- thermal：nominal
- low power mode：false

结论：

手机没有 OOM，没有 jetsam，K40 单 window 不能因为内存直接否决。速度上，CPU-only 单 window 约 18.45 秒，后续如果要跑完整 K40/20，需要单独评估真实图片预处理、window 数量、alignment、loop/fusion 的总耗时。

下一步 gate：

先跑真实 40 帧预处理 tensor 的手机 Stage 1，再决定是否进入全 capture 的 K40/20。
