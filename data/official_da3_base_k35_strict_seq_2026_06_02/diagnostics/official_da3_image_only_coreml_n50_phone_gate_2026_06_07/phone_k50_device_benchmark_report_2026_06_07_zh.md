# DA3-BASE K50 手机单 window benchmark

日期：2026-06-07

设备：Kyle's iPhone，iPhone 14 Pro，iOS 26.3.1

测试范围：只跑一个 `K50@280x504` DA3-BASE image-only CoreML window。50 帧复用同一个零 CHW float32 tensor。这个测试只回答“手机能不能承受 K50 单 window 的模型加载和推理”，不代表真实照片质量，也不包含 Sim3、loop、fusion。

CoreML computeUnits：`cpuOnly`

结果：通过。

关键数字：

- 模型加载：11163.4 ms
- 单 window 推理：31120.3 ms
- 峰值 RSS 近似：637.7 MB
- 设备物理内存：5662.1 MB
- 推理后 jetsam available：3642.1 MB
- thermal：nominal -> fair
- low power mode：false

结论：

手机没有 OOM，没有 jetsam，K50 单 window 不能因为内存直接否决。但速度已经明显慢：CPU-only 单 window 约 31.12 秒，并且热状态从 nominal 升到 fair。

下一步 gate：

不要直接跳全序列 K50。先用真实图片跑 Stage 1 的 K40 vs K50，对比深度/置信度/pose 质量提升是否值得 31 秒单 window 和热压力。
