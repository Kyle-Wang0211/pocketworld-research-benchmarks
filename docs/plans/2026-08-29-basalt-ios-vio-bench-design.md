# Unified iPhone VIO Replacement Bench Design

## Objective

Determine whether the frozen Basalt or XRSLAM candidate can replace ARKit on the
tested iPhone, using exact-input replay, exclusive live feasibility, and a
production-equivalent ARKit reference arm. This benchmark is research
evidence only; it does not modify PocketWorld or authorize Basalt for production.

## Frozen identity

- Basalt upstream: `0f3b2b52c807f70ff4e2973ce253c73329eea7bc`
- Basalt headers: `aa441ba3e51050c47ba1902537792a2e4db7e43d`
- vcpkg submodule: `1e199d32ad53aab1defda61ce41c380302e3f95c`
- vcpkg registry baseline: `05442024c3fda64320bd25d2251cc9807b84fb6f`
- Official baseline configuration: upstream `data/euroc_config.json`
- XRSLAM upstream: `4beb1a942f33da9afbfae2d70e2c641cfc2bb675`
- Mobile product: `VIOReplacementBench`, bundle `com.kyle.viobench`
- Engine isolation: `PWBasaltEngine.framework` and `PWXRSLAMEngine.framework`

The Basalt algorithm sources and configuration stay unchanged. Mobile-only work
is limited to the build target, C ABI/Objective-C++ transport adapter,
instrumentation, dataset reader, and Swift UI.

## Three-arm, dual-channel experiment

### Live soak

For Basalt/XRSLAM, AVFoundation delivers monochrome camera frames and Core Motion delivers raw
gyroscope and accelerometer samples. Both are converted to one monotonic time
domain before entering the selected VIO core. The ARKit arm instead owns one
private production-equivalent ARSession and never enters either C++ session.

The app records camera/IMU input rates, every drop reason, queue residence,
service and pipeline latency, pose output rate, CPU seconds, physical footprint,
thermal-state dwell, camera pressure, low-power mode, and battery-level change.
The formal run matches the product's five-minute use limit. Its clock, CPU
accounting, and system sampler start before selected estimator/session
initialization, and all 300 seconds are scored with no excluded warm-up. First
usable pose delivery latency is a required metric and must not exceed the production AR
page's 1800 ms fallback. ARKit is timed to callback delivery of its first normal
pose; Basalt/XRSLAM are timed to publication of their first finite pose. Loss
and safety validity cover the full session and final drain.

### Ground-truth replay

The Basalt/XRSLAM arms in the same iPhone binary consume an immutable EuRoC sequence, calibration,
timestamps, IMU and ground truth. `replay-paced` follows dataset timestamps and
tests realtime behavior; `replay-max` tests maximum throughput. Accuracy uses one
SE(3) alignment with scale fixed to 1, then reports ATE and one-second RPE.

ARKit cannot accept replay and is not ground truth. A future `live-mocap` mode may evaluate live accuracy
when independently synchronized motion-capture truth is available.

## State and data ownership

One process-wide lease permits exactly one selected arm and one output directory. Sensor callbacks
never block on disk writes or UI. Start creates an atomic `started` receipt and
heartbeat. Stop first seals input, drains accepted work, stops the selected arm, flushes
artifacts and atomically replaces the receipt with `valid_pass`, `valid_fail`,
`invalid`, or `aborted`. A crash leaves the started receipt recoverable and is
classified on next launch.

## Metrics and honesty rules

The app cannot obtain calibrated watts through a public iOS API. It therefore
records `power_w: null`, battery percentage change, CPU seconds, thermal dwell
and optional Power Profiler artifact identity. Watts require an external
calibrated power analyzer.

Live runs without external ground truth report accuracy as `not_evaluable`.
Phone-only evidence is scoped to the tested device, OS, input and build and is
never used to choose a global consumer default.

A candidate cannot receive replacement eligibility merely by passing its own
absolute gates. It must also be no worse than the separately run ARKit arm on
startup delivery, live latency, transport loss, thermal dwell, footprint, CPU
time, and battery proxy, pass fixed-input EuRoC accuracy, and later pass the
PocketWorld product-shadow gates. Live accuracy superiority remains blocked
until an external-ground-truth experiment exists.

## Safety boundary

The bench has a separate bundle and data container. It never installs over,
launches, uninstalls or mutates `com.kyle.PocketWorld`. Signing and
device installation are separate gates after unsigned Release build, tests and
bundle-identity checks succeed.
