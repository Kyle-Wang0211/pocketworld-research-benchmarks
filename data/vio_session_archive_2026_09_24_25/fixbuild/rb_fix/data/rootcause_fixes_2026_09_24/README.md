# 2026-09-24 设备位姿闸 6 场触发的四项根因修复(fixA–fixD)+ step2 余项

来源:Claude 会话 `2359d42b` 的 scratchpad(`fixA/ fixB/ fixC/ fixD/ step2/`),本地删除前归档。
四项都**只是补丁 + 离线 / 台架证据**:没有提交到 pocketworld / Aether3D,没有上生产包。

前序归档:分支 `data/sfm-device-align-20260924` @ `7b1f8a0`(step1 90 场 + step2 补丁 B/C 与结果;**未合 main**)。
本目录 `step2_remainder/` 只放 7b1f8a0 与 `data/vio-session-archive-20260923` 里都还没有的 step2 文件(按 git blob 哈希逐个比对)。

背景(详见 7b1f8a0 的 README):核末尾的设备位姿 Sim3 对齐闸(σ = 4 cm)在 step1 的 90 场里触发 6 场。
逐场裁决:2 场是**我们喂错了设备位姿**(ARKit 自己标了 `limited_initializing` 仍照喂;补拍把两段 ARKit 会话混在一起喂),
其余是 **SfM 核按设备位姿直接放帧、绕过上游 `RegisterNextImage` 证据门**;其中 `cap_1788795741337526` 追到手机端 GPU 特征提取异常。
四项修复一一对应:A 不喂未就绪位姿,B 不混会话,C 核内证据门,D GPU 模糊派发截断。

设备对齐状态码(step2 补丁 B 头文件):`1` aligned,`2` aligned_gate_tripped(至少一帧超出 chi2(3) 95% 半径),`3` failed_insufficient_pairs,`4` failed_ransac。

## 补丁与各自的基线

| 修复 | 补丁文件 | 打在哪 | 核对方式 |
|---|---|---|---|
| A | `fixA_device_pose_trust/patch_A_device_pose_trusted.diff`(9 个文件,含 2 个新文件) | pocketworld `pw-dense-stage` `1a43510` | 补丁里每个 pre-image blob 都等于 `1a43510` 的对应文件 |
| B(交付版) | `fixB_device_session/patch_fixB_device_session_onA_v1.diff`(8 个文件) | `1a43510` **先打 A 再打 B** | 其 pre-image 等于 A 的 post-image(`device_pose_trust.dart` 46afe4b、`official_highres_reconstruction_input.dart` f08a328、`sfm_live_recon.dart` 40352b7),其余等于 `1a43510` |
| B(独立版) | `fixB_device_session/patch_fixB_device_session_v1.diff` | 直接打 `1a43510`;与 A 互斥 | pre-image 等于 `1a43510` |
| C 核 | `fixC_core_reg_evidence/patch_C_core_reg_evidence_on_B_v1.diff` | Aether3D `7dc00642` + step2 的 `patch_B_device_align_v1.diff`(在 `7b1f8a0` 的 `step2_patches_and_results/`;这是**核侧 device-align 补丁 B,不是 fixB**) | diff 是 `step2/src` → `fixC/src`;`src_revisions/` 记着 `7dc00642` / `4e22ee7` |
| C 产品侧 | `fixC_core_reg_evidence/patch_C_pocketworld_side_v2_abi.diff` | pocketworld `vendor/official_sfm/`(`1a43510`,与 `4e22ee7` 逐文件相同):头文件 + ABI 符号表 + export shim | orig 副本 10 个文件 blob 全等于 `1a43510` |
| C 台架 | `fixC_core_reg_evidence/patch_C_host_driver.diff`(改后全文 `driver/pwofficial_pose_ab_driver.cc`) | step2 的台架驱动(7b1f8a0 `step2_patches_and_results/driver/`) | |
| D | `fixD_gpu_blur_truncation/patch/fixD_gss_2pass_default.diff` | Aether3D `aede0a2e`,`aether_cpp/tools/sift_pyramid_dawn.cc` | 改前文件 blob `e9758e00` = `aede0a2e` 该文件 |
| D(出货源) | `fixD_gpu_blur_truncation/patch/fixD_gss_2pass_default_568f53d3.diff` | 出货源码 `568f53d3`,同一文件 | 改前文件 blob `6da47994` = `568f53d3` 该文件 |

C 的两个臂默认都关:臂 a `OFFICIAL_AETHER_REG_EVIDENCE=1`(上游证据门),臂 b `OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1`(走 resume 路径重跑 finalize)。
D 改完后默认两遍可分离模糊;融合版要 `OFFICIAL_AETHER_GSS_FUSED=1` 才开。

## fixA —— 设备位姿可信位(`fixA_device_pose_trust/`)

- **根因**:追踪状态在喂核前丢失,ARKit 自标 `limited_initializing` 的帧照样按设备位姿喂核;自动快门的追踪闸在 limited 时也失效(补丁头注释与 `device_pose_trust.dart` 写明)。
- **修法**:每个喂入帧带 `devicePoseTrusted`(只有 `normal` 可信,状态缺失按不可信);新 FFI `pwofficial_add_jpeg_frame_v2`(v1 参数 + `pose_t` 后一个 `int32 device_pose_trusted`),框架里没有 v2 符号时回退 v1 并记录 `devicePoseTrustHonored=false`。
- **离线证据**(`offline/`,用的是核自己的 `device_pose_alignment_v1.h` 编的 `device_align_offline`;汇总见 `offline/results/phone_gate_state_summary.txt`,归档时从 `phone_gate_state.json` 重印,没有重跑核):
  - 90 场,σ = 4 cm:`all` 臂 6 场触发 → `trusted` 臂 5 场。只剔了 3 场里的 5 帧(共 4499 对)。
  - 唯一被消掉的是 `cap_1787733401226757`(剔帧 1–3):最大中心误差 382.3 → 59.4 mm;对「最后一个不可信帧之后的帧」做 Umeyama 参考,尺度偏差 −3.18% → −1.93%。
  - `cap_1789119308200005`(混会话那场)剔 1 帧后仍然触发(362.2 → 361.9 mm)⇒ 这场要靠 fixB。
- 测试日志 `test_logs/`:补丁后 `flutter test` 有 5 条失败(`test_patched.txt` 末尾)。其中 4 条在 fixB 未打补丁的基线里也失败(`fixB_device_session/results/fail_base.txt`);`global_ptol_benchmark_contract_test` 的 setUpAll 失败在那份基线里没有对照。`analyze_patched.txt` 里只有 warning。
- `research/`:只归档了自己写的抽取脚本;抓下来的 Apple / ARCore / 华为 / OpenXR 文档和第三方源码没有入库,清单(大小 + sha256 前缀)见 `research/SOURCES_NOT_ARCHIVED.txt`。

## fixB —— 设备跟踪会话切分(`fixB_device_session/`)

- **根因**:孤儿采集恢复 / 补拍 / 整项目重喂把重启前旧 ARKit 会话的照片带着旧世界系外参重新喂进来,一个模型里混了两个世界系(补丁注释 `[DEVICE-SESSION 2026-09-24]`)。
- **修法**:Dart 侧给每张照片记 `deviceSessionId`;只有参考会话的帧 `devicePoseTrusted=true`,其余按不可信走 fixA 的通道;续跑必须把喂帧时的信任位原样读回。核不需要知道会话 id。
- **离线证据**(`results/offline_cap0005_final.json`,`cap_1789119308200005`,σ = 4 cm):
  - 改前(手机交付位姿,23 对):`aligned_gate_tripped`,17/23 内点,中心误差中位 / 最大 11.8 / 362.2 mm。
  - A+B(legacy planner,14 对):闸通过,14/14,5.4 / 9.0 mm;A+B(recorded epoch,14 对):5.3 / 7.2 mm。
  - 同一场改前在 σ = 1 m 下闸**不报**(23/23 aligned,最大 255.6 mm)。
  - `cap_1787733401226757`:`results/cap6757_tracker.json` 把帧 0 切成独立会话,参考会话 19 张,可信 19/20。
- **普遍程度**:`results/scan_sessions.txt`:106 场去重里确定跨会话 4 场(step1 90 场里 2 场);`results/within_run_breaks.json`:14 个拍摄窗口在拍摄中途发生追踪中断(`scan_tracking_breaks.json` 一共扫了 112 个窗口)。
- 测试日志:`results/final_AB.txt`、`final_standalone.txt`(各 3 条失败,和基线失败同名);草稿测试 `test_scratch/`。

## fixC —— 核内图像证据注册(`fixC_core_reg_evidence/`)

- **根因**:核把每帧直接按设备位姿放进模型(拍摄中、finalize、resume 都是这样),上游 `IncrementalMapper::RegisterNextImage` 的证据门(P3P RANSAC + 精化)从未走过;之后没有位姿先验的 BA 把证据不足的帧推远。
- **修法**:`aether_sfm_add_frame_v2` / `pwofficial_add_frame_v2` / `pwofficial_add_jpeg_frame_v2`;不可信帧不再按设备位姿放、不做 Sim3 配对、不当重力 / 位姿先验,只按上游无先验图像注册(拍摄中、finalize、resume 都重试),证据不够就保持未注册;信任位存在位姿库原保留字的 bit0,resume 同样执行。统计接口 `aether_sfm_registration_evidence_stats_v1`。
- **结果**:`results/summary_final.json` / `summary_table.md`。表格列(见 `tools/summarize.py`):subject | arm | 注册/喂入 [未注册帧] | 点数 | 重投影 px | 闸状态 内点/配对 | 尺度 | 错放帧(>112 mm) | 中心误差 中位/最大 mm | 两视图方向错 / 配对 | 点云→参考 中位 mm / >2 cm 占比 | 每 ARKit 米的交付单位 | live 末错放 | 流式 s + finalize s。
  - `cap_1786199789306631`(手机特征回放):base 189/190,错放 [110, 111, 154],最大 318.8 mm;**臂 a** 182/190(未注册 8 帧,base 本来就有 1 帧),无错放,最大 54.7 mm;**臂 b** 189/190,帧 111 仍错放,最大 118.8 mm。
  - 臂 a 在另两场也弃帧:`cap_1784820775062947` 45/50(base 49/50),`cap_1788795741337526` 19/20(base 20/20)。
  - 契约 + A + B(不可信帧走图像注册):`cap_1789119308200005` 的 uB2 各臂(帧 0–8 不可信)在 JPEG / 手机特征 / RESUME 下闸全通过,14/14,最大 6.4–6.9 mm(base JPEG 是 2 号状态);`cap_1787733401226757` 的 u03 各臂(帧 0–3 不可信)16/16,最大 9.6–10.6 mm(base 最大 382 mm)。不可信帧全部靠图像证据注册上,未注册 0。
  - Mac 录制 XRSLAM(`S_*_Xhost`)各臂交付单位 / ARKit 米 = 1.0638–1.0672,三臂一致(`summary_table.md`)。
- lepton:用产品自带的 Lepton 0.5.8 静态库在 Mac 上解码(`lepton/lep_decode.c`,调用 App 同一入口);`lepton/retag_macho_ios_to_macos.py` 只改 Mach-O 平台加载命令,机器码不动。解码出来的照片没有归档。
- `base_sfmB_inputs/`:COLMAP 4.1.1 参考位姿 / 点(`fixC/base_sfmB/inputs` 里唯一没有归档过的两个文件)。`inputs/`:本次各臂的喂帧 jsonl(只有位姿和内参,没有图像)。

## fixD —— GPU 高斯模糊派发静默截断(`fixD_gpu_blur_truncation/`)

- **根因**(补丁头注释):真机 `cap_1788795741337526` 第 5 帧 octave 0 的三次融合 H+V 模糊派发(s = 2, 3, 4;每个 workgroup 自上而下扫满 3024 行)只有前约 144/504 条带写出结果,其余保持 0,全程没有报错(Dawn Metal 后端 `QueueMTL.mm:236` 的完成回调不看 `MTLCommandBuffer` 状态)。同一命令缓冲里的两遍派发是完好的。宿主上两条路径输出的关键点集合相同(差 0–1 个点,是融合版自身原子序抖动)。
- **修法**:默认改回两遍可分离卷积,即上游 VLFeat `_vl_scalespace_fill_octave` → `vl_imsmooth_f` 的结构。
- **回放**(出货核 + 出货 GPU 提取器在宿主 Dawn/Metal 上跑,`tools/run_replays.sh`;`runs/*/eval.json`,20 帧全注册):
  - `G_fused`:第 5 帧误差 5.6 mm,第 5 帧 ≥15 内点的验证配对 14 对,最大内点 413。
  - `G_2pass`:5.1 mm,14 对,413。
  - `G_faultf5`(融合版默认路径上,把第 5 帧 octave 0 第 2/3/4 层 x ≥ 1152 清零,`FI_SPEC` 见 `tools/run_replays.sh`,注入代码在 `gpufi/`):24.7 mm,2 对,最大内点 25 —— 复现了真机症状。
- **普遍程度**(归档时从 `out/` 数出来):`out/gvp90.txt` 1664 帧「手机 GPU vs 宿主 GPU」关键点一致率低于 0.8 的只有 3 帧(`cap_1788795741337526:5`、`:6`、`cap_1788250111167292:7`);`out/coarsecut.jsonl` 2673 帧(59 场)里找到截断列 `cut_x` 的 3 帧,只有 `cap_1788795741337526` 帧 5 的 `fine_after_cut` 明显(0.125),另两帧(`cap_1786071183652291` 帧 177、`cap_1788234800013456` 帧 1)分别只有 0.002 / 0.007。
- 对比图:`out/f5_phone_vs_cpu.jpg`、`f5_seam_crop.jpg`、`f4_f5_f6_kps.jpg`(关键点叠加图)。
- `gpufi/`:只归档故障注入那一个文件和它相对 `568f53d3` 的 diff;原来 `gpufi/aether_cpp` 其余 247 个文件跟本地 `gpu568/` 副本逐字节相同(`gpu568` 里这个文件的 blob = `568f53d3`)。

## step2 余项(`step2_remainder/`)

- `base_sfmB/inputs/`:17 个喂帧 jsonl + `prep_report.json`;`base_sfmB/tools/prep_inputs.py`;`base_sfmB/runs/takeover_render_*.png`(4 张接管对比渲染图)。
- `c_patch/c_patch_a_to_b.diff`:step2 `c_patch/a → b`(退役 Dart SCALE-ANCHOR)。`a/` 的 6 个文件 blob 全等于 pocketworld `1a43510`(`a_blob_hashes.txt`),所以这个 diff 能精确还原 `b/`;它与已归档的 `patch_C_retire_dart_scale_anchor.diff` 只差 diff 上下文里的一行空行。
- `device_pose_alignment_v1.h.sigma040.bak`(σ = 4 cm 版头文件)、`pick.txt`。
- step2 其余文件都已经在 `7b1f8a0` 或 `data/vio-session-archive-20260923` 里(blob 哈希相同);`proto/` 下没归档的只有 `*.bin`。

## 待用户拍板(出自各 agent 的完成报告;这里只列事项,不加新数)

- 全部:这些只是补丁,不提交、不上生产;上生产需要用户明说。**A+B 必须和 C 的核一起上**:核里没有 v2 符号时 A 回退 v1,会把不可信帧照旧按设备位姿放 —— 要么同批上,要么把回退改成不喂。
- A:非 `normal` 时手动快门是否像 Apple Object Capture 样例那样直接隐藏(UX);XRSLAM 的「收敛 / 跟丢」没有官方信号,阈值要先上台架实测,再由用户签字。
- C:臂 a 会弃帧(上面三场臂 a 未注册分别为 8/190、5/50、1/20,base 为 1/190、1/50、0/20),跟「拍多少注册多少」冲突 —— 开 a、开 b 还是都不开;要上台架测手机耗时、XRSLAM 尺度、弃帧率,以及真机上甩飞能不能复现。
- D:① 分组截断之后又按 `out_cap` 硬截(COLMAP 保留整组);② GPU 失败时 CPU 回退的参数和 GPU 不一致;台架还要测:融合版在高温 + 匹配器并发下的截断率、两遍版必须 0 截断、两遍版耗时、Android / 鸿蒙 Vulkan 用同一内核的情况。

## 没有归档的东西

重的、能重新生成的中间产物的去处和重建方法见 `artifacts/local_heavy_artifacts.md`「Root-cause fixes 2026-09-24」一节。
