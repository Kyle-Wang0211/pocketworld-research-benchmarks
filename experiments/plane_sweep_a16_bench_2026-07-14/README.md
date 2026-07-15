# A16 tiled pure-A plane-sweep benchmark

This benchmark verifies the latest certified-floor ownership gates from the pure-A plane-sweep experiment on the actual iPhone 14 Pro (iPhone15,2 / Apple A16 GPU). It consumes only images, calibrated intrinsics, known poses, and the certified floor plane. No LoFTR, detector-free matcher, LiDAR, or sceneDepth output is consumed.

## Frozen fixture

- Source research revision before this run: `f2fc9a182fd851979499384b967756b8df777782`
- Fixture manifest SHA-256: `f58371097e0e840b01402ca611fc6f1d8072514e0bbf2d2bfae17dbadce9c59b`
- Generator SHA-256: `5d7ce3a4ff3a5c873fadfe284c3cf7a052f19a4acfce033f3b59cc65a958c1a3`
- iOS implementation SHA-256: `8700015b0d18ebfcd0a39de61a419a70a1f8103f15d98cf2b9311a179af85348`
- Surface: `floor_0`
- Tile: 64 candidates at 5 cm spacing
- Views: 38 resource frames, base maximum 10, strict rescue maximum 48
- Gates: ZNCC >= 0.70, >=3 mutually compatible views, >=5 degrees parallax; strict rescue also requires ZNCC >= 0.8500471980155323 and >=10.241134230890212 degrees.
- Hypotheses per certified-floor point: 1. The structural-plane owner does not compete against arbitrary parallel-depth births.

The generated PNG and binary fixture resources are deliberately ignored because they are reproducible from the generator and consume 255 MiB. The small manifest and device evidence are tracked.

## Commands

```sh
/opt/homebrew/bin/python3.11 -m unittest experiments/plane_sweep_a16_bench_2026-07-14/test_generate_fixture.py -v
/usr/bin/time -lp /opt/homebrew/bin/python3.11 experiments/plane_sweep_a16_bench_2026-07-14/generate_fixture.py
cd experiments/plane_sweep_a16_bench_2026-07-14/ios_bench
xcodegen generate --spec project.yml
xcodebuild -project PWPlaneSweepBench.xcodeproj -scheme PWPlaneSweepBench -configuration Profile -sdk iphoneos -destination 'generic/platform=iOS' -derivedDataPath build CODE_SIGNING_ALLOWED=YES build
xcrun devicectl device install app --device 1B290474-D354-5B4C-AAB0-0805AC5DC832 build/Build/Products/Profile-iphoneos/PWPlaneSweepBench.app
xcrun devicectl device process launch --device 1B290474-D354-5B4C-AAB0-0805AC5DC832 --terminate-existing com.kyle.PocketWorld.PlaneSweepBench
xcrun devicectl device copy from --device 1B290474-D354-5B4C-AAB0-0805AC5DC832 --domain-type appDataContainer --domain-identifier com.kyle.PocketWorld.PlaneSweepBench --source Documents/planesweep_bench/latest.json --destination /tmp/pw_c_latest.json
```

The app was installed and launched detached. No debugger or console was attached.

## Device verdict

Run evidence: `runs/iphone15_2_floor_owner_rescue48_20260715_131436/`.

- Decision: `PASS_A16_FLOOR_OWNER_RESCUE_PARITY`
- Accepted parity: exact
- Base accepted parity: exact
- Rescue accepted parity: exact
- Valid-mask mismatches: 0
- Expected and actual accepted indices: 20, 22, 24, 27, 36, 48, 59, 61, 62
- Base indices: 22, 24, 27, 61
- Strict-rescue indices: 20, 36, 48, 59, 62
- Normalized-patch values compared: 46,501
- Mean absolute patch error: 0.0000044642761535969846
- Maximum absolute patch error: 0.00016203522682189941
- GPU dispatch-and-wait: 70.24 ms cold, 42.84 ms and 41.94 ms warm
- End-to-end: 2.565 s cold, 1.396 s and 1.389 s warm
- Decode portion: 2.483 s cold, 1.342 s and 1.339 s warm
- Peak sampled RSS: 141,148,160 bytes
- Resident 4K textures: 1
- Final thermal state: nominal

The shader is not the end-to-end bottleneck. Sequential PNG decoding dominates the fixture runtime; product integration should reuse capture-time textures or the existing local thumbnail/texture cache instead of re-decoding PNGs.
