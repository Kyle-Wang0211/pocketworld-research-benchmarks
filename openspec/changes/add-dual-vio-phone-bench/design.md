# Design

## Fairness boundary

Basalt and XRSLAM share the same AVFoundation/CoreMotion capture contract, EuRoC mono
loader, run durations, system sampler, metric definitions, artifact finalizer,
and evaluator. Live resource runs execute one engine at a time. Replay runs use
the same frozen input manifest and execute each engine independently. Live runs
are not the same physical trajectory and cannot select an accuracy winner.

Their shared live pixel contract is full-range NV12 luma at 640x480, zero output
rotation, and stabilization disabled. This deliberately differs from XRSLAM's
sample-only BGRA-to-OpenCV-gray path so both engines receive the same grayscale
pixels; every run records that deviation and the realized active format. ARKit
is not an exact-input arm: it owns its private Apple sensor chain and mirrors the
current product configuration. It is a same-device system reference, never
ground truth or a raw-input algorithm A/B.

## Binary isolation

Basalt pins OpenCV 4.12.0 while XRSLAM pins OpenCV 4.0.1. Putting both static
closures into the app Mach-O would risk duplicate definitions or ABI binding.
The project instead builds one app and two private two-level dynamic frameworks:

- `VIOReplacementBench` / `com.kyle.viobench`
- `PWBasaltEngine.framework`, exporting only `basalt_bench_*`
- `PWXRSLAMEngine.framework`, exporting only `xrslam_bench_*`

The app links both inert adapters, but the process-wide run lease permits only
one active sensor/session owner and only the selected native session is created.
On success the selected native handle is explicitly destroyed before the lease
is released; every error/abort path enforces the same ordering with a defer. A
stopped wrapper therefore cannot retain process-global upstream ownership into
the next arm or next run.
Every run hashes the app executable and its selected engine artifact. `uses_arkit`
means an ARSession was constructed; it does not mean the system framework is
absent from the unified binary.

The frozen XRSLAM archive contains objects built for iOS 26.2 despite an older
receipt claim, so the unified app truthfully declares iOS 26.2.

## Input adapters

For Basalt/XRSLAM, the platform layer records raw camera and CoreMotion events. Each engine
adapter reproduces its pinned upstream transport semantics. Basalt receives
gyro-timestamped IMU samples with acceleration interpolated across adjacent
accelerometer samples. XRSLAM receives separate acceleration and gyroscope
events. Its camera, acceleration, and gyroscope callbacks execute on one serial
queue and enter one bounded callback-order-preserving handoff. The native layer
forwards IMU synchronously, owns exactly one create-time preallocated grayscale
slot, and runs exactly once per admitted camera frame. Adapter-specific drops,
queue-full events, nonfinite outputs, and undelivered results are terminal
invalidity, never hidden. The ARKit adapter instead mirrors the production
ARWorldTrackingConfiguration: autofocus, gravity alignment, light estimation
off, horizontal plane detection, locked 1920x1440 high-resolution-capable
format, main delegate queue, and fresh reset/remove-anchors start options. It
records tracking, mapping, timestamp-gap, lifecycle, latency-proxy, resource,
and stop receipts without modifying Apple's estimator.

## Claims

Live soak establishes mobile throughput, latency, memory, CPU, battery proxy,
and thermal feasibility only. The live clock and resource accounting begin
before selected estimator/session initialization, and the full 300 seconds are
scored with no excluded warm-up. The common startup metric is delivery to
the app of ARKit's first normal-tracking pose or a candidate's first finite pose,
and any value above the production page's 1800 ms readiness fallback fails.
It has no ground truth and cannot establish
trajectory accuracy. EuRoC replay supplies fixed-scale SE(3) ATE/RPE evidence.
Basalt/XRSLAM and EuRoC ground truth are evaluated in the body/IMU frame:
Basalt emits `T_w_i`, XRSLAM emits official `BODY_POSE`, and camera pose is not
accepted by the scorer because a fixed alignment cannot remove its rotating
camera-to-IMU lever arm. ARKit does not accept EuRoC replay and its live
world-from-camera poses are not accuracy evidence.
Neither candidate is eligible for production or global defaults until its own gates
and the later product-shadow gates pass. Replacement also requires every
same-device live feasibility measure to be no worse than the separately run
ARKit reference arm. Because the live trajectories differ and ARKit cannot
consume the frozen replay, live accuracy superiority remains blocked until a
separate external-ground-truth experiment exists; the bench must not infer it
from candidate-vs-ARKit trajectory disagreement.

## v2 design deltas — 2026-08-30

### One monotonic domain

`mach_absolute_time` nanoseconds, everywhere. `std::chrono::steady_clock` is
banned in bench native code: on Darwin it is `CLOCK_MONOTONIC` ==
`mach_continuous_time` and includes device sleep, while `CMClockGetHostTimeClock`
and `DispatchTime.uptimeNanoseconds` exclude it. Mixing them reported the phone's
entire sleep accumulation as a latency (97 s run, 81,219,463 ms p95). Native code
calls `mach_absolute_time()` and applies `mach_timebase_info` — mach ticks are
24 MHz on arm64, not nanoseconds.

`ClockDomainInvariant` rejects any latency exceeding run elapsed plus 250 ms.
Invalid, never clamped: clamping would have hidden this defect behind a plausible
number instead of an absurd one.

### One capture, replayed

`ARFrame.capturedImage` luma at 1920x1440 is the shared input. Recording is
uncompressed — it is algorithm input, not a preview. ~2.76 MB/frame, ~23.2 GiB
for 300 s.

Known gap, to be declared and never described as verified: candidates are scored
on ARKit-conditioned imagery, since ARKit owns autofocus and exposure during the
capture. A production replacement would drive its own AVCaptureSession. One
AVFoundation cross-check recording is owed before any production shadow.

No ground truth exists for the recording, so this channel answers cross-arm
agreement, loop-closure error, static drift and coarse scale — never absolute
accuracy. EuRoC remains the only absolute accuracy channel.

### Resources by decomposition

ARKit's resource cost is measured live during the capture. Candidate cost is
measured by replay-paced 300 s with the device stationary, plus a camera term
measured once by a null run and identical for both candidates. Thermal load comes
from compute, not from the operator's arm, and replay is repeatable. Reported as
a decomposition, not as a direct measurement.

### Calibration at 1920x1440

Intrinsics come from `ARFrame.camera.intrinsics` recorded during the capture: a
hardware property describing exactly the frames being replayed, so nothing is
extrapolated. The frozen 640x480 upstream intrinsics scaled by 3 must agree
(fx 1346.903, fy 1347.432, cx 964.038, cy 722.149); disagreement means the two
formats differ by more than a scale and must halt the run. Extrinsics are a rigid
IMU-to-camera transform and stay at the upstream XRSLAM value unchanged.
Distortion stays zero, and that approximation is now worse — the same distortion
acts over three times the pixel radius.

### Upstream configs must be scaled, not tuned

Basalt's official config is tuned for 752x480 and XRSLAM's for 640x480; patch
size, pyramid depth, detection grid and feature caps are pixel-unit values.
Running them unchanged at 1920x1440 measures our port, not the algorithm. Every
changed parameter records upstream file, commit, original value, new value, scale
factor and derivation. Tuning until it runs is forbidden.
