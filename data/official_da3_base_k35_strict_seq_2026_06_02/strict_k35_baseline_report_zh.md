# DA3-BASE K35 strict sequential baseline 诊断报告

日期：2026-06-02

## 1. 真实采集顺序依据

使用 `photo_bundle.json` 的 `frames[].timestamp` 升序作为真实采集顺序；同 timestamp 的 tie-break 是原始 manifest index。没有按字符串文件名排序，没有 graph patch，没有智能选帧。

自检结果：

- frame count: 414
- first frame: `cap-1`, timestamp `1339396.229695`
- last frame: `cap-2219`, timestamp `1339766.020314`
- timestamp monotonic: `true`
- strict capture: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict`

## 2. Strict windows 明细

固定 K=35，overlap=18，step=17。

`window_000` = index 0-34:

`cap-1, cap-3, cap-5, cap-7, cap-21, cap-23, cap-29, cap-31, cap-33, cap-35, cap-37, cap-39, cap-42, cap-44, cap-48, cap-50, cap-52, cap-54, cap-56, cap-74, cap-78, cap-80, cap-96, cap-103, cap-105, cap-107, cap-109, cap-114, cap-116, cap-118, cap-122, cap-124, cap-126, cap-128, cap-131`

`window_001` = index 17-51:

`cap-54, cap-56, cap-74, cap-78, cap-80, cap-96, cap-103, cap-105, cap-107, cap-109, cap-114, cap-116, cap-118, cap-122, cap-124, cap-126, cap-128, cap-131, cap-136, cap-138, cap-140, cap-142, cap-144, cap-148, cap-167, cap-190, cap-192, cap-194, cap-196, cap-198, cap-205, cap-207, cap-210, cap-214, cap-212`

`window_002` = index 34-68:

`cap-131, cap-136, cap-138, cap-140, cap-142, cap-144, cap-148, cap-167, cap-190, cap-192, cap-194, cap-196, cap-198, cap-205, cap-207, cap-210, cap-214, cap-212, cap-216, cap-220, cap-222, cap-224, cap-227, cap-230, cap-235, cap-257, cap-260, cap-263, cap-272, cap-274, cap-280, cap-288, cap-291, cap-296, cap-310`

## 3. CoreML strict 输出

CoreML `--compute-unit all` 在 model load 阶段无 traceback 退出，只留下 `model_load_start` 日志；已保留失败目录：

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict_all_failed`

CoreML CPU 成功跑完前 3 个 strict windows，并移动到标准输出路径：

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_strict`

运行结果：

- window count: 3
- selected unique frames: 69
- model load: 3.297s
- predict: window_000 52.676s, window_001 52.925s, window_002 53.511s

## 4. 单窗点云与 PNG 对照

Strict CoreML `window_000`:

- PLY: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/strict_window_000_coreml/strict_window_000_single_rgb.ply`
- views PNG: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/strict_window_000_coreml/strict_window_000_single_views.png`
- report: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/strict_window_000_coreml/strict_window_000_single_report.json`

旧 graph-patch `window_000` 对照：

- PLY: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/window_000_single_rgb.ply`
- views PNG: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_streaming_2026_05_30/diagnostics/alignment_debug_2026_06_01/window_000_single_views.png`

拼图对照：

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/strict_window_000_coreml/strict_vs_graph_patch_window_000_views.png`

肉眼观察：strict 单窗仍有 DA3 raw depth 的厚度/噪点，但比旧 graph-patch 单窗明显更收敛；旧图更像多视角散成一团。

## 5. PyTorch vs CoreML 输出

同一组 strict `window_000` 35 张图的官方 PyTorch manifest:

`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/strict_window_000_official_manifest.json`

官方 PyTorch K35@742 MPS 尝试失败：

- output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/official_pytorch_k35_742/official_da3_stage_summary.json`
- error: `Invalid buffer size: 89.01 GiB`
- preprocess shape 已确认：`35 x 3 x 476 x 742`

官方 PyTorch K35@476 MPS 尝试失败：

- output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/official_pytorch_k35_476/official_da3_stage_summary.json`
- error: `Invalid buffer size: 15.36 GiB`
- preprocess shape：`35 x 3 x 308 x 476`

官方 PyTorch K35@252 MPS 成功，仅作为 API/契约定位，不作为最终质量对照：

- summary: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/official_pytorch_k35_252/official_da3_stage_summary.json`
- export report: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/official_pytorch_k35_252_export/official_pytorch_window_000_export_report.json`
- PLY: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/official_pytorch_k35_252_export/official_pytorch_k35_process_res_252_single_rgb.ply`
- views PNG: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/official_pytorch_k35_252_export/official_pytorch_k35_process_res_252_single_views.png`
- CoreML/PyTorch 拼图: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/pytorch_vs_coreml_window_000/pytorch252_vs_coreml_strict_window_000_views.png`

## 6. 关键数值

| 项目 | 点数 | bbox diag p01-p99 | depth min/max/mean | pose/scale |
|---|---:|---:|---|---|
| strict CoreML window_000 | 52,562 sampled / 8,763,341 valid | 1.4009 | 0.262 / 1.381 / 0.760 | camera center diag 0.6625 |
| old graph-patch window_000 | 43,353 sampled / 7,228,561 valid | 2.1332 | 旧报告未导出 depth 统计 | - |
| official PyTorch K35@252 | 5,886 sampled / 983,967 valid | 2.7705 | 0.637 / 8.710 / 1.680 | Umeyama scale 0.5810, camera center diag 1.4307 |

CoreML strict `window_000` 其他统计：

- confidence min/max/mean: 1.000 / 12.625 / 3.698
- predicted fx mean: 545.714
- predicted fy mean: 537.500

PyTorch K35@252 其他统计：

- processed shape: `35 x 168 x 252 x 3`
- confidence min/max/mean: 1.000 / 5.872 / 2.295
- predicted fx mean: 168.436
- predicted fy mean: 199.628

Strict `window_000 -> window_001` bridge:

- report: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/strict_window_000_001_bridge/strict_window_000_001_bridge_report.json`
- shared frames: 18
- residual point count: 6,357,456
- RMSE: 0.0529
- median: 0.0270
- P90: 0.0888
- P95: 0.1224
- Sim3 scale: 0.8906

旧 graph-patch 第一桥对照：

- RMSE: 0.0759
- P90: 0.1073

## 7. 最终判断

当前结果最像：旧 graph patch / window 选择方式破坏了 DA3 streaming 的连续局部输入假设。

依据：

- strict sequential 单窗 bbox diag 从旧 graph-patch 的 2.1332 降到 1.4009，PNG 肉眼也更收敛。
- strict 第一桥 residual RMSE/P90 为 0.0529/0.0888，优于旧 graph-patch 第一桥 0.0759/0.1073；第一跳 bridge 不是当前最像的爆点。
- strict CoreML 单窗仍有 raw depth 厚度和散点，所以不能把它当最终点云审美结论；但它已经明显优于旧 graph-patch 单窗。
- PyTorch K35@742 和 K35@476 在本机 MPS 前向阶段因 buffer 过大失败，因此不能完成严格 PyTorch@742 vs CoreML@742 质量 parity 结论。K35@252 成功只说明官方 PyTorch API 和同 35 帧 manifest/pose/intrinsics 路径能跑通，不能直接判定 CoreML 契约正确或错误。

所以优先级排序：

1. window 组织方式：最可疑，且本次证据支持。
2. CoreML 契约：仍需后续高分辨率 PyTorch parity 或更小 batch 官方路径验证，当前不能排除，但不是本轮首要证据。
3. 素材局部/DA3 raw depth 厚度：存在，但 strict 改善明显，暂不作为主因。
4. 跨 window bridge：至少 window_000 -> window_001 第一桥不像主因。

## 8. 下一步最小动作

只做一个动作：跑完整 24 个 strict sequential CoreML windows，然后做 adjacent-only incremental diagnostics（1/2/4/8/24 windows），仍然不要 graph patch、不要 loop、不要 Poisson/mesh。
