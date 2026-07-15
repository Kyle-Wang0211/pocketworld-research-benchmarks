# Detector-free known-pose depth sweep: A16 backend parity

This experiment validates a self-developed, model-free, known-pose multiview
depth-sweep contract on an iPhone 14 Pro. It is a backend benchmark, not an
Apple-only product architecture and not yet a full-scene production integration.

## Cross-platform boundary

The product route is:

1. Dart owns capture/finalize orchestration, durable job state, progress, and
   selection UI on every client.
2. C++17 behind a C ABI owns the depth-sweep contract, view selection, birth
   gates, tile scheduling, and deterministic result semantics.
3. Platform GPU code is a thin compute backend: Metal on Apple, Vulkan compute
   on Android and HarmonyOS, and WebGPU (with a CPU fallback) on Web.
4. Swift/Kotlin/ArkTS only bridge buffers and lifecycle events. They do not own
   reconstruction policy or thresholds.

The current benches contain no Swift source. Their Objective-C++ shells exist
only to run and measure native Metal and Dawn on real hardware. The reusable
parity semantics live in `shared/portable_depth_contract.h`, and the single-source
cross-platform kernel lives in `shared/known_pose_depth_sweep.wgsl`. The next
product step is to put the sweep/tile engine behind the existing Aether C ABI
and let Dart call it through FFI.

Moving the per-pixel sweep itself to Dart would reduce GPU throughput and is not
the cross-platform solution. Sharing orchestration in Dart and numeric work in
C++/GPU preserves both one product behavior and native performance.

## Frozen algorithm contract

- input: cap56 grayscale frames, camera intrinsics, and known poses;
- no learned model or training data;
- no LoFTR or any third-party matcher output;
- no LiDAR or sceneDepth data;
- 128×72 diagnostic tile, 48 inverse-depth samples, seven source views;
- 5×5 ZNCC patches, best four views, `ZNCC >= 0.75`, depth margin `>= 0.03`;
- OpenCV-compatible 1/32-pixel bilinear coordinate quantization;
- all product births, accepted depth indices, and view counts must match exactly.

A rejected candidate has no product-point identity. Its internal argmax remains
an explicit diagnostic, but cannot fail product-point parity. Score tolerances
cover floating-point evaluation order only and never permit a birth or accepted
depth mismatch.

## True-device results

Both runs used `iPhone15,2`, iOS 26.5, Apple A16 GPU, a signed Profile build,
detached `devicectl` launch, and App-container result recovery.

| Fixture | Manifest SHA-256 | Expected/actual births | Accepted depth mismatch | View mismatch | Diagnostic rejected argmax mismatch | A16 GPU cold | Peak RSS | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| cap56 ref10 | `4a74e697da3a94022465f26b526993d7c710c90f34abf6404e3d2f8ea09a8f42` | 842/842 | 0 | 0 | 1 | 28.85 ms | 56.7 MB | PASS |
| cap56 ref17, external validation | `ccb495b7329cf4d7563a63b704bce58fd608f793dba4b3e7eae07feb7f975945` | 1340/1340 | 0 | 0 | 1 | 28.64 ms | 56.5 MB | PASS |

The same ref17 contract was then executed by the single WGSL kernel through
Dawn on the iPhone 14 Pro. Dawn selected Apple A16 GPU / Metal internally:

- 1340/1340 product births, accepted-depth mismatch 0, view mismatch 0;
- measured wall times 20.96, 20.78, and 20.53 ms after one 37.19 ms warmup;
- one-time WGSL/Tint pipeline compilation 286.94 ms;
- sampled RSS 89.8 MB and final thermal state nominal;
- learned model, third-party matcher output, LiDAR, and sceneDepth all absent.

This validates the production shader language and runtime boundary on Apple.
Android/HarmonyOS Vulkan and browser WebGPU executions remain required; the
WGSL source and birth contract no longer need a platform-specific rewrite.

The ref17 fixture was frozen and generated only after the v2 parity semantics
were registered. Its portable float32 birth mask also matched the legacy host
baseline exactly before the device run.

Evidence:

- `runs/iphone15_2_cap56_ref10_v2_20260715_143711/`
- `runs/iphone15_2_cap56_ref17_v2_20260715_143839/`
- `runs/m3pro_dawn_cap56_ref17_v1_20260715_1449/`
- `runs/iphone15_2_dawn_cap56_ref17_v1_20260715_145351/`

Each directory contains the fixture manifest, signed Profile build log,
installation and detached-launch JSON, and the recovered device result.

## Reproduction

```sh
/opt/homebrew/bin/python3.11 -m unittest test_generate_fixture.py -v
clang++ -std=c++17 -Wall -Wextra -Werror \
  shared/portable_depth_contract_test.cpp \
  -o /tmp/pw_portable_depth_contract_test
/tmp/pw_portable_depth_contract_test
/opt/homebrew/bin/python3.11 generate_fixture.py --reference-index 17

cd ios_bench
xcodegen generate --spec project.yml
xcodebuild -project PWDetectorFreeBench.xcodeproj \
  -scheme PWDetectorFreeBench -configuration Profile \
  -destination 'generic/platform=iOS' \
  -derivedDataPath build/DerivedData \
  -allowProvisioningUpdates build \
  CODE_SIGN_STYLE=Automatic DEVELOPMENT_TEAM=26AH7V448L
```

Installation and launch intentionally use `devicectl` without `--console`:

```sh
xcrun devicectl device install app \
  --device 1B290474-D354-5B4C-AAB0-0805AC5DC832 \
  build/DerivedData/Build/Products/Profile-iphoneos/PWDetectorFreeBench.app
xcrun devicectl device process launch \
  --device 1B290474-D354-5B4C-AAB0-0805AC5DC832 \
  --terminate-existing com.kyle.PocketWorld.DetectorFreeBench
```

## Scope of the verdict

This proves product-point parity and bounded A16 cost for two cap56 reference
tiles. It does not yet prove full-resolution tiled throughput, sustained thermal
behavior, Android/Harmony Vulkan parity, WebGPU parity, or full-scene quality.
Those remain required before production enablement.
