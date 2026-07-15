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

## Cross-platform strict wall scale rescue (2026-07-15)

The required wall path now uses a shared WGSL patch-normalization kernel through Dawn,
with the clique, parallax, and unique-depth semantics in portable C++. The iOS app is only
a detached device harness: Apple executes the WGSL through Dawn's Metal backend, while the
same kernel can run through Vulkan on Android/HarmonyOS. It consumes no learned model,
matcher output, LiDAR, or sceneDepth.

The frozen cap50 `wall_1` tile 0 contains 64 candidates and the four highest-density strict
rescue additions. Both physical scales evaluate the center plane and parallel alternatives
at -10/-5/+5/+10 cm. The baseline uses a 6 cm patch diameter, 4-view clique, 10-degree
parallax, and 0.02 unique-depth margin. The rescue uses a 12 cm patch diameter, 5-view
clique, 18-degree parallax, median ZNCC >= 0.90, and 0.06 unique-depth margin. Every
pairwise clique edge still passes ZNCC >= 0.80.

```sh
/opt/homebrew/bin/python3.11 experiments/plane_sweep_a16_bench_2026-07-14/generate_wall_scale_rescue_fixture.py
clang++ -std=c++17 -O2 experiments/plane_sweep_a16_bench_2026-07-14/shared/wall_scale_rescue_contract_test.cpp -o /tmp/pw_wall_contract_test
/tmp/pw_wall_contract_test
cd experiments/plane_sweep_a16_bench_2026-07-14/ios_dawn_wall_bench
xcodegen generate --spec project.yml
xcodebuild -project PWWallPlaneSweepDawnBench.xcodeproj -scheme PWWallPlaneSweepDawnBench -configuration Profile -destination 'generic/platform=iOS' -derivedDataPath /tmp/pw_wall_dawn_derived CODE_SIGN_STYLE=Automatic build
xcrun devicectl device install app --device 1B290474-D354-5B4C-AAB0-0805AC5DC832 /tmp/pw_wall_dawn_derived/Build/Products/Profile-iphoneos/PWWallPlaneSweepDawnBench.app
xcrun devicectl device process launch --device 1B290474-D354-5B4C-AAB0-0805AC5DC832 --terminate-existing com.kyle.PocketWorld.WallPlaneSweepDawnBench
```

Final-source run evidence:
`runs/iphone15_2_dawn_wall_scale_rescue_final_20260715_154115/`.
An immediately preceding independent device launch is retained in
`runs/iphone15_2_dawn_wall_scale_rescue_20260715_153817/` and reached the same parity verdict.

- Decision: `PASS_DAWN_A16_WALL_SCALE_RESCUE_PARITY`
- Baseline accepted indices: exact 7/7
- Strict-rescue accepted indices: exact 5/5
- Final union accepted indices: exact 11/11, including all four new tile points
- Valid-mask mismatches: 0
- Normalized-patch values compared: 442,584
- Mean / maximum absolute patch error: 8.83e-7 / 9.40e-5
- Warm wall tile: 20.41, 21.01, and 21.62 ms
- WGSL pipeline creation: 32.00 ms on the final-source run
- Peak sampled RSS: 94,208,000 bytes; one cropped frame resident at once
- Final thermal state: nominal

This closes A16 backend parity for the strict wall rescue without changing any frozen
baseline birth on the representative cap50 tile.

The second-capture holdout is cap51, not cap56. cap51 has six certified walls over all 81
JPEGs still present from its 105-frame ledger; the host union grows 111 -> 118 with all
runtime non-regression checks passing. cap56 contains no wall meeting the frozen structural
support spans and is therefore not wall-evaluable.

For an independent A16 fixture, cap51 `wall_2` tile 6 contains 64 candidates with host
baseline `[]` and strict rescue/union `[16]`. Generate it with:

```sh
POCKETWORLD_CAP51_PHOTOS=/tmp/pocketworld_cap51_photos_20260715 \
  /opt/homebrew/bin/python3.11 \
  experiments/plane_sweep_a16_bench_2026-07-14/generate_cap51_wall_scale_rescue_fixture.py
```

Two detached device launches are retained in
`runs/iphone15_2_dawn_cap51_wall2_tile6_20260715_160344/` and
`runs/iphone15_2_dawn_cap51_wall2_tile6_rep2_20260715_1604/`. Both report exact
baseline/rescue/union parity and zero validity mismatches over 455,625 normalized patch
values. Mean / maximum absolute error is 2.87e-6 / 4.28e-4; best-of-three wall time is
40.73 ms and 64.15 ms, peak sampled RSS is 117.9 MB and 110.1 MB, and thermals remain
nominal. The source JPEG hash for every cropped resource is pinned in the fixture manifest.

These cap50 and cap51 device runs are representative 64-candidate kernel-parity tiles, not
full-capture device executions. B's second-capture host holdout and C's two-capture A16 tile
parity are complete; shared product integration remains open. Ceiling remains non-blocking.
