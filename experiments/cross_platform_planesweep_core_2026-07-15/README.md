# Cross-platform structural plane-sweep core

This directory is the host-verifiable base for B and C. The production source
lives in `Aether3D-cross/aether_cpp`; these scripts compile that exact C ABI and
compare it with the frozen cap50/cap51 research outputs.

The route consumes only first-party sparse XYZ, the known floor plane, JPEGs,
intrinsics, and camera poses. It consumes no LiDAR, scene depth, learned matcher,
or LoFTR-derived output. Sparse points are never removed. Only certified walls
may own new plane-sweep births; ceiling is not release-blocking.

Current host evidence:

- cap50 wall fit: six candidates, five certified; exact angle, plane, support,
  coverage, and certification parity with the frozen Python reference.
- cap51 wall fit: six candidates, six certified; exact parity.
- cap50 full-wall C ABI: 38 baseline births retained, 14 strict rescue births,
  46-point union; zero missing/unexpected points.
- cap51 full-wall C ABI: 111 baseline births retained, 118-point union; zero
  missing/unexpected points across six walls.
- Representative A16 Dawn/WGSL tiles reproduce the CPU birth sets exactly.

Run the shared wall-fit parity check:

```sh
/opt/homebrew/bin/python3.11 \
  experiments/cross_platform_planesweep_core_2026-07-15/verify_structural_plane_fit_c_abi.py \
  --aether-root /Users/kaidongwang/Developer/Aether3D-cross \
  --output experiments/cross_platform_planesweep_core_2026-07-15/runs/structural_plane_fit_cap50_cap51.json
```

Android/HarmonyOS device optimization is intentionally deferred until hardware
exists. The shared C++ C ABI is the portability boundary; Dawn maps the same
WGSL to Metal or Vulkan when that backend is available, with the deterministic
CPU scorer remaining the fallback. Web is view-only and may use WASM/WebGPU.
