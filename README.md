# PocketWorld Research Benchmarks

This repository is the paper/research bench for PocketWorld geometry experiments.
The product app lives separately in `Kyle-Wang0211/pocketworld`.

## Current Sealed Product Baseline

- DA3 model family: DA3-BASE, not Large/Giant.
- Product geometry config: `K35@476x742`.
- Product route target: official DA3 streaming structure adapted to K35 capacity:
  official chunk/overlap, loop retrieval, loop chunk forward, loop Sim3, and Sim3 loop optimizer.
- Commercial loop retrieval candidate under test: SelaVPR++.
- MoGe-2 status: research/shadow only. It is not mandatory production SAP input until GT/proxy tests show stable value.

## Research Tracks

- `experiments/da3_multiview_k_resolution_sweep_2026_05/`: archived DA3 K/resolution sweep, phone thermal runs, and DA3-BASE benchmark notes.
- `data/latest_capture_414/`: 414-frame real-capture overlap and MoGe uncertainty reports.
- `data/official_da3_base_k35_streaming_2026_05_30/reports/`: official-style DA3-BASE K35 streaming + VPR/loop comparison report.
- `data/tum_rgbd_*`, `data/tartanground_*`, `data/dtu64_*`: GT benchmark summaries.
- `tools/python/`: Mac research executors.
- `tools/dart/`: Dart research executors that reuse production contracts where practical.
- `artifacts/`: manifests for heavyweight local artifacts that should not live directly in git.

## Heavy Artifacts

Tensor binaries, MoGe `.npz` files, high-res photos, descriptor arrays, local database files, and vendored model checkpoints are kept outside git by default. Their local source paths are listed in `artifacts/local_heavy_artifacts.md`.
