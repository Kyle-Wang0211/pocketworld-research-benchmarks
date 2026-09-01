# XRSLAM at production pixels — 2026-09-02 handoff

Continues `VIO_THREE_ARM_BENCH_HANDOFF_2026-08-30.md`. Everything below was
measured on one iPhone 14 Pro against one shared 28.3 s recording
(`run-6e2d4b99-896b-4372-ae47-ac0b4679cf18`, 1697 frames at 1920×1440, IMU at
100.3 Hz), replayed identically to every arm. Evaluation artifacts are under
`~/Developer/viobench-recordings/eval-*`; the ATE script is
`~/Developer/viobench-recordings/ate.py` (Umeyama, both Sim(3) and fixed-scale
SE(3); the bench's own evaluator uses fixed-scale SE(3) only).

## 1. What production actually feeds a VIO

Read from `pocketworld/ios/Runner/OfficialAetherARKitPlugin.swift` and
`lib/ui/official_capture/ar_capture_page.dart`, not from memory:

- **1920×1440 4:3**, the locked `hires43` preview.
- **60 fps nominal**, dropping to **30 fps** when thermal state is `fair` for
  ≥10 s, back to 60 after `nominal` for ≥30 s (hysteresis).
- 12 MP is the **still-photo** path. The source says it outright: "取景流不进重建
  (重建只吃快门 12MP 静照)". A VIO never sees 12 MP.
- Production already gates on tracking health: `lockOrigin` returns nil unless
  `trackingState == .normal`, and `CaptureSession._lockOriginWhenReady` polls
  every 100 ms. A cold-start window is not a new problem for a replacement.

The bench's scoring resolution already matches (`BenchResolution.scoring =
1920×1440`, `scoringFramesPerSecond = 60`), so "replicate production pixels" was
already true; what was missing was a **live** channel at that size (below).

## 2. ARKit's own numbers, and why the naive comparison is wrong

From the reference recording's receipt (`arkit_reference`, `record` channel):

| | ARKit |
|---|---|
| `processed_fps` | 56.73 |
| `first_usable_pose_latency_ms` | **2874.9** |
| `first_normal_latency_ms` | 2831.4 |
| `p95_pipeline_latency_ms` | 42.81 |
| `tracking_normal_ratio` | **0.9571** |
| `peak_phys_footprint_mb` | 233.1 |
| `cpu_seconds` / 30 s | **20.97** |
| verdict | `valid_fail`, `first_usable_pose_latency_ms>1800` |

Two things follow, both counter-intuitive:

- **ARKit fails the 1800 ms cold-start gate too**, by more than XRSLAM does.
  That gate is stricter than the reference it is supposed to be measured
  against. A ~2 s monocular cold start is physics (scale and gravity need
  translation), not a defect.
- **`processed_fps` is not comparable across arms.** ARKit emits a pose for
  every frame including the ones it flags `.limited`; XRSLAM emits none until it
  initialises. Normalised to poses production would actually use, ARKit is
  1702 × 0.9571 / 30 = **54.30 fps**.

## 3. XRSLAM at production pixels, live

New capability added this session: `-PWLiveFullResolution` runs the live channel
at 1920×1440 instead of the frozen 640×480 pairing. The 2026-08-30 note said
this was blocked because scaling the frozen calibration threefold is only valid
if both formats share a field of view, which could not be shown. It can be shown
now, and better than by scaling: the run enables
`isCameraIntrinsicMatrixDeliveryEnabled` and receipts what the camera reports.

Measured, camera-reported at 1920×1440, stable across four runs:
`fx = fy ≈ 1306–1341, cx ≈ 958, cy ≈ 719`.

The scaled-frozen values would have been `fx 1346.9, cx 964.0`: the principal
point agrees within a pixel but **the focal length is 3% off**, so the two
formats are not a pure scale of each other. The live path now uses the
camera-reported intrinsics; scaling would have been wrong.

30 s handheld run at 1920×1440 @ 60 fps camera:

| | XRSLAM | ARKit (normalised) |
|---|---|---|
| usable poses / s | **55.60** | 54.30 |
| p95 pipeline latency | **31.00 ms** | 42.81 ms |
| first usable pose | **2021 ms** | 2874.9 ms |
| camera frames dropped | **0** | 1 |
| unusable output | **0.11%** (2/1782) | 4.3% (non-normal) |
| thermal serious / critical | 0 s / 0 s | 0 s / 0 s |
| CPU per 30 s | ~59 s | **20.97 s** |

**XRSLAM matches or beats ARKit on every output-quality axis measured in a 30 s
window. It costs about 3× the CPU** — ARKit runs on dedicated silicon. That gap
is a battery and long-duration thermal question, and it is unresolved (§6).

Both arms are camera-limited at 60 fps: neither is the bottleneck. The earlier
"XRSLAM is 2.04× slower" framing was an artefact of the live channel being
hard-wired to `cameraRateHz: 30`, which capped it at 30 fps regardless of engine
speed.

## 4. Speed work: what paid, what didn't

Per-frame cost at 1920×1440, measured on device by instrumenting upstream's
`OpenCvImage` (instrumentation has since been removed):

| stage | 640×480 | 1920×1440 |
|---|---|---|
| CLAHE | 0.5 ms | 3.3 ms |
| build pyramid | 0.3 ms | 2.0 ms |
| KLT track | 1.1 ms | 2.3 ms |
| **GFTT detect** | **2.4 ms** | **20.3 ms** |
| front end total | 4.3 ms | 27.9 ms |

Detection is **73%** of the budget and scales with pixel count (8.5× for 9×
the pixels). `GFTTDetector::create(200, 1e-3, 20, 3, true)` — a `qualityLevel`
of 1e-3 collects a hundred thousand candidates on a 2.76 MP frame to keep 200.

**Levers that paid, both lossless and both upstream's own:**

1. `XRSLAM_ENABLE_THREADING` — upstream's switch, cross-platform, `XRSLAM_IOS`
   left OFF. The vendored production artifact has `threading: false`.
2. `sliding_window.tracker_frequent` 1 → 2 — upstream's own YAML key for how
   often the tracker re-detects. Default 1 is right at the 640×480 this config
   was tuned for; at 1920×1440 every frame over-supplies corners.

Replay throughput, unpaced, full resolution:

| | fps | ATE SE(3) | scale |
|---|---|---|---|
| non-threaded, frequent=1 (baseline) | 28.02 | 2.60 cm | 4.13% |
| threaded, frequent=1 | 34.06 | 2.73 cm | 2.80% |
| threaded, frequent=2 | **54.34 / 55.64** | 2.61 / 3.02 cm | 1.67 / 2.92% |
| threaded, frequent=3 | — (run aborted) | 3.81 cm | 3.84% |

Two samples are given for frequent=2 because **threading makes runs
non-deterministic**: worker interleaving varies. Accuracy at frequent=2 is
unchanged within that spread, not improved — an earlier claim that it improved
accuracy is withdrawn. frequent=3 is past the knee: clearly worse, and it starts
emitting non-finite poses.

A back-to-back A/B on a thermally soaked device (same hour, same binary, only
the `.a` differing) isolates threading:

| | production `.a` | threaded `.a` |
|---|---|---|
| fps | 21.49 | **51.64 (2.40×)** |
| CPU | 121.7 s | **72.2 s (−41%)** |
| ATE SE(3) | 3.19 cm | **2.51 cm** |
| poses | 1646 | 1641 |

Threading is not buying speed by dropping work: pose counts match and accuracy
improves. It is also markedly more heat-tolerant (the non-threaded arm fell from
28.02 to 21.49 fps once the device was hot; the threaded one from 55.64 to
51.64).

**Levers that did not pay, each refuted by measurement, not argument:**

- Compile flags: already at upstream parity (`-O3 -DNDEBUG`; Apple disables
  `-march` upstream too).
- OpenCV NEON: already on. OpenCV 4.0.1 uses `CV_SIMD128` / `v_float32x4` in
  `calcMinEigenVal` / `calcHarris` / `cornerEigenValsVecs`. An earlier claim
  that 4.0.1 lacked NEON was wrong — it came from grepping OpenCV 5.0.0's macro
  names against the wrong tree.
- OpenCV thread count: already 6 of 6 CPUs, nothing limits it.
- **Adding `cv::parallel_for_` to `cornerEigenValsVecs`** (absent in 4.0.1 *and*
  in today's master; rows are independent so it would be bit-identical): refuted
  by measuring the ceiling. `boxFilter` and `Sobel` already go through
  `parallel_for_`, and on this device at this image size they show **zero
  speedup, slightly negative**, 1 → 6 threads. These operators are
  memory-bandwidth bound at 2.76 MP; spreading the work buys nothing. Do not
  spend a modified OpenCV on this.
- Pyramid rebuild: does not happen; `calcOpticalFlowPyrLK` consumes the
  prebuilt `image_pyramid`.
- `cv::undistort` map rebuild: never triggered; ARKit is pinhole,
  `camera_distortion_flag: 0`.

No published speedup was found to replicate: `basalt-monado` / `basalt-xr` carry
XR performance work but Basalt is out (§5); the "selective image pyramid" method
is **US patent 12148128** and carries FTO risk.

## 5. Basalt: out, and why

At production pixels Basalt needs **58.0 ms/frame** against a 33.3 ms budget at
30 fps — it does not clear even the thermal-fallback gate, let alone 60 fps.

Its cost model (two resolutions, same recording) shows a different shape from
XRSLAM's: 95% of Basalt's per-frame wall time scales with pixel count, and its
core utilisation *falls* from 3.90 at 640×480 to 1.59 at 1920×1440 — roughly
47 ms of serial work at full resolution. There is real headroom there
(parallelising it could reach ~43 fps), but it is not worth spending, because:

**Basalt's scale collapses at low resolution, and it is structural.** Two
control experiments:

| Basalt | features | scale error | ATE SE(3) |
|---|---|---|---|
| 640×480, grid 40 | 192 | 54.4% | 41.23 cm |
| 640×480, grid 20 | 768 (×4) | 46.2% | 30.45 cm |
| 1920×1440, grid 40 | 1728 | **6.06%** | 6.06 cm |

Quadrupling feature density moves scale error by 8 points. Density is not the
driver; angular resolution is (`fx` 1348 → 449 px). **XRSLAM on the identical
640×480 input holds 5.3% scale and 2.82 cm**, so 640×480 carries enough
information — Basalt's estimator is what degrades. Basalt is fast where its
scale is unusable and unusable where it would need to be fast.

Two isolation runs died of OOM (640×480 grid 13, 1920×1440 grid 120), so
"angular resolution is the driver" rests on the trend, not a clean isolation.

Basalt's live memory is flat (188 MB over 95 s), unlike XRSLAM's (§6).

## 6. The open blocker: memory, and four wrong diagnoses

**XRSLAM with threading plus the observability patches leaks ~41 MB/s in the
live channel and is jetsam-killed in 55–65 s.** Every 30 s result in §3 was
taken inside that window. Nothing above should be called shippable until this
is closed.

The heartbeat now carries `footprint_mb` (a killed run leaves no receipt, so the
receipt's peak footprint never existed for exactly the runs that needed it):

```
t=  0s   28.8 MB      t= 45s  1658.7 MB
t= 10s  383.5 MB      t= 65s  2736.3 MB  → killed
```

Bisected by swapping only the `.a`, same bench binary, same camera path:

| library | live memory |
|---|---|
| production (non-threaded) | **213 MB flat, 100 s** |
| pure threading (production's two patches + `XRSLAM_ENABLE_THREADING`) | **160 MB flat, 95 s** |
| threading + the three observability patches | **41 MB/s, dies ~60 s** |
| the same with the queue read made lock-free | **still leaks** |
| Basalt (control) | 188 MB flat, 95 s |

So it is the observability patches, in the live path specifically. But note the
mirror image: **pure threading survives live and dies on unpaced replay**
(upstream's frame queue has no bound — that is what the back-pressure was for),
while the patched library survives replay and leaks live. Each configuration
works in one channel and fails in the other.

Four hypotheses were raised and each was refuted by the next measurement:
the preview tap (it is 10 Hz, decimated 4×, drops when busy — 1.7 MB/s
ceiling); `tracker_frequent=2` (frequent=1 dies sooner); the stationary
never-initialising case (an initialised run died just as fast); and lock
contention on `Worker::lock()` from polling the queue depth (making the read
lock-free changed nothing). The mechanism is still unknown. Do not trust a fifth
hypothesis that has not been measured.

Long-duration thermal was never measured: every long run died of memory first.

## 7. Bugs fixed along the way

All in the bench, all validated, all kept in the tree:

- **`frames.bin` was mapped whole, once per frame.** A 4.4 GB archive with
  `Data(contentsOf:options:.mappedIfSafe)` — replay could not even reach the
  preparation stage. Now reads only the frame's byte ranges
  (`FrameStreamReader`). A second site cached the whole mapped stream in a
  dictionary.
- **No autorelease pool in the replay loop.** Each decode allocates its luma and
  chroma planes plus a copy — several MB that Foundation returns autoreleased,
  accumulating for the whole recording.
- **The read-at-recording-size fix had been applied to one arm only.** Basalt
  fed a full-size plane into the HEVC decoder and failed at preparation, which
  is why the Basalt 640×480 point was missing — not a device disconnect. Both
  arms now share `loadReplayImageAtEngineSize`.
- **A dead engine hung the replay silently.** Fourteen minutes of a full queue,
  a stale heartbeat, and nothing in any artifact. Now fails as
  `replay_engine_stalled_camera_queue_full_no_pose_progress` after 20 s without
  pose progress.

## 8. Health signalling: what upstream lacks and what was added

Upstream reports no health at all: `SYS_CRASH` exists in the enum and **nothing
in the tree ever assigns it**, so a run that emitted a degenerate quaternion
still reported `TRACKING_SUCCESS`. ARKit, by contrast, drops to a non-normal
state 4.3% of the time and production already waits on that.

Added as `Vendor/patches/xrslam_pending_worker_frames.patch` (read-only, no
algorithm change, declared outside the frozen `XRSLAM.h` so the public ABI
header stays byte-identical):

- **Divergence flags** — VINS-Mono's `Estimator::failureDetection()`, ported
  verbatim *including which conditions upstream leaves disabled* (the
  little-feature and big-delta-angle checks are commented out there). Active:
  `‖ba‖ > 2.5`, `‖bg‖ > 1.0`, translation jump > 5 m, vertical jump > 1 m.
  VINS reboots the estimator on a hit; this only reports, because upstream
  XRSLAM has no recovery path.
- **Sustained-divergence timer** — ORB-SLAM3's `RECENTLY_LOST` shape, with its
  inertial `time_recently_lost(5.0)`; an isolated hit is not a failure.
  Voxel-SLAM's consecutive-degeneration rule was *not* copied: it is
  LiDAR-inertial and its constant could not be read from the source.
- **Ingest counters** — how many IMU samples and camera frames actually reached
  the estimator, because both of upstream's pairing failure paths are silent.

Measured: divergence flags fired **0** times while 3 of 1697 poses were
degenerate. The two are different failure modes — the estimator was healthy and
those poses are safe to skip. Per-pose validity checking (already in
`XRSLAMPoseAdapter.makeTimedPose`) is what catches them.

**These patches are also what leaks (§6).** They are observability, not
function. If the leak cannot be closed cheaply, shipping pure threading and
doing per-pose validity checking on the Swift side is the cheaper path.

## 9. An inconsistency for the owner to settle

`live-soak` treats **one** non-finite pose as fatal (`non_finite_pose` → the
whole run is `invalid`); the replay channel records 1-in-1651 non-finite and
does not flip its verdict. Same fact, two standards. Relaxing the live gate
would make a failing arm pass, so it was deliberately **not** changed here. The
product question is whether one bad pose in ~900, which the consumer skips, is
acceptable.

## 10. Repository state

`main` of this branch is left at the **production artifact**
(`libxrslam_generic_4beb1a9.a`, sha `fdc75c99…`, `threading: false`) with
`verify_vendor.sh` green. `verify_vendor.sh` had been red since the production
artifact was swapped in on 08-31 — only the `.a` hash had been updated, not the
receipt pin or the receipt-semantics assertions; both are fixed, and the
`zero_inlier_mask` patch is now pinned alongside the lifecycle patch.

`sliding_window.tracker_frequent` is left at upstream's default. Its win is
measured **only against the threaded library on replay**; its effect on the
shipped non-threaded library was never measured under comparable thermal
conditions, so it is not carried in the tree.

Experimental artifacts, outside the repo:

| file | what |
|---|---|
| `~/Developer/xrslam-4beb1a9-thr` | build worktree, pinned 4beb1a9, deps as local tarballs |
| `~/Developer/xrslam-threading-artifact/pure_threading.a` | threading + production's two patches, **no leak, no back-pressure** |
| `~/Developer/xrslam-threading-artifact/mine.a` | the above + three observability patches, **leaks live, works on replay** |
| `~/Developer/xrslam-threading-artifact/threading_lockfree.a` | lock-free queue read attempt; still leaks |

Rebuild recipe: `cmake -S . -B build-thr2 -G Ninja` with
`XRSLAM_IOS_OVERRIDE=1 XRSLAM_IOS=OFF XRSLAM_STATIC_INTERFACE=ON
XRSLAM_THREADING_OVERRIDE=1 XRSLAM_ENABLE_THREADING=ON XRSLAM_FP_CONTRACT=off`,
`CMAKE_CXX_FLAGS="-Dceres=pw_xrslam_ceres_1_14 -ffp-contract=off -fno-fast-math
-fchar8_t -fvisibility=hidden -fvisibility-inlines-hidden"`, then `libtool
-static` over interface + core + the two extras + localization + yaml-cpp.
`OPENCV_ROOT` is **ignored** by this tree; it fetches OpenCV 4.0.1's official
iOS framework itself.

New launch flags: `-PWLiveFullResolution`, `-PWPaceReplay`, `-PWHalfFrameRate`,
`-PWTrackerFrequent N`.

## 11. Next, in order

1. **Close the leak.** Bisect the three observability patches one at a time
   against the live channel; `pure_threading.a` is the known-good floor. Or
   drop them and do per-pose validity in Swift.
2. **Long-duration thermal**, once a configuration survives minutes. The open
   question is whether ~3× ARKit's CPU throttles the device over a real
   session. Stationary is a fair and conservative test — nobody waves a phone
   for ten minutes, and initialisation forces per-frame detection, which is the
   most expensive path.
3. **EuRoC with ground truth.** Every accuracy number here is agreement with
   ARKit over a 4.65 m path, not accuracy. The dataset is at
   `~/Developer/euroc` (V1_01/02/03; the prepare script hardcodes
   `MH_01_easy` and needs parameterising). Nothing in this document answers
   "is XRSLAM more accurate than ARKit" — that channel is the only one that can.

## Operational notes

- Every launch purges prior self-test runs. **Pull artifacts immediately after
  each run**; one XRSLAM `poses.tum` was lost this way and had to be re-measured.
- Comparisons made hours apart are not comparable: the same library measured
  28.02 fps cold and 21.49 fps hot. Alternate A/B in the same hour.
- `/tmp` is cleared mid-session. Evaluation outputs belong in
  `~/Developer/viobench-recordings/`.
- Read artifacts from the device container; do not launch the app to read data.
