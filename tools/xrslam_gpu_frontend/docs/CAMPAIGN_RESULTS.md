# XRSLAM threading back-pressure — bench results 2026-09-03
Recording: run-6e2d4b99-896b-4372-ae47-ac0b4679cf18 (1702 frames, 1920x1440, 60 fps, IMU 100 Hz). Mode replay-device-recording, backend xrslam.
Arms: thrnogate (threading ON, accessor only) engine sha 4a9c75d1…, .a ca98a914… | thrbp (threading ON + library producer-side gate cap 2/4) engine sha 3dffda97…, .a b6167af7…
| run | arm | bench feeder gate | pacing | outcome |
|---|---|---|---|---|
| R0 run-4fcc212e | thrnogate | on (cap 2) | max | complete, 1640 poses, 34.3 fps, 0 drops, footprint ~140 MB flat, engine_backlog_peak 3 |
| R1 run-b9eca18c | thrnogate | off | max | process gone at +6 s, 0 poses, receipt state=started |
| R1p run-82b0c66e | thrnogate | off | paced 60 fps | 29→776→1463→2895 MB, jetsam at +29 s (per-process-limit, rpages 196608) |
| R2 run-d1902ae4 | thrbp | off | max | heartbeat flat ~145 MB through +50 s; **artifacts lost** (self-test purge on next launch before pull) |
| R2b run-2de39ccd | thrbp | off | max | complete, 1638 poses, 29.1 fps, 0 drops, footprint 142–146 MB flat, engine_backlog_peak **6 = 2+4 configured caps**, camera_input_capacity 0 (flag active), engine sha 3dffda97… |
| R2p run-1ffdacc4 | thrbp | off | paced 60 fps | complete, 1638 poses, 25.1 fps, drops 0, peak footprint None MB, engine_backlog_peak 6, capacity 0, engine sha 3dffda97… |

## Step 1 rerun (2026-09-03 20:48), bench with telemetry-kept-on-invalid + relative cold-start gate
| S1' run-8a4df815 | thrnogate | live-soak 120 s, 1920x1440 @30 fps camera (code: productionResolution.cameraRateHz=30), started nominal | **initialised this time** (3536 poses, first usable 2155.7 ms < ARKit ref 2874.9 ⇒ cold-start gate passes), then **unbounded growth: footprint 29→182→219→627→1866 MB, engine_backlog_peak 314**, camera 3591/3591 accepted, 0 late drops, p95 32 ms, fps 29.5, thermal nominal 33 s / fair 25 s / serious 62 s, cpu 2.2 cores. Verdict valid_fail (thermal_serious>0, footprint>750). ⇒ the "live 41 MB/s leak" of the 09-02 note is the same unbounded engine deque: it only shows once the engine is initialised and falls behind 60 fps (stationary, never-initialised runs stay flat). Library gate (thrbp) is therefore the fix for live too — to be measured next. |
| S1' run-f92cafbb | **thrbp** | live-soak 120 s, 1920x1440 @30 fps camera (code: productionResolution.cameraRateHz=30), started nominal | initialised (2077 poses, first usable 17.2 s), **footprint flat: max 229 MB, end 140 MB, engine_backlog_peak 6 (=2+4 cap)**. Cost: camera delivered only 2582 frames (21 fps) because the gate blocks the capture callback, processed 17.1 fps, p95 pipeline latency 1425 ms (max 1774), Swift handoff peak 203/264. Thermal nominal 35 / fair 25 / serious 63 s. Verdict invalid (platform_camera_loss). ⇒ gate bounds memory live too, but converts overflow into platform-level frame loss and ~1.4 s latency once the engine falls behind 60 fps under heat. |

## Step 2 (2026-09-03 22:07) — thrbp live-soak 600 s, 1920x1440 @30 fps camera, started nominal
| S2 run-0fd0093f | thrbp | 600 s | **memory holds: footprint peak 245 MB, end 141 MB, backlog peak 6 for the whole 10 min.** Thermal: serious from 54 s, all remaining 548 s serious, **never critical**; CPU ~1.9 cores. Throughput collapsed under heat: camera delivered 11 569 frames (19 fps, AVFoundation starved by the blocked delegate), 6 244 poses (10.4 fps), p95 pipeline latency 1 596 ms (max 2 310), first usable pose 194.9 s, Swift handoff peak 264/264. Verdict invalid (platform_camera_loss). |

## Step 2b (22:32) — thrbp + -PWTrackerFrequent 2, live-soak 600 s
run=run-f26fab79 engine=xrslam channel=live_soak state=invalid reason=platform_camera_loss eng_sha=4642f1c1
  metrics: {'diagnostic_elapsed_seconds': 600.73, 'diagnostic_first_usable_pose_latency_ms': 17999.02, 'diagnostic_max_pipeline_latency_ms': 1354.41, 'diagnostic_p95_pipeline_latency_ms': 787.4, 'diagnostic_pose_count': 15622, 'diagnostic_processed_fps': 26.0}
  camera off/acc=16160/16160 imu=60183 poses=15628 backlog_peak=6 drops_late=0 handoff_peak=177
  telemetry n=602 footprint MB start=29 q1max=219 q2max=235 q3max=233 end=223 max=235 thermal={'nominal': 31, 'fair': 35, 'serious': 536} cpu核当量 均值1.84 峰2.64
min thermal(占比)                    fp峰MB   cpu核   样本
  0 {'nominal': 31, 'fair': 30}      176   1.19   61
  1 {'fair': 5, 'serious': 55}       163   1.16   60
  2 {'serious': 60}                  224   1.63   60
  3 {'serious': 60}                  235   2.08   60
  4 {'serious': 60}                  233   1.97   60
  5 {'serious': 60}                  228   2.08   60
  6 {'serious': 60}                  233   2.11   60
  7 {'serious': 60}                  223   2.15   60
  8 {'serious': 60}                  224   2.06   60
  9 {'serious': 60}                  234   1.93   60
 10 {'serious': 1}                   223   1.90    1
首次 serious: 65 s | 首次 critical: None s | 总时长 600 s

freq1 vs freq2 platform drops: camera_drops_out_of_buffers 6425 -> 1840 (late 0 both); config_sha a3c841c8 -> b013907b (override landed)

## ARKit reference live-soak 600 s (run-f3d525c9, 22:57, started nominal)
run=run-f3d525c9 engine=arkit_reference channel=live_soak state=valid_pass reason=thresholds_met eng_sha=9a3aca86
  metrics: {'app_drop_rate': 0, 'arkit_reference_first_usable_pose_latency_ms': 2874.92, 'battery_level_delta': 0.05, 'cpu_seconds': 480.7, 'estimated_missed_frames': 0, 'finite_pose_ratio': 1, 'first_mapped_latency_ms': -1, 'first_normal_latency_ms': 1434.38, 'first_usable_pose_latency_ms': 1480.72, 'longest_non_normal_seconds': 0.93, 'max_frame_interval_ms': 16.67, 'measurement_duration_seconds': 600, 'p95_callback_handler_duration_ms': 0.67, 'p95_consecutive_rotation_deg': 0.03, 'p95_consecutive_translation_m': 0.0, 'p95_frame_interval_ms': 16.67, 'p95_pipeline_latency_ms': 55.53, 'peak_phys_footprint_mb': 266.31, 'processed_fps': 59.94, 'relocalization_attempts': 0, 'relocalization_recoveries': 0, 'stall_duration_ms': 0, 'stall_events_over_one_second': 0, 'thermal_critical_seconds': 0, 'thermal_serious_seconds': 0, 'tracking_normal_ratio': 1.0}
  camera off/acc=None/None imu=None poses=None backlog_peak=None drops_late=None handoff_peak=None
首次 serious: None s | 首次 critical: None s | 总时长 599 s

## Relative verdict (owner's bar: not worse than same-device ARKit, metric by metric)
### freq2 (thrbp + tracker_frequent 2) vs ARKit
候选 xrslam (run-f26fab79, invalid/platform_camera_loss, 601s) vs 参考 arkit_reference (run-f3d525c9, valid_pass/thresholds_met, 600s)
  指标                             候选      ARKit
  位姿/s                         26.0       59.9  劣于
  相机交付 fps                     26.9       59.9  劣于
  p95 延迟 ms                   787.4       55.5  劣于
  首个可用位姿 ms                   17999       1481  劣于
  footprint 峰 MB                235        266  不劣于
  serious 秒                     536          0  劣于
  critical 秒                      0          0  不劣于
  CPU 核当量                      1.84       0.80  劣于
  平台丢帧                         1840          0  劣于
  ⇒ 2/9 项不劣于 ARKit;有劣于项 ⇒ 未过
### freq1 (thrbp) vs ARKit
候选 xrslam (run-0fd0093f, invalid/platform_camera_loss, 601s) vs 参考 arkit_reference (run-f3d525c9, valid_pass/thresholds_met, 600s)
  指标                             候选      ARKit
  位姿/s                         10.4       59.9  劣于
  相机交付 fps                     19.2       59.9  劣于
  p95 延迟 ms                  1596.0       55.5  劣于
  首个可用位姿 ms                  194860       1481  劣于
  footprint 峰 MB                245        266  不劣于
  serious 秒                     548          0  劣于
  critical 秒                      0          0  不劣于
  CPU 核当量                      1.91       0.80  劣于
  平台丢帧                         6425          0  劣于
  ⇒ 2/9 项不劣于 ARKit;有劣于项 ⇒ 未过

## Lever 1 (diagnostic only — resolution is lossy, not a shipping lever): thrbp + freq2 at 640x480 live 600 s (run-1e7422d3)
Thermal: nominal for all 600 s (first time any XRSLAM arm stayed out of fair); CPU 0.52 cores (< ARKit 0.80); footprint peak 45 MB; p95 40 ms; camera 30 fps, 0 drops. But stationary initialisation took 566 s (1014 poses, 1.7 fps) and the run ended `non_finite_pose`. Relative verdict 6/9 not worse (poses/s, camera fps, first pose worse). ⇒ the thermal gap at 1920x1440 is entirely pixel count; at 640x480 the SoC never throttles.
Full-resolution replay baselines (ate.py via uv, vs ARKit trajectory): R0 Sim3 2.48 cm / scale 2.44 %; R2b 2.39 cm / 3.74 %; R2p 2.36 cm / 3.43 % (all freq 1; spread = threading non-determinism).
| S3r run-ca319492 | thrbp + freq2, replay 640x480 (-PWDiagnosticDownscale), bench feeder gate on | invalid: replay_engine_stalled_camera_queue_full_no_pose_progress at ~+20 s, 0 poses — engine produced no pose within the bench's 20 s stall window at 640x480 with freq 2 (the 09-02 session's 640 replays ran with freq 1 and no library gate). Resolution is already excluded as a lever (lossy); recorded as a data point only. |
| S4r run-… (23:34) | thrbp + freq2, replay 1920x1440, bench gate on, nominal | complete, 1640 poses, 54.9 fps replay throughput, backlog peak 3, footprint ≤158 MB. **Sim3 ATE 3.31 cm / scale 2.67 % / SE3 3.45 cm** vs freq-1 baselines Sim3 2.36–2.48 cm — scale within spread, ATE ~0.9 cm worse (outside the 0.12 cm freq-1 spread). Two more freq-2 samples queued (S4r2, S4r3). |
freq1 full-res replay baselines incl. 09-02: Sim3 ATE 2.11 (upstreamcfg 09-02), 2.36, 2.39, 2.48 (tonight), 2.54 (09-02 backpressure) cm; scale 2.4–4.1 %. freq2 first sample 3.31 cm is outside.
| S4r2 (23:37) | thrbp + freq2, replay 1920, gate on, thermal fair | 1640 poses, 51.3 fps, **Sim3 3.30 cm / scale 1.88 % / SE3 3.36 cm** |
| S4r3 (23:38) | thrbp + freq2, replay 1920, gate on | 1640 poses, **Sim3 2.87 cm / scale 2.65 % / SE3 3.03 cm** |

### Lossless-gate verdict for `sliding_window.tracker_frequent` 1 → 2 (replay 1920x1440, same recording)
freq 1 Sim3 ATE: 2.11, 2.36, 2.39, 2.48, 2.54 cm (mean 2.38) | freq 2: 3.31, 3.30, 2.87 cm (mean 3.16). Scale: freq 1 2.4–4.1 %, freq 2 1.9–2.7 % (not worse).
⇒ ATE is ~0.8 cm (+33 %) worse with no overlap between the two sets ⇒ **not lossless ⇒ rejected as a shipping lever** (it remains the best-known throughput lever: 26 vs 10 fps live under `serious`).

## 2026-09-04 gpufe arm (GPU front end: CLAHE/pyramid/Scharr/GFTT/LK on Dawn, OpenCV 4.0.1 bit-exact replicas) — first device replay
Same build (engine sha 3e3c968d, xrslam.a 7b3050ba + libpw_gpu_frontend_ios.a da4b36c0 + Debug libwebgpu_dawn), single variable = `-PWXrslamGpuFrontend`.
| run | arm | result |
|---|---|---|
| run-7c7904b2 (01:09) | gpufe build, flag off (control) | 1638 poses, 16.5 fps, cpu 1.73 cores, thermal serious throughout (phone hot), Sim3 ATE 2.38 cm / scale 4.59 % / SE3 2.92 |
| run-ddfd75ba (01:11) | flag on | prepare failed: RunReceipt.validate rejected backend "gpu_frontend" (failure.json) — gate extended, engine rebuilt (sha 3e3c968d) |
| run-c9acab1f (01:28) | flag on | **GPU path ran: stats frames 1651, fallbacks 0, healthy**; 1642 poses, **9.1 fps**, cpu **0.53 cores** (vs 1.73), thermal **nominal for all 182 samples**, footprint peak 288 MB (vs 168); Sim3 ATE **2.62 cm** / scale 1.27 % / SE3 2.66 (control 2.38 / 4.59 / 2.92; freq-1 baselines 2.11–2.54). On-device GPU stage means: preprocess 54.2 ms, detect 11.9 ms, track 18.5 ms ×2 per frame ⇒ ~100 ms/frame wall vs CPU ~28 ms. |
Reading: CPU load −69 % and no thermal rise, but wall time 3.5× worse — the first port is naive (per-frame Dawn buffer allocation, one submit per dispatch, u8→u32 expansion on the CPU, 11.6 MB CLAHE readback, one-thread-per-point LK with 5 KB private arrays). ATE 2.62 is 0.08 cm above the 5-sample baseline spread with n=1; needs ≥3 samples after the speed work (numerics are bit-exact on Mac; run-to-run spread is threading timing).

### 09-04 gpufe v2 (pooled buffers, one submit per stage, packed u8, fused fwd+rev LK, workgroup-per-point LK) — engine 1e430675
| run | arm | fps | cpu cores | thermal | Sim3 ATE / scale / SE3 | gpufe stage ms (pre/det/track fwd+rev) |
|---|---|---|---|---|---|---|
| run-ea97e68c | ctrl (flag off) | 36.0 | 2.13 | nominal | 2.27 / 3.13 % / 2.54 | — |
| run-e1edaf7a | gpu | 36.6 | 0.58 | fair | 3.13 / 2.28 % / 3.23 | 8.2 / 4.1 / 13.0 |
| run-2d1c88cc | gpu | 36.9 | 0.59 | fair | 3.21 / 1.37 % / 3.25 | 8.2 / 4.1 / 13.0 |
| run-e6b17859 | gpu | 36.8 | 0.59 | nominal | 3.20 / 1.39 % / 3.23 | 8.2 / 4.1 / 13.0 |
Systematic +0.9 cm ⇒ semantic gap found: OpenCV 4.0.1 GFTTDetector returns response = 0 for every corner (gftt.cpp:116) and XRSLAM std::sort()s by response, i.e. a deterministic permutation of the goodFeaturesToTrack order that the order-dependent PoissonDiskFilter then consumes; the GPU path had sorted by the real eig value. Fixed in GpuImage (same cv::KeyPoint sequence, same std::sort) → engine 3cedb715.
### 09-04 gpufe v3 (sort semantics replicated) — engine 3cedb715
| run | arm | fps | cpu cores | thermal | Sim3 ATE / scale / SE3 |
|---|---|---|---|---|---|
| run-04ac2fc9 | ctrl | 35.7 | 2.12 | nominal | 2.29 / 2.72 % / 2.49 |
| run-82ccb081 | gpu | 36.7 | 0.58 | nominal | 2.73 / 1.18 % / 2.76 |
| run-3fbbb5e5 | gpu | (see below) | | | |
Note: twice the bench poller reported a "stall" (+895 s / +600 s) while the run had finished in ~50 s: `devicectl device info files` listing goes stale; pw_run_arm.sh now also tries to copy diagnostics.json as a completion signal.
| run-3fbbb5e5 | gpu | 36.8 | 0.58 | nominal | 2.63 / 0.14 % / 2.63 |
| run-f2b48eb0 | gpu | 36.8 | 0.58 | nominal | 2.69 / 0.75 % / 2.71 |
### 09-04 gpufe v4 (+ on-device audit: every 50th frame the CPU path is re-run on the same inputs and compared bit-for-bit) — engine e2d92f8c
| run | arm | fps | cpu | thermal | Sim3 / scale / SE3 | audit clahe / detect / track (frames, bad) |
|---|---|---|---|---|---|---|
| run-734b33e1 | gpu | 36.1 | 0.62 | nominal | 2.21 / 3.33 % / 2.53 | 33,0 / 33,0 / **32,32** |
| run-66c5975a | gpu | 36.3 | 0.62 | nominal 37 / fair 10 | 2.23 / 2.74 % / 2.44 | 33,0 / 33,0 / **32,32** |
CLAHE and detection are bit-identical on the device; LK differs on every audited frame. The iOS OpenCV LK object is the same NEON code path as the Mac reference (otool: ld2 17 / smull 10 / sqrshl 5 / scvtf.4s 32, no fma, in both), and the Mac GPU matches that reference 150/150 — so the deviation is on the A16 GPU side (fast-math reciprocal/sqrt is the prime suspect). Next build: strict math in the library + per-point audit detail + input dump on first mismatch.
GPU-arm ATE so far (Sim3 cm): v1 2.62; v3 2.73, 2.63, 2.69; v4 2.21, 2.23 — CPU ctrl 2.38, 2.27, 2.29; freq-1 baselines 2.11–2.54.
### 09-04 02:25 gpufe live-soak 600 s (1920x1440 @30 fps, dark room, phone stationary) — engine e2d92f8c, run-9bc4704c
0 poses (never initialised), camera delivered 9.8 fps / 12 087 platform drops, footprint peak 389 MB, **thermal nominal for all 600 s, CPU 0.37 cores (ARKit ref 0.80)**; relative verdict 3/7 (memory, drops, fps worse). GPU stage means on live: preprocess 27.9 ms / detect 17.7 / track 51.1 (replay: 8.2 / 4.1 / 13.0) ⇒ ~100 ms/frame ⇒ the gate blocks the capture callback. Audit on live: CLAHE 118/118 exact, **detect 117/118 MISMATCH**, track n/a (no tracks) — the dark/noisy frames expose the one known non-exact stage (Harris 3x3 box sum in f32 vs CPU double accumulation: near-ties flip threshold/NMS). Two fallbacks.

### 09-04 morning — on-device numerics audit closes: the GPU front end is bit-exact on the iPhone 14 Pro
Engine 2347570a (run-c4387217, replay, Sim3 2.24 cm): audit every 50th frame, CPU path re-run on identical inputs —
CLAHE 33/33 exact, detection 33/33 exact (after: Sobel column fma order, exact double-emulated 3x3 box sum, zero-response sort quirk),
pyramids+Scharr 32/32 exact, LK forward+reverse 32/32 exact (0 points differ). Device fp self-check: div/int→float/round/mul/add/floor
all IEEE; raw sqrt off by 1 ulp in 29 % (replaced by integer-exact sqrt_rn/div_rn); contraction happens even in strict mode (guarded by fma(x,y,0)).
The "LK differs on device" scare (v4–v15) was an audit bug: XRSLAM passes IMU-predicted positions as the LK initial flow (frame.cpp
Frame::track_keypoints) and the CPU reference had used curr; with the real initial flow everything matches. Bisection artefacts
(one-thread-per-point kernel, CPU-pyramid upload, kernel variants) all agreed with the CPU too.
### 09-04 ~11:50 gpufe replay ×3, engine 3b3528bd (exact kernels, lightweight audit) — all audits exact
| run | fps | Sim3 / scale / SE3 |
|---|---|---|
| run-927b9099 | 27.2 | 2.18 / 3.88 % / 2.60 |
| run-86416ba5 | 25.5 | 2.44 / 4.51 % / 2.95 |
| run-47475616 | 24.8 | 2.34 / 4.23 % / 2.81 |
CPU control band 2.11–2.54 (mean 2.38); GPU arm now 2.18–2.44. Throughput dropped from ~36 fps (v3) to ~26 because the exact 3x3 box sum makes detect ~11 ms; to be optimised.

### 09-04 13:xx gpufe engine 281576c7 — packed u8 pyramid + TwoSum exact box sum + LK 64-thread workgroups with 5 accumulation threads
run-54324de3 (replay, audit CLAHE 33/33, detect 33/33, track 32/32 exact): **preprocess 7.4 / detect 5.6 / track 6.2 = 19.3 ms/frame** (was 35.8),
replay 44.7 fps (CPU arm 36), Sim3 ATE 2.40 cm / scale 3.09 % / SE3 2.65, CPU 24.5 s over 1697 frames. Lesson: on the A16 the LK cost was
serial-chain occupancy (1 active thread per 256-thread workgroup), not arithmetic; 64-thread groups + 5 chains cut 13.1 → 6.2 ms.
Also: assemble_and_build.sh had a silent pipefail exit (grep with no match under set -e) that reinstalled the OLD app twice — fixed with || true.

### 09-04 13:10 gpufe live-soak 600 s, daytime, engine 281576c7 (run-9a45bff6) — verdict 2/9, not passed
Started nominal after cool-down; 3961 poses (6.6/s), camera delivered 14.5 fps (9300 out-of-buffer drops), first usable pose 356 s,
p95 pipeline latency 1175 ms, footprint peak 350 MB (ARKit 266), thermal nominal 62 s / fair 410 / serious 131 (first serious 471 s),
CPU 0.45 cores (ARKit 0.80). GPU stages LIVE: 25.6 / 17.6 / 19.9 ms (replay same build: 7.4 / 5.6 / 6.2) — the 3x live slowdown again;
503 GPU-error fallbacks (reason not captured yet). Audits still exact (CLAHE 174/174, detect 164/164, track 173/173).
Fused-dispatch build (12→8 preprocess dispatches, detect single submission) replay run-1b55e848 right after the soak: 10.9 / 7.2 / 8.8 ms at
thermal serious throughout — not comparable (v23's 19.3 ms was also measured at serious); clean re-measure queued after cool-down,
plus diagnostics: empty-submission latency probe every 50 frames and per-1000-frame stage buckets.

### 09-04 18:44 gpufe live-soak 600 s WITH initial motion (engine 30e52761, run-173d0878) — the live slowdown is thermal throttling
First usable pose 1.87 s (ARKit ref 1.48 s), 10 838 poses (18.0/s), camera 18.1 fps, 7115 platform drops, p95 1081 ms, footprint 335 MB, thermal nominal 48 s / fair 55 s / serious 499 s (serious from 102 s), CPU 0.61 cores, 0 GPU fallbacks, audit CLAHE 217/217 detect 217/217 track 216/216 exact.
Per-1000-frame GPU stage buckets (pre/det/trk ms): nominal 10.0/6.4/7.1 = 23.5 → fair/serious 21–22/12.5/13.5 ≈ 47 → serious 26/14.8/16.3 ≈ 57. Empty-submit latency 1.04 ms. ⇒ the 2–3× "live vs replay" gap is GPU frequency throttling once the phone leaves nominal; at nominal the front end fits 30 fps.
vs CPU arm (S2): poses/s 18.0 vs 10.4, p95 1081 vs 1596, serious at 102 s vs 54 s, CPU 0.61 vs 1.9; camera fps 18.1 vs 19; footprint 335 vs 245. Relative to ARKit still 2/9.
Earlier daytime 600 s (run-9a45bff6, static phone): 503 "candidate overflow" fallbacks in dark frames — capacity raised 65536→262144 (0 fallbacks here).

### 09-04 19:12 gpufe PIPELINED live-soak 600 s (engine 13befc71, run-83f0c93e; pyramid built asynchronously on the capture thread)
11 234 poses (18.7/s), camera 19.0 fps, first pose 6.4 s, p95 977 ms, footprint 423 MB (per-frame scratch now pooled per frame), thermal nominal 87 / fair 250 / serious 265 (serious from 336 s vs 102 s before), CPU 0.50, 0 fallbacks, audit CLAHE 228/228, detect 228/228, track 227/228 (ONE mismatching frame — under investigation).
Tracker-thread stages: preprocess 2.8 ms (submit only; wait 0), detect 17.0, track 30.5 — buckets [2.6,13.0,20.4] at nominal → [2.6,17.4,31.8] under fair/serious. The tracker's detect/LK batches now queue behind the capture thread's prefetch batches (empty-submit latency 3.6 ms vs 1.0), so per-frame tracker time did not drop; net: poses/s 18.7 vs 18.0, serious delayed 102 → 336 s. Relative to ARKit still 2/9.
Replay with pipelining (run-30387ccd): 45.8 fps (vs 44.7), pre_wait 0.02 ms, detect 10.5 (queued behind prefetch), Sim3 2.25 cm.

### 09-04 19:35 gpufe pipelined, prefetch depth ≤ 1 (engine 5d6ccfe2, run-080d4034) — first 600 s live with NO serious state
10 848 poses (18.1/s), camera 18.5 fps, first pose 9.5 s, p95 977 ms, footprint 367 MB, CPU 0.50, 0 fallbacks, 7068 prefetches declined (tracker then preprocesses synchronously), audit CLAHE 222/222, detect 222/222, track 221/222 (one frame, dump now includes the initial flow). Verdict 3/9 (serious seconds joins critical/CPU as not-worse).
Tracker stages: preprocess 1.8 (submit; wait ≈0) / detect 15.8 / track 17.9 ms — buckets [1.8,10.4,13.1] then ~[1.7,16.3,18.4]; empty-submit 2.4 ms (replay 0.6) ⇒ with the camera on and the phone in "fair" the GPU already runs at a lower clock; the throughput ceiling is GPU frequency, not the kernels. Replay with the same build: 48.2 fps, tracker 17.4 ms/frame, Sim3 2.20 cm.

### 09-04 20:27 gpufe HYBRID (GPU: CLAHE + GFTT in one prefetched submission; CPU: pyramid + upstream LK) — engine ddfa269e, run-7d61f64d, 600 s live with initial motion
**17 739 poses (29.6/s = the live channel's 30 fps cap), camera 29.7 fps, platform drops 185 (was 6875), p95 pipeline latency 33.4 ms (ARKit 55.5 → NOT WORSE), first pose 2.5 s**, footprint 340 MB, CPU 0.82 cores (ARKit 0.80 → "worse" by 0.02), serious from 265 s (336 s serious total), 0 fallbacks, audit CLAHE 356/356, detect 356/356 (LK is now the upstream CPU code itself). Strict verdict 2/9 (latency joins; CPU and serious-seconds drop out).
Tracker thread: GPU submit 0.8 + wait ~5 + CPU pyramid 2.2 + CPU LK 1.8 + host select 0.25 ≈ 10 ms/frame. Replay with the same build: 74.3 fps (was 48), Sim3 2.35 cm.
First 300 s (product cap) — XRSLAM: thermal mostly fair, serious 35 s; ARKit: nominal/fair, 0 serious.

### 09-04 21:55 hybrid arm, live 300 s with the camera at 60 fps (`-PWLiveCameraRate 60`, engine 9580f22c, run-44a75d0e)
32.3 poses/s, camera 37.0 fps, 6871 drops, p95 994 ms, first pose 32.8 s, CPU 1.27, serious from 111 s, verdict 1/9. Tracker waits 14.9 ms/frame for the GPU (submit→finish 41 ms): CLAHE+GFTT at throttled clocks (~19 ms/frame) exceeds the 16.7 ms budget, the engine tops out at ~32 fps and the back-pressure gate drops the rest ⇒ latency back to ~1 s. 30 fps channel (29.6/s, 33 ms) is this pipeline's operating point.

### 09-04 22:18 v38 = hybrid + slim frames (L0 only, pool ≤3) + CLAHE/detect split into two submissions + audit opt-in (`-PWXrslamGpuFrontendAudit`) — replay gate (engine 5c95499c, run-657d5782)
audit clahe 33/0 detect 33/0 (bit-exact on device after the split); footprint max **268 MB** (was 340; ARKit 266); replay 83.3 fps (was 74); ATE Sim3 2.47 / SE3 2.84 cm (thread-scatter band); tracker: preprocess 0.90 ms (wait 1.64) + cpu pyramid 2.30 + cpu LK 2.59 + detect 0.41 (det_gpu 0.05 = detection already finished behind the CPU LK).
Mac: harris_fused (Sobel recomputed inside Harris, no dx/dy round trip) = 0 bitwise eig mismatches / 2 764 800 under strict math (the 430 313 seen without AETHER_STRICT_MATH=1 was the probe running fast-math). → v39.

### 09-04 22:33 v39 = v38 + harris_fused (Sobel recomputed inside Harris; dx/dy buffers gone) — replay gate (engine 70b666c5)
audit clahe 33/0 detect 33/0; footprint max **246 MB** (v38 268, ARKit 266); ATE Sim3 2.53 / SE3 2.87 cm (band); replay 77 fps (pre_gpu 14.2 ms at replay clocks — replay-to-replay GPU timing scatter is larger than the fusion effect; the live throttled-clock run is the judge).
Mac (v40 prep): GPU pyramid readback (pyrDown levels, no derivatives, packed padded layout) = 0 / 3 943 656 padded bytes vs CPU buildOpticalFlowPyramid dumps, detect ordered 150/150.

### 09-04 22:50 v40 = v39 + GPU pyramid (pyrDown levels read back packed, zero-copy bordered Mats fed to the upstream CPU LK; no derivatives) — replay gate (engine 55ff21ce)
audit clahe 33/0 detect 33/0, **track 32/32 mismatching (≤0.0018 px on 44% of points)** → Mac probe (lk_deriv_path_probe, OpenCV 4.0.1): derivative-free vs withDerivatives pyramids give identical LK (150 pts, 0 diff) ⇒ the on-device diff is the audit again omitting the IMU-predicted initial flow (same trap as 09-03), not the pyramid. Footprint max 242 MB; ATE 2.23/2.54 cm; cpu cores 1.80 (v39 1.96, v38 2.22). Tracker thread: cpu_lk 4.45 ms (was 2.32 + pyramid 2.09) — the derivative-free pyramid makes the upstream LK recompute Scharr in both the forward and the reverse call, so no tracker-thread gain. → v41: per-level buildOpticalFlowPyramid(maxLevel 0, withDerivatives) reusing the bordered GPU level (tryReuseInputImage) = Scharr once; audit seeded with the initial flow.

### 09-04 23:05 v41 = v40 + per-level buildOpticalFlowPyramid(maxLevel 0, withDerivatives) on the GPU levels (Scharr once) + audit seeded with the initial flow — replay gate (engine 29171c17)
audit clahe 33/0 detect 33/0 **track 32/0** (LK on GPU pyramid == LK on CPU pyramid, bit-exact); ATE 2.34/2.54 cm; footprint max 269 MB (derivative Mats back; v39 246); cpu cores 1.82; tracker: preprocess 0.83 + scharr 1.40 + LK 2.36 + detect 1.37 (det_gpu 1.05) ≈ v39's 6.1 ms — the GPU only replaced pyrDown (~0.7 ms CPU). v39 vs v41 decided live (same build, `-PWXrslamGpuFrontendCpuPyr` = v39 behaviour).

### 09-04 22:35 live 300 s, v41 arm (GPU pyramid + fused Harris; engine 29171c17, run-2d9cae2f) — user did not move at start (first-pose invalid)
28.3 poses/s, p95 **621 ms**, drops 453, footprint 296, CPU 0.75, serious from 98 s (203 s), verdict 2/9. GPU wait per frame: pre_wait 9.0 + det_gpu 15.0 ms; empty submit 19 ms (GPU deeply throttled).
### 09-04 22:54 live 300 s, same build with `-PWXrslamGpuFrontendCpuPyr` (= v39 behaviour; run-bd88bc84) — first pose 41 s (late motion)
steady 29.9 poses/s (25.8 over the whole run), p95 46.9 ms ✓, drops 26, footprint 280, CPU 0.73 ✓, serious from 157 s (144 s), verdict 3/9. GPU wait identical to v41 (pre_wait 9.1 + det_gpu 14.6, empty submit 19 ms) ⇒ the extra GPU wait is not the pyramid; replay GPU time v38 12.7 → v39 14.2 ms says fused Harris is slower (ALU-bound on a throttled GPU) — it only bought 22 MB. Decision: fused Harris and GPU pyramid become opt-in flags (`-PWXrslamGpuFrontendFusedHarris`, `-PWXrslamGpuFrontendGpuPyr`), default = v38 behaviour → v44.

### 09-05 11:59 live 300 s, v44 default arm (= v38 behaviour: slim frames, split A/B, sobel+harris, CPU pyramid; engine 0f69c2b3, run-413ab8df)
26.5 poses/s, camera delivered only 27.7 fps, p95 **827 ms**, drops 663, first pose 13.3 s, footprint 280, **CPU 1.23 cores**, serious from **74 s** (227 s), verdict 1/9. GPU waits small (pre_wait 2.4 + det_gpu 5.0) ⇒ not GPU-bound; CPU-side times inflated (pyramid 2.78, LK 3.19 vs 2.0/2.3) and the camera itself under 30 fps ⇒ the device was CPU-throttled from early on (fastest serious ever, after an idle night). Suspect device state (thermal/power), not code: v43 (same slim/split code, fused Harris on) was p95 46.9 / CPU 0.73 the evening before. Repeat needed.
### 09-05 17:44 v44 repeat aborted: phone battery died mid-run (explains the 11:59 anomaly too: low battery ⇒ iOS power throttling).
### 09-05 19:41 v44 repeat, phone cool + charged (run-753cf3b0): **reproduced** — 22.9 poses/s, camera 27.2 fps, p95 849 ms, drops 816, footprint 304, CPU 1.09, serious from 138 s, verdict 1/9 (first pose 43 s: late motion). GPU waits small (2.4 + 5.6) but pre_gpu 20.8 ms, empty submit 11.3 ms, prefetch_declined 2066 (v43 509).
Reading: every version since v38 submits TWO batches per frame (A: CLAHE, B: detect); at throttled clocks each submission carries ~11–19 ms of overhead (empty_submit), so per-frame GPU occupancy grew by ~10 ms; when the tracker falls behind, prefetches are declined, preprocessing turns synchronous, and the pipeline collapses (self-reinforcing). v43 (fused) sat at the edge (24 ms waits, p95 46.9); v41 and v44 tipped over. The 20:27 hybrid (ONE submission, pipelined) had ~5 ms waits and p95 33. → v45: single submission again (split behind a switch, default off), keep slim frames + audit fixes.
### 09-05 21:00 v45 live (single submission again; engine 64d197a4, run-ec5cdc13): **still collapsed** — 22.8 poses/s, camera 26.6 fps, p95 864 ms, drops 1007, footprint 313, CPU 1.06, serious from 132 s; pre_gpu **33.4 ms** (CLAHE+detect in one submission), pre_wait 13.4, empty submit 1.6 ms, prefetch_declined 2235. So the split was not the cause. Every run today (11:59, 19:41, 21:00) shows the camera itself under 30 fps and serious within ~2 min; yesterday's runs did not. Need an environmental control (ARKit arm live today) and battery/charging state in telemetry before touching more code.
### 09-05 21:10 battery state from telemetry.jsonl (batteryState / level / first serious):
good hybrid runs: run-7d61f64d (09-04 20:37, 600 s) **full** 100% → serious 266 s; run-bd88bc84 (v43, 22:59) **full** → 158 s.
collapsed runs: run-413ab8df (11:59) charging **15%** → 75 s; run-753cf3b0 (19:41) charging 70% → 139 s; run-ec5cdc13 (v45, 21:00) charging 70% → 133 s; run-2d9cae2f (v41) charging 100% → 99 s.
Charging (heat from the charger + battery at < full) is the confound candidate for today's collapses; next control = same v45 build, phone unplugged during the run.
### 09-05 21:20 correction + latency root cause
Charging is a legitimate product condition (user), and the ARKit reference itself ran while charging (0 serious s, 0.80 core). Today's three runs are valid failures: under charging heat our pipeline (full-res GPU CLAHE+GFTT every frame + CPU LK + backend) draws more power than ARKit, gets throttled (GPU CLAHE+detect 33 ms/frame), and then COLLAPSES instead of degrading.
Collapse mechanism (bench + library): xrslam's producer-side gate (`await_capacity`, thrbp) blocks the feeder thread when the tracker backlog is full → camera+IMU events pile up in the bench's serial handoff (capacity 8 + 2×128 = 264; peak 155 ≈ 1 s) → pipeline latency 800+ ms, camera callbacks dropped (platform drops), pose rate 23/s. Pipeline latency = pose emit time − capture time.
Fix (bench, flag `-PWXrslamDropStaleCamera`): each drained batch submits only its newest camera frame, IMU untouched, older frames counted as `stale_camera_dropped`. Byte-identical when not overloaded.
### 09-05 21:16 run-bf460e8f (flag -PWXrslamDropStaleCamera) — **INVALID**: the live chain does not install; the phone still ran the v45 app (receipt eng_sha 64d197a4), stale drops 0, handoff peak 173, p95 1029 ms, camera 23.4 fps (camera_drops_out_of_buffers 1961: AVFoundation runs out of pixel buffers because queued events hold them). Lesson: always match the receipt's eng_sha to the build before reading a run. Rebuilt + installed engine fc6c3fcf / app bc0354ae (flag string and diagnostic_stale_camera_dropped verified in the binary).

## 09-08 21:39 live 300 s, drop-stale-camera arm (engine c94f735a, app 0a24f384, run-470abebc) — charging, the collapse is fixed
Rebuild note: `~/Developer/viobench-build` had been reclaimed (disk 99%); the iOS front-end lib was rebuilt from scratch (script reconstructed, gpufe.a 34981c3d) and now links a **different Dawn archive** (rebuilt 09-07, sha 199fec5e vs the pinned 625cf65d). Replay gate re-run first: audit clahe 33/0, detect 33/0, 0 fallbacks, ATE 2.17/2.54 cm ⇒ still bit-exact.
| metric | v45 (09-05 21:00) | drop-stale (now) | ARKit |
|---|---|---|---|
| p95 latency ms | 864 | **42.0** | 55.5 ✓ |
| max latency ms | 1341 | 154 | — |
| poses/s | 22.8 | 28.4 | 59.9 |
| CPU cores | 1.06 | **0.80** | 0.80 ✓ |
| platform drops | 1007 | 43 | 0 |
| footprint MB | 313 | 276 | 266 |
| first pose s | 38.5 | 3.6 | 1.5 |
| verdict | 1/9 | **3/9** | |
387 stale frames dropped; handoff peak still hits 264/264 (the producer gate still stalls the feeder) — but latency no longer follows the queue, because only the newest frame of each batch is submitted. Latency and CPU now match ARKit; the remaining gaps are structural: pose rate is capped by the 30 fps camera channel (ARKit takes 60), 173 s serious = our pipeline draws more power, footprint +10 MB, first pose needs motion to initialise.

## 09-09 pose delivery decoupled from the visual frame rate
Upstream already computes the IMU-propagated pose: `Detail::track_gyroscope` and `track_accelerometer`
both `return predict_pose(t)`. The C interface discarded that return value, and `XRSLAM_RESULT_BODY_POSE`
reads `latest_pose_`, which is only written in `track_camera` - so our pose rate was the visual frame
rate by construction. Additive fix (`XRSLAMGetPropagatedPose`, XRSLAMGetResult untouched) plus a bench
flag `-PWPosePollHz N` that polls it instead of taking one pose per frame.

| live 300 s, charging | 09-08 per-frame | 09-09 first try (BODY_POSE) | 09-09 propagated |
|---|---|---|---|
| poses/s | 28.4 | 23.8 | **47.9** |
| p95 latency ms | 42.0 | 6.5 | 7.6 |
| CPU cores | 0.80 | 1.25 | 1.06 |
| serious s | 173 | 220 | 197 |
| verdict | 3/9 | 2/9 | 2/9 |
47.9 rather than 60 is the poll scheduler, not the engine: the loop resets its deadline to `now` after
each poll, so每 iteration's overshoot accumulates (60 x 16.7/20.9 = 47.9). Accumulating the deadline
instead should reach 60. Unverified: these are propagated predictions and the live channel has no
ground truth, so a replay arm polling in sensor time and scoring ATE against ARKit still owes us the
accuracy answer.

### Engine build environment restored (the 09-08 disk cleanup had destroyed it)
OpenCV 4.0.1 iOS framework re-downloaded (MD5 35ebe10d... = the value upstream's CMake pins) and Eigen
3.3.7 (the tag upstream pins; the local Aether3D copy is 3.4.0 and was not used). `configure_engine.sh`
and `assemble_and_build.sh` reconstructed from the recipe recorded in the artifact receipt.
Bit-identity was NOT achieved: 44 of 57 archive members differ from the 09-05 build. Compiler version,
SDK and determinism were all checked and are unchanged; the one object disassembled differs by register
allocation and one stack spill, i.e. equivalent instruction sequences, but that was not proven for all
44 and the cause is unidentified. The gate therefore fell back to behaviour, which passed: on-device
audits CLAHE 33/0 and detect 33/0 (bit-exact against the CPU path), 0 fallbacks, ATE 2.21 cm inside the
2.36-2.54 band. The 09-05 archive is preserved at ~/Developer/pw_backups/.

### 09-09 02:42 poll scheduler fixed (accumulate the deadline) — run-099164cd, engine aa1250ce
52.3 poses/s (was 47.9), CPU 0.81 cores (ARKit 0.80), p95 7.6 ms, footprint 302, serious 203 s, first
pose 4.2 s, verdict 2/9. The remaining 13 % to 60 is the harness, not the engine: polling happens inside
the single-threaded live drain loop, one pose per iteration, and an iteration sometimes exceeds 16.7 ms.
The engine can emit a pose per IMU sample (100 Hz). Pose rate is now a harness property; the open gaps
are power (203 s serious vs 0), memory (302 vs 266 MB) and initialisation (4.2 s vs 1.5 s).

### Propagated-pose accuracy, replay against the ARKit reference — CORRECTED
The first attempt (02:21-02:33, runs 4f58a9f1 / 80f57848 / a53a95b0 / d180db0f) is **void**: the flags
were passed from an interactive zsh as an unquoted `$flag`, and zsh does not word-split, so
`-PWHalfFrameRate -PWPosePollHz 60` reached the app as ONE argument and neither flag was parsed. Three
of those four "arms" were the same unmodified configuration run three times, and the 2.53 cm number
reported from them as evidence of propagation quality proved nothing. Same trap as 09-05; the bench now
writes `diagnostic_half_frame_rate` so a flag that was passed but not parsed shows up in the receipt.

Re-run with arguments passed as separate words, both arms verified at 849/849 accepted frames (30 fps):
| arm | poses | pairs vs ARKit 60 Hz | Sim3 ATE | scale |
|---|---|---|---|---|
| half rate, per-frame poses | 796 | 796 | 4.33 cm | 4.16% |
| half rate + 60 Hz polling (**every second pose is IMU propagation**) | 1331 | 1331 | **3.71 cm** | **1.44%** |
Propagation does not cost accuracy — it improves the score, because ATE pairs by timestamp against
ARKit's 60 Hz track and the propagated poses fill the gaps between visual updates, giving a denser and
more evenly spaced alignment (796 -> 1331 pairs).

Also fixed: `-PWHalfFrameRate` was never scoreable. The replay guard compared `cameraAccepted` against
every camera event in the recording, so deliberately feeding half of them was reported as
`replay_input_count_mismatch` — a harness invariant, not the engine crash it looked like. The guard now
halves its expectation when the flag is on.

### 09-09 time-to-first-pose, attributed and closed
Instrumented the initializer's four exits (two were silent) plus the frame-count floor, and split the
wall clock. Live, engine cd5948cf:
| | run-acec8e26 | run-29d3398b |
|---|---|---|
| first pose | 3555 ms | 5221 ms |
| capture warm-up (start → first frame in engine) | — | **317 ms** |
| frame-count floor (`gap*(num-1)`) | 35 | 35 |
| attempts | 3 | 54 |
| failed on shared tracks < 50 | 2 | **53** |
| failed on parallax / rotation / triangulation | 0 | 0 |
So ~70 % of the wait is the geometric condition "the first and last sampled keyframes share 50 tracked
features" not yet holding, and the spread between runs is entirely that. Capture warm-up is 6 %.

**Lossless optimisation attempted and measured worthless.** `mirror_keyframe_map` clones eight frames,
rebuilds their tracks and concatenates 35 frames of IMU on *every* attempt, before init_sfm() applies
the shared-track test that rejects nearly all of them; `PW_INIT_FAST_REJECT=1` applies that same test on
the source map first. Replay off/on: every counter identical (35 / 15 / 13 / 1 / 1), so the decision is
provably unchanged — but the whole mirror cost is **14.4 ms across 15 attempts**, about 1 ms each. The
hypothesis that failed attempts were starving frame intake is refuted by its own measurement. Flag kept,
default off.
Where the intake shortfall really is: during initialisation the engine consumed 91 frames in 4.9 s
(18.5 fps) while the camera delivered ~29 fps. The limit is the per-frame front end — tracker waits
14.5 ms for the GPU (21.3 ms of GPU work), plus 2.2 ms CPU pyramid and 2.2 ms CPU LK — not the
initializer. Making initialisation converge sooner without changing which observations it uses therefore
reduces to making the front end faster, which is the work already done and now bounded by the throttled
GPU.
