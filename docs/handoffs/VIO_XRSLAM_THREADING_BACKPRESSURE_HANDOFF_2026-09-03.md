# XRSLAM threading back-pressure — 2026-09-03 handoff

Continues `VIO_XRSLAM_PRODUCTION_PIXEL_HANDOFF_2026-09-02.md` §6 (the memory blocker). Scope: the
**replay-channel** failure only ("pure threading dies on unpaced replay: upstream's frame queue has no
bound"). The **live** 41 MB/s leak in the observability patches is a different bug and is untouched here.

## What was built

A producer-side gate inside the library, `~/Developer/xrslam-4beb1a9-thr`, branch
`pw/threading-backpressure-20260902`, tag `bench/threading-backpressure-2026-09-02`, commit `2c88935`:
`Worker::await_capacity()/notify_space()` with `space_cv`; `FeatureTracker::track_frame` and
`FrontendWorker::issue_frame` block when their deque reaches its cap (2 / 4, overridable with
`-DXRSLAM_FEATURE_TRACKER_QUEUE_CAPACITY` / `-DXRSLAM_FRONTEND_QUEUE_CAPACITY`). It waits, never drops.
With `XRSLAM_ENABLE_THREADING` off it compiles to nothing (byte-identical `.o`, positive control passed).
Both call sites hold no lock (`issue_frame` is outside `synchronized(map)`); `stop()` also notifies
`space_cv` so a blocked producer wakes at shutdown.

Two archives, production-shaped (54 members, generic, `-Dceres=pw_xrslam_ceres_1_14 -fchar8_t
-ffp-contract=off -fno-fast-math`), live in `pocketworld/vendor/xrslam/libs/ios-arm64/` with receipts:
`libxrslam_thrnogate_4beb1a9.a` (threading + accessor only, sha ca98a914…) and
`libxrslam_thrbp_4beb1a9.a` (+ gate, sha b6167af7…).

## Bench changes (uncommitted in this worktree)

- `-PWFeederGateOff`: `XRSLAMNativeSession.snapshot()` reports `cameraInputQueue.capacity = 0` so
  `waitForReplayCapacity` returns immediately. Without it the bench's own gate (cap 2, driven by
  `XRSLAMGetPendingWorkerFrames`) hides the engine's unbounded deque whenever the accessor is present.
  Audit trail: `diagnostics.json/queue_measurements/camera_input_capacity = 0`.
- `xrslam_engine_backlog_peak` (`XRSLAMBench.h/.cpp`, diagnostics `effective_configuration`): peak of the
  accessor across snapshots. `camera_input_peak` is the single handoff slot and saturates at 1; it cannot
  show whether the engine's queue is bounded.

## Results — one recording (run-6e2d4b99, 1702 frames 1920×1440 @60, IMU 100 Hz), backend xrslam

| run | arm | bench gate | pacing | outcome |
|---|---|---|---|---|
| R0 `run-4fcc212e` | thrnogate | on | max | complete, 1640 poses, 34.3 fps, 0 drops, footprint ≤157 MB, backlog peak 3 |
| R1 `run-b9eca18c` | thrnogate | **off** | max | process gone at **+6 s**, 0 poses (5 s heartbeat too coarse to see the curve) |
| R1p `run-82b0c66e` | thrnogate | off | paced 60 fps | 29→776→1463→2895 MB, **jetsam at +29 s** (`JetsamEvent-2026-09-03-185429.ips`: victim VIOReplacementBench, `per-process-limit`, rpages 196608) |
| R2 `run-d1902ae4` | **thrbp** | off | max | heartbeat flat ~145 MB to +50 s; **artifacts lost** to the self-test purge (below) |
| R2b `run-2de39ccd` | thrbp | off | max | complete, 1638 poses, 29.1 fps, 0 drops, footprint ≤168 MB, backlog peak **6** |
| R2p `run-1ffdacc4` | thrbp | off | paced 60 fps | complete, 1638 poses, 25.1 fps, 0 drops, footprint ≤175 MB, backlog peak 6 |

Receipts bind the arm: `engine_artifact_sha256` is the sha256 of the `PWXRSLAMEngine` framework binary
(thrnogate 4a9c75d1…, thrbp 3dffda97…), `app_binary_sha256` matches the built app.

**Verdict.** Under identical feeding the un-gated threaded engine dies in 6 s (unpaced) or 29 s (camera
rate); the gated one completes both with flat memory. Backlog peak 6 is the configured bound: the accessor
sums the tracker deque (cap 2) and the frontend deque (cap 4). Pose counts 1640 vs 1638 are within
threading's non-determinism (the 09-02 note measured 1646/1641).

**Not a throughput comparison.** R0 ran at thermal `nominal/fair`, R2b `fair/serious`, R2p entirely
`serious`; the 09-02 note already measured 28→21 fps from heat alone on the non-threaded library. The fps
column is confounded and must be re-measured cold, alternating arms in the same hour.

## What this does not close

- The **live** leak (09-02 §6, 41 MB/s with the three observability patches). thrnogate carries only the
  accessor patch; a live-soak of thrnogate vs thrbp (`-PWAutoRun live-soak -PWAutoRunBackend xrslam
  -PWLiveFullResolution -PWAutoRunSeconds 120`, stationary is fine) is the next bisect step and was not run.
- Long-duration thermal (09-02 §11 item 2) — now unblocked on replay, still unmeasured.
- The gate turns unbounded growth into producer stalls. Under sustained overload frames are still lost
  upstream (PocketWorld's `PwVioSlamFeeder` ring drops with `queue_full`); "no frame loss" holds only inside
  the library.

## Traps hit today (each cost a run)

- `-PWAutoRun` runs carry `.self_test` and are **purged on the next launch**. Pull and verify
  `receipt.json` is on disk before launching anything else; `backup_runs.sh`'s "设备上没有 run" must not
  be filtered out of the log. R2 was lost this way.
- A device that is `unavailable` makes `devicectl device info files` return a 2-line empty table. That is
  a probe failure, not an empty container — the 4.7 GB recording was on the device the whole time.
- Jetsam `.ips` files land minutes late. Absence at the moment of death is not evidence against jetsam.
- `receipt.json` exists from run start (state `started`); completion is `SHA256SUMS` / `diagnostics.json`.
- Editing `run_arm.sh` while an instance was executing it (bash reads incrementally).

## Repository state

- Bench worktree: vendored `.a` restored to production (`fdc75c99…`, `verify_vendor.sh` green). Three
  source files modified (flag + backlog peak), not committed. Validator (`validate_bench_artifact.py`)
  predates the `replay_device_recording` channel and the current scope string; it fails on 09-02 receipts too.
- PocketWorld: `com.kyle.PocketWorld` on device restored to the default arm (build id
  `default-restore-20260903`, `PWXrslamSHA256 = fdc75c99…`). Uncommitted: `PW_XRSLAM_BENCH_ARM` switch in
  `ios/Podfile` and `ios/scripts/stamp_runtime_identity.sh` (default path byte-equivalent; 15 contract tests
  green), the two arm archives + receipts, a Dart queue-depth probe (`lib/vio/diagnostics/vio_queue_depth_probe.dart`,
  degrades explicitly when the symbol is absent) and its two hooks in `ar_capture_page.dart`. The Dart probe
  is not needed for the bench path; keep or drop is a product call.
- Artifacts: `~/Developer/viobench-recordings/{run-4fcc212e,run-82b0c66e,run-b9eca18c,run-2de39ccd,run-1ffdacc4}`
  and `eval-xrslam-threading-backpressure-20260903/` (RESULTS.md, poll logs, jetsam .ips).

## Addendum (same day): the cold-start gate was wrong, and there is nothing upstream to copy

**Gate.** `BenchGateEvaluator.live` failed any arm whose first usable pose came after 1 800 ms. That
number is `ar_capture_page.dart:711 _warmupFallbackDuration` — a UI warm-up fallback that opens the
capture page whether or not tracking is normal. It is not a tracking requirement, and ARKit itself
measures 2 874.9 ms to `.normal` on the shared recording, so the absolute gate failed the reference it
was supposed to compare against. Owner's call on 2026-09-03: the gate is now **relative** — a candidate
fails only if its first-usable-pose latency exceeds the ARKit reference receipt found on the device
(`app.engine_id == "arkit_reference"`, newest `VIOBenchRuns/*/receipt.json`); with no reference the
gate is not evaluated and `metrics.arkit_reference_first_usable_pose_latency_ms = -1` records that.
Touched: `BenchGateEvaluator.swift`, `BenchmarkCoordinator.swift` (both live call sites),
`BenchGateEvaluatorTests.swift` (+1 test), `Schemas/metric_definitions.v1.json` (one sentence — this
changes `metric_definitions_sha256`, so receipts from today onward carry a new identity). App and test
bundle build. The 08-30 contract's "不在看到结果后调门槛" rule was knowingly overridden by the owner;
the reason is the transcription error above, not the result.

**Nothing to copy.** Per the owner's rule (search for an existing fix, copy it, do not invent), the
XRSLAM lineage was checked for any bound on the threaded frame queue:

- upstream `openxrlab/xrslam`: `worker.h` has a single commit ("first commit", 2022-09-01);
  `feature_tracker.cpp` changed only for IMU-PARSAC (2024-01) and the viewer (2024-07); one branch
  (`main`, at 4beb1a9); 12 issues/PRs, none about memory, queues or threading.
- predecessor `zju3dv/PVIO`: `pvio/src/pvio/utility/worker.h` is the same class line for line — no bound.
- forks: `manorajesh/xrslam` (deps, PARSAC, depth fusion, `-ffast-math`; nothing on threading),
  `TuskAW/xrslam` (= upstream), `zitongzhan/xrslam_ios` (behind upstream).
- `Jianxff/rd_vio` ("separated from xrslam, multi-threading enabled by default"): `track_frame` is
  `frames.emplace_back(...)` with no size check, no wait, no drop.
- upstream's own iOS demo (`xrslam-ios/visualizer`): pushes every frame unconditionally from the
  sample-buffer delegate on `.main`, VGA 640×480, no `alwaysDiscardsLateVideoFrames`. It never ran at
  production pixels, which is why the bound was never needed there.

So the library gate in `2c88935` stays as the only implementation; it is the minimal one (block the
producer at the two deques, never drop). For the **live** 41 MB/s leak the copyable answer is the
09-02 note's own: the three observability patches are not upstream code and their source no longer
exists outside `mine.a`; drop them and rely on the per-pose validity check already in
`XRSLAMPoseAdapter.makeTimedPose`. The `thrnogate` arm (accessor only) is the natural first bisect.

## Addendum 2 (evening): the live "leak" is the same unbounded deque

Step-1 live-soak, `thrnogate` (threading + accessor only), 1920×1440 at the live channel's 30 fps (SensorTransportModels.productionResolution.cameraRateHz = 30; the 60 fps in the 09-02 note does not match the tree — 3 591 frames in 120 s confirms 30), phone propped, started at
thermal nominal:

- `run-4eb94170` (first attempt): never initialised (0 poses, stationary), footprint flat 158 MB for
  120 s. Verdict `invalid: platform_camera_loss` from **one** late camera frame in 3 590; the bench then
  discarded the system samples. Fixed the same evening: `BenchmarkCoordinator` now calls
  `writeSystemSamples` before the `.invalid` terminal receipt in both live paths (verdict unchanged,
  measurement kept).
- `run-8a4df815` (rerun, same arm): **initialised** (3 536 poses; first usable pose 2 155.7 ms, below
  the ARKit reference 2 874.9 ms so the relative cold-start gate passes) and then grew without bound:
  footprint 29 → 182 → 219 → 627 → **1 866 MB** over 120 s, `xrslam_engine_backlog_peak` **314**,
  camera 3 591/3 591 accepted with 0 late drops, p95 32 ms, thermal nominal 33 s / fair 25 s /
  serious 62 s, CPU 2.2 cores.

314 queued frames × ~6 MB (luma + decode planes) ≈ 1.9 GB, which is the footprint. So the 09-02 note's
"41 MB/s live leak in the observability patches" is most likely this same unbounded engine deque:
it only appears once the engine is initialised and falls behind the 30 fps camera (thermal throttling makes that
worse), and every "flat" live run in that note (pure_threading 160 MB, this run-4eb94170) was one that
never initialised. The attribution to the three observability patches was a confound of
initialised-vs-not, not evidence about the patches. Whether `thrbp` (library gate) holds live is the
next run (`scripts/pw_step1.sh`).

Orchestration now lives in the repo (`scripts/pw_*.sh`) and builds in `~/Developer/viobench-build/`;
the scratchpad copies were lost to a session restart.

## Addendum 3: the gate holds live; the cost is where the overflow goes

`thrbp` live-soak 120 s (`run-f92cafbb`, same setup, started nominal): initialised (2 077 poses, first
usable 17.2 s), **footprint flat — peak 229 MB, end 140 MB, `xrslam_engine_backlog_peak` 6, i.e. the
configured 2 + 4**. Under identical conditions the un-gated arm reached 1 866 MB with a 314-frame
backlog. Step 1's memory question is closed: the library gate bounds the engine deque on replay and live.

What the gate cannot do is make the engine faster. Blocking the producer means blocking AVFoundation's
sample-buffer delegate, so the camera itself ran out of buffers: `camera_drops_out_of_buffers = 1 024`,
only 2 582 frames delivered (21 fps), processed 17.1 fps, p95 pipeline latency 1 425 ms (max 1 774),
Swift handoff peak 203/264, thermal serious 63 s. Verdict `invalid: platform_camera_loss`. The
underlying fact is the same as in Addendum 2: at 1920×1440 and 30 fps the engine falls behind as soon as the
device is `fair`/`serious`. Production already reacts to that (60 → 30 fps after `fair` ≥ 10 s); the
bench live channel does not, so under heat it keeps the 30 fps that production would also fall back to.

Step 2 (thermal, 600 s, ARKit reference then `thrbp`, cooled to nominal before each) is running from
`scripts/pw_step2.sh`.

## Addendum 4: step 2, `thrbp` for 600 s

`run-0fd0093f`, live-soak 600 s at 1920×1440 / 30 fps camera, started at thermal nominal, phone propped
and untouched. **Memory is closed for long duration**: footprint peak 245 MB, end 141 MB, engine backlog
peak 6, for the full ten minutes. Thermal: `serious` from 54 s and for the remaining 548 s, never
`critical` (the same 54–58 s onset as every 120 s run, both arms — the device reaches `serious` in under
a minute at this workload regardless of the gate). CPU 1.9 cores.

Throughput under that heat is not acceptable: 11 569 camera frames delivered (19 fps — the gate blocks the
sample-buffer delegate and AVFoundation runs out of buffers), 6 244 poses (10.4 fps), p95 pipeline
latency 1 596 ms, 195 s to the first usable pose, Swift handoff ring pinned at 264/264. Against the
owner's step-2 bar: `thermal_critical = 0` passes; "fps not below the 30 fps fallback" fails (10.4);
"poses uninterrupted" fails (1.6 s latency).

The gate did its one job. What is now measured, not argued: at production pixels the engine cannot
sustain even the 30 fps thermal-fallback rate once the device is `serious`, and it is `serious` within a
minute. The only lever already measured and upstream's own is `sliding_window.tracker_frequent` 1 → 2
(`-PWTrackerFrequent 2`; the 09-02 note measured it on replay only). `scripts/pw_step2b.sh` runs the
same 600 s soak with it; nothing else is changed.

## Operational note (late evening)

- The ARKit reference live-soak first attempt left a run directory holding only the self-test marker:
  the failure happened after `prepare()` created the directory and before `writeStarted`, and that
  path wrote nothing. `BenchmarkRunPreparation.prepare` now writes `failure.json` into the directory on
  any throw after creation. The rerun (with that build) is queued behind a cool-down.
- `thermalState` gating uses iOS `ProcessInfo.thermalState` (throttling level), not skin temperature;
  a phone can be `serious` without feeling warm. Every arm reached `serious` 54–58 s into every run.
- Long chains (cool → run → pull → cool → run) are launched with `nohup … & disown` and log to
  `~/Developer/viobench-recordings/eval-xrslam-threading-backpressure-20260903/chain_*.log`; Claude Code
  session restarts kill ordinary background tasks (three lost chains today).
- Pending: `S2-arkit-live600` (or its `failure.json`), then `S2b-thrbp-live600-freq2`.

## Addendum 5: why the ARKit live-soak arm never ran

With `failure.json` in place the rerun (`run-c6158e67`) reported `invalidRoot` from
`CalibrationMaterializer`. Cause: the live-channel branch that rewrites the frozen calibration to the
production resolution when `-PWLiveFullResolution` is set applied to every backend, and
`arkit_runtime_calibration.json` is a descriptor (`calibration_owner` / `intrinsics_source` /
`pose_frame` / `status`), not a Basalt-layout file, so the rewrite threw before the started receipt.
Fix (`BenchmarkRunPreparation.swift`): the rewrite is skipped for `backend == .arkit`; ARKit carries its
descriptor through unchanged, as the non-full-resolution path already did. The 09-02 note's ARKit
numbers came from the `record` channel, which never enters this branch — an ARKit live-soak at full
resolution had never been attempted. Rerun queued behind step 2b (`scripts/pw_chain_arkit_fix.sh`).

## Addendum 6: step 2b — the one upstream lever, `tracker_frequent` 1 → 2, live 600 s

`run-f26fab79`, identical to step 2's `thrbp` soak except `-PWTrackerFrequent 2`:

| | freq 1 (`run-0fd0093f`) | freq 2 (`run-f26fab79`) |
|---|---|---|
| camera frames delivered / 600 s | 11 569 (19 fps) | 16 160 (27 fps) |
| poses | 6 244 (10.4 fps) | 15 628 (26.0 fps) |
| p95 pipeline latency | 1 596 ms | 787 ms |
| first usable pose | 194.9 s | 18.0 s |
| Swift handoff peak | 264 / 264 | 177 / 264 |
| footprint peak / end | 245 / 141 MB | 235 / 223 MB |
| engine backlog peak | 6 | 6 |
| thermal | serious from 54 s, 548 s serious | serious from 65 s, 536 s serious; never critical |
| CPU | 1.9 cores | 1.8 cores |

Halving the corner re-detection rate more than doubles sustained throughput under `serious` and cuts
latency in half, with the memory bound intact. It is still short of the 30 fps thermal-fallback floor and
the run is still `platform_camera_loss` (AVFoundation out-of-buffers while the delegate is blocked), so
the step-2 bar is not met yet — but this is the first live 10-minute run whose numbers look like a VIO
rather than a stall. `tracker_frequent` is upstream's own YAML key; nothing else was changed.

## Addendum 7: the bar, as the owner defines it

"跟生产端 ARKit 一样或者更好就行" — not worse than production ARKit on the same device under the same
conditions, metric by metric. The 30 fps floor used above was mine (from the contract's `processed_fps`
gate and the thermal-fallback rate), not the owner's, and is withdrawn as a pass/fail criterion. The
09-02 note's ARKit numbers (56.7 fps, 30 s `record` channel, cold) are not a valid reference for a
10-minute soak. The comparison that counts is `S2-arkit-live600` vs `S2b-thrbp-live600-freq2`, same
hour, both started at nominal — pending as of this addendum.

- Offline judgement: `scripts/pw_relative_verdict.sh <candidate-run> <arkit-run>` compares poses/s,
  camera delivery, p95, first usable pose, footprint peak, serious/critical seconds, CPU, platform drops.
- In-app: `BenchGateEvaluator.live` now takes a `LiveReference` (newest same-device ARKit **live-soak**
  receipt, read by `BenchmarkCoordinator.arkitLiveReference()`); when present every live gate is
  relative to it, and the 08-30 absolute values remain only as the no-reference fallback.

## Addendum 8: the ARKit reference ran, and the verdict under the owner's bar

`run-f3d525c9`, ARKit live-soak 600 s, same device, started at nominal, same hour as step 2b (after
the calibration-rewrite fix): **59.9 fps, p95 55.5 ms, first usable pose 1 481 ms, footprint peak
266 MB, thermal nominal 115 s / fair 485 s / serious 0 / critical 0, CPU 0.80 cores, 0 drops,
tracking_normal_ratio 1.0, verdict valid_pass.** Its own cold-start latency is 1.48 s here (the
2.87 s in the record-channel receipt was a different session).

Metric by metric against it (`scripts/pw_relative_verdict.sh`), `thrbp + tracker_frequent 2`:
poses/s 26.0 vs 59.9 — worse; p95 787 vs 55.5 ms — worse; first usable 18.0 s vs 1.48 s — worse;
footprint 235 vs 266 MB — not worse; serious 536 s vs 0 — worse; critical 0 vs 0 — not worse;
CPU 1.84 vs 0.80 cores — worse; platform drops 1 840 vs 0 — worse. **2/8 not worse ⇒ does not meet
the bar.** `thrbp` with the default tracker is worse on every axis but memory.

What the pair says, without interpretation: on this iPhone 14 Pro at 1920×1440, ARKit holds 60 fps for
ten minutes at 0.8 cores and never leaves `fair`; XRSLAM (threaded, gated, half-rate detection) needs
1.8 cores, pushes the SoC to `serious` inside a minute and then sustains 26 fps at 0.8 s latency. The
gap is not memory any more (closed today) and not a single tunable — it is 2.3× the CPU for 0.43× the
poses. The remaining upstream-owned levers were all refuted on 09-02 (parallel_for, NEON, flags); the
detection cost (73 % of the frame at this resolution) is the structural item.

Comparability caveat: ARKit's arm runs its own 60 fps session; the bench feeds XRSLAM through the
AVFoundation transport at `cameraRateHz = 30`. On poses/s and camera delivery XRSLAM's ceiling in this
harness is therefore 30, not 60 — the verdict on those two rows is against a stricter ceiling than the
candidate could reach. Every other row (latency, cold start, thermal, CPU, drops) is not affected.

## Next: optimise metric by metric, one upstream/production lever per run

The seven "worse" rows share one root cause (per-frame cost → `serious` within a minute → throttling),
so levers are ordered by leverage on that cost, each measured alone against the same-night ARKit
reference with `pw_relative_verdict.sh`:

1. **Resolution 640×480** — production's own XRSLAM feed (`PwVioSlamFeeder` downsample factor 3) and
   upstream's only precedent; front end 27.9 → 4.3 ms per the 09-02 measurements. Cost: replay scale
   error rose from ~2 % to 5.3 % at 640×480 on 09-02 — to be re-measured on replay with this arm.
   Run: `S3-thrbp-live600-freq2-640` (`scripts/pw_chain_lever1.sh`), identical to S2b minus
   `-PWLiveFullResolution`.
2. Detection budget through upstream YAML keys (`feature_tracker_max_keypoint_detection`,
   `feature_tracker_min_keypoint_distance`), one at a time, replay accuracy as the guard.
3. Upstream's own iOS profile (`XRSLAM_IOS=ON`, keymap/PnP low-latency chain) — last, because it does
   not reduce detection cost.
Refuted on 09-02 and not to be retried: `cv::parallel_for_` in corner detection, NEON/compile flags,
OpenCV thread count.

## Addendum 9: resolution is a diagnostic, not a lever (owner: "无损提速")

The owner's rule is lossless speed-up; 640×480 costs pose accuracy (09-02: scale 5.3 % vs ~2 %), so it
is not a shipping lever. It was still run once, as a diagnostic (`run-1e7422d3`, thrbp + freq 2, live
600 s, 640×480): **thermal nominal for the whole 600 s, CPU 0.52 cores (below ARKit's 0.80), footprint
45 MB, p95 40 ms, 0 drops** — the thermal gap at 1920×1440 is pixel count and nothing else. The same
run also shows the stationary cold-start problem at that size: 566 s to the first usable pose, then a
non-finite pose (`invalid: non_finite_pose`).

Lossless gate from here on: every lever must replay the shared recording with ATE and scale not worse
than the full-resolution baseline (R0 2.48 cm / 2.44 %, R2b 2.39 cm / 3.74 %, R2p 2.36 cm / 3.43 %; the
spread is threading non-determinism). `S3r` (640×480 + freq 2) and `S4r` (1920×1440 + freq 2) replays
are queued to place resolution and `tracker_frequent` against that gate separately.

Clarification recorded for the "12 MP" question: 12 MP is the still-photo path into reconstruction and
no VIO sees it; ARKit tracks on 1920×1440; production's shadow XRSLAM is fed 640×480 (factor 3).

## Addendum 10: `tracker_frequent` 2 against the lossless gate (replay, 1920×1440)

freq-1 full-resolution replay baselines on this device (Sim3 ATE vs the ARKit trajectory, `ate.py`):
2.11 cm (09-02 upstream config), 2.36 / 2.39 / 2.48 cm (tonight), 2.54 cm (09-02 back-pressure arm);
scale 2.4–4.1 %. First freq-2 sample (`S4r`, thrbp, bench gate on, cold): **Sim3 3.31 cm, scale
2.67 %, SE3 3.45 cm**, 1 640 poses, 54.9 fps replay. Scale is inside the baseline spread; ATE is
~0.8 cm outside it. Two more freq-2 samples are being taken before calling it. The 09-02 note's own
freq-2 samples were 2.61 / 3.02 cm against a 2.60 cm freq-1 — the same direction.

## Addendum 11: verdicts under the lossless gate, and what is left

`tracker_frequent` 2, three replay samples at 1920×1440: Sim3 ATE 3.31 / 3.30 / 2.87 cm against five
freq-1 samples 2.11–2.54 cm — no overlap, ~+0.8 cm (+33 %); scale not worse. **Not lossless; rejected**
as a shipping lever, kept as the measured throughput lever (26 vs 10 fps live under `serious`).
640×480: lossy by the 09-02 measurement (scale 5.3 %) and, tonight, no initialisation in the bench's
20 s replay stall window; **rejected**, kept as the thermal diagnosis (nominal for 600 s, 0.52 cores).

Parameter-level lossless levers are therefore exhausted: threading + the library gate are the only ones
that passed (memory closed, accuracy within threading spread). Detection-budget keys would trade the same
currency (tracks → ATE) and were not run. What remains lossless by construction is moving the 73 % of
the frame that is corner detection / CLAHE / pyramid onto the GPU with the same algorithm — a project,
cross-platform (the WGSL/Dawn matcher line is the precedent), not a bench evening. Against the owner's bar
(not worse than production ARKit, metric by metric) the CPU-only XRSLAM at 1920×1440 currently scores
2/9; ARKit's 0.8 cores on dedicated silicon vs XRSLAM's 1.8–1.9 is the number that has to move.
