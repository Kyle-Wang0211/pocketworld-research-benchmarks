# XRSLAM front end on the GPU (WGSL/Dawn) — sources, gates, results

The XRSLAM CPU front end costs 27.9 ms/frame at 1920×1440 on an iPhone 14 Pro, 73 % of it in
`goodFeaturesToTrack`. This directory holds everything needed to reproduce the GPU port of that front
end and the bench campaign that measured it against production ARKit on the same device.

The rule the port was written under: **bit-exact, not approximately equal**. Every kernel is a port of
the OpenCV 4.0.1 (`c9ad5779`, Apache-2.0) expression order, not of the algorithm's textbook form — the
CLAHE redistribution loop, `FixPtCast` rounding, the NEON accumulation order in the KLT solver, the
`double` accumulator inside `boxFilter`, even `GFTTDetector` returning `response = 0` (which makes
XRSLAM's `std::sort` permute equal keys, and the Poisson filter downstream is order dependent).

## Layout

| path | what |
|---|---|
| `wgsl/` | the kernels. `gftt_common`/`lk_common` are the shared headers; the rest are one kernel each: CLAHE (hist/lut/interp), `pyrdown`, `scharr`, `sobel_dxdy`, `harris_box` (+ `harris_fused`, Sobel folded in), `gftt_max`/`thr`/`find`, `lk_track`(`_wg`), `pack_u8`/`unpack_u8`, `fp_selfcheck` |
| `tools/gen_wgsl_header.py` | bakes `wgsl/*.wgsl` into `aether_cpp/tools/pw_gpufe_wgsl.h` — run it after every kernel edit |
| `tools/*_cpu_ref*.cpp` | OpenCV 4.0.1 reference dumps the GPU is compared against, byte for byte |
| `tools/lk_deriv_path_probe.cpp` | proves upstream LK gives identical results with and without prebuilt derivatives |
| `tools/clahe_*.py` | the CLAHE ±1 hunt (enumerates rounding variants until one matches) |
| `patches/xrslam-4beb1a9-gpu-frontend.patch` | the engine side: `GpuImage : OpenCvImage`, the prefetch call in `XRSLAMManager::PushImage`, the `XRSLAM_GPU_FRONTEND` option. Apply to openxrlab/xrslam `4beb1a9` on top of the threading back-pressure branch |
| `scripts/build_gpufe_ios.sh` | builds the front end for iOS into `libpw_gpu_frontend_ios.a` |
| `docs/PLAN.md` | the M1–M4 plan and the three-level lossless gate |
| `docs/CAMPAIGN_RESULTS.md` | every run, in order, with its verdict — including the ones that failed |

The host library itself (`pw_gpu_frontend.cpp/.h`, the Dawn harness, the self-test and probes) lives in
`Aether3D/aether_cpp/tools/` because it links Dawn; this directory is its shader and reference side.

## Gates (all three, in this order, or the number means nothing)

1. **Mac**: `aether_gpufe_selftest` — CLAHE bytes, ordered detections, LK forward/reverse, the packed
   pyramid, all against the 4.0.1 dumps. Strict math must be on (`AETHER_STRICT_MATH=1`); with fast
   math the fused Harris kernel differs from the split one in 430 313 of 2 764 800 pixels.
2. **Device replay**: `scripts/pw_chain_gpufe_replay.sh` with `AUDIT=1` — every 50th frame re-runs the
   CPU path on-device and compares. Also reports ATE against the CPU baseline.
3. **Device live**: `scripts/pw_chain_gpufe_live.sh` — 300 s (the product's capture cap), verdict
   computed against the same-device ARKit reference run, metric by metric.

Check the receipt's `eng_sha` against the build you meant to test before reading any run: the live
chain does not install (pass `INSTALL=1`), and a run was once read off the previous app.

## Where it landed (2026-09-08, `run-470abebc`, iPhone 14 Pro, charging)

| | CPU front end | GPU front end | ARKit |
|---|---|---|---|
| p95 pipeline latency | — | **42.0 ms** | 55.5 ms |
| CPU core-equivalent | 1.9 | **0.80** | 0.80 |
| poses/s | 10.4 | 28.4 | 59.9 |
| tracker thread | 27.9 ms | 10.7 ms | — |

Bit-exactness held on device throughout (CLAHE 33/33 frames, detection 33/33, 0 fallbacks, ATE
2.17 cm vs the CPU baseline's 2.39). Latency and CPU now match ARKit; pose rate does not, because the
camera channel is 30 fps and a 60 fps channel needs the throttled GPU to finish CLAHE + detection in
16.7 ms (it takes ~19). The remaining gaps are power (173 s in `serious` vs ARKit's 0) and 10 MB of
footprint, not numerics.

The single largest fix was not in a kernel: under overload the engine's producer-side gate stalls the
feeder thread, sensor events pile up in the bench's serial handoff, and latency becomes queue depth
(864 ms). Submitting only the newest camera frame of each drained batch (`-PWXrslamDropStaleCamera`,
IMU untouched) turns the collapse into graceful degradation: 864 → 42 ms.
