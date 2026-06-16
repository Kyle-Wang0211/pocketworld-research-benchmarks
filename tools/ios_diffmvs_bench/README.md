# DiffMVS on-device benchmark (iOS)

Measures **per-frame latency** and **peak `phys_footprint`** (the memory figure iOS
Jetsam uses against the ~4.1GB budget) for a CoreML model, over N frames (default 414).
Model-agnostic: it reads the model's own input descriptions and feeds random inputs,
so it works for whatever final DiffMVS input signature you ship.

## Files
- `DiffMVSBench/Benchmark.swift` — core: compile+load model, build inputs, time loop, sample memory
- `DiffMVSBench/ContentView.swift` / `BenchApp.swift` — one-button SwiftUI UI
- `DiffMVSBench/DiffMVS_PLACEHOLDER.mlpackage` — tiny stand-in so the app runs **today** (NOT real timing)
- `project.yml` — XcodeGen project spec

## Build & run (fastest path)
1. `brew install xcodegen` (if needed)
2. `cd tools/ios_diffmvs_bench && xcodegen generate`
3. `open DiffMVSBench.xcodeproj`
4. Set your signing **Team** (target ▸ Signing & Capabilities), plug in an iPhone, ⌘R.
5. Tap **运行 Benchmark**. Reads median/p90/min ms-per-frame, total for 414 frames, and peak MB vs 4.1GB.

(No XcodeGen? Create a new iOS App in Xcode, drag the 3 `.swift` files + the `.mlpackage`
into the target, run.)

## STATUS: real model is bundled
`DiffMVS.mlpackage` (3.55MB, exported by `../python/pw_export_coreml.py`) is in the
target — the harness uses it automatically (placeholder is fallback).

### Mac CoreML results (real frames, 512×896, N=5) — confirm these on device
| Compute Units | median/frame |
|---|---|
| **CPU+GPU (default)** | **127 ms** |
| CPU only | 703 ms |
| ALL (ANE+GPU+CPU) | 1869 ms ⚠️ |

⚠️ **`.all` is a trap**: CoreML puts 3D-conv/grid_sample on the ANE, which can't run
them, and thrashes ANE↔GPU↔CPU. **Use CPU+GPU.** 414 frames ≈ 52s @ 127ms.
Weights 3.5MB; expect peak memory well under the 4.1GB jetsam budget — the app prints
the real phys_footprint so you can confirm on device.

## (history) Producing the model — blockers cleared
The placeholder only proves the harness/memory plumbing works. For real numbers, add
`DiffMVS.mlpackage` (the harness prefers it over the placeholder automatically).

To produce it, the PyTorch→CoreML export must clear ONE remaining op: `torch.inverse`
(the 4×4 homography inverse in `diffmvs/models/module.py:192`). It is pure camera math
(`src_proj @ inv(ref_proj)`), independent of features — so the clean fix is to **precompute
the relative transform on CPU and pass it in as a model input**, removing `aten::inverse`
from the graph. `grid_sample` already converts on coremltools 9.0; that was the old blocker.
Once exported, drop `DiffMVS.mlpackage` into `DiffMVSBench/` and rebuild.

## What the numbers mean
- **median ms/frame** at 512×896, N=5 — multiply by your real per-scan frame count.
- **peak MB** — compare to ~4198 MB (4.1GB). DiffMVS weights are ~3MB; the cost volume is
  the memory driver and scales ~linearly with pixels, so lower resolution = lower RAM.
- Toggle **Compute Units** (ALL / CPU+GPU / CPU) to see ANE vs GPU vs CPU behaviour.
