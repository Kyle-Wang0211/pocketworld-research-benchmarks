# SPEED 战:LAPACK 收尾 A/B + colorize 并行核实(2026-07-18 深夜)

## colorize 并行:已在生产,无需任何动作

核实(pocketworld@ar-capture-rs):`lib/capture/colorize_pipeline.dart` 已实现**有界并行解码(窗口 3)+jpegPath 去重+单 consumer 严格顺序归约**,文件头含逐位一致论证与对拍脚本(tool/colorize_parallel_check.dart);live(ar_capture_page:1303)与冷恢复(sfm_resume:363)双路接线;iOS `colorizeQueue` = `.concurrent`(AetherARKitPlugin.swift:416)。提交 76ed9d4"colorize 并行化+提速集成"。**用户 07-18"直接进生产"的裁决=早已兑现**;设备实测收益下次装机会话读遥测(decodeMs/uniqueDecodes)。

## LAPACK 收尾 A/B(同 session E/L 交替 ×3,墙钟可信口径)

exe=2e03c66b(homebrew libceres 自带 Accelerate,**无需重编**,AETHER_DENSE_LAPACK 运行时开关直接可用;此前"exe 没链 Accelerate"判断错误——Accelerate 链在 dylib 里)。

| cap(帧数) | E(Eigen)finalize | L(LAPACK)finalize | 判 |
|---|---|---|---|
| cap51(105) | 14.7/20.4/20.4s | 15.7/19.8/19.8s | 噪声内(±0.6s) |
| cap50(139) | 32.1/31.5/31.5s | **30.0/30.0/30.2s** | **-1.3~-2.1s(≈-4.6%),三跑一致** |

- **产物无损 ✓**:点数差 0-5(run-to-run 线程噪声同级),ghost/厚度/覆盖全在臂内涨落带内(ab_rulers.json;注:本表 cover/thick 用本实验自用尺,与 f_rulers 银行表不可横比,A/B 内部有效)。
- **路由源码的阈值设计被证实**:kAetherDenseLapackMinImagesDefault=180,"≤200 帧无增益"基本成立(139 帧已见 ~5% 小增益,105 帧无);-65% 锚=~400 相机大场景,当前拍摄规模不适用。
- **iOS 落地路径**:host 是 homebrew ceres 白嫖;设备端 vendored ceres 须按 LAPACK 定案记忆的两行 CMake 补丁重编(设备批),运行时路由(≥180 帧自动开)已在库,小场景零风险。

## 复现

run_ab.sh(SHA 断言+交替对照)/ rulers_ab.py(backend 读回断言)/ ab_rulers.json / ab.log / smoke_cap51_L(冒烟:dense_backend=LAPACK 实证)。
