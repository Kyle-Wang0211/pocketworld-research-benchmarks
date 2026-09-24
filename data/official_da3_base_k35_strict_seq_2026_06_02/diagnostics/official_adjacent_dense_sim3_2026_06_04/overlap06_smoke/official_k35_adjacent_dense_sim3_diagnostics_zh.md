# Official K35 Adjacent Dense Sim3 Diagnostics

## What This Is

- Read-only diagnostic.
- Mirrors DA3-Streaming adjacent dense Sim3 semantics.
- Does not apply transforms, fuse points, clean points, mesh, or run loop optimization.

## Inputs

- capture_dir: `data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_official_save_overlap06`
- da3_dir: `data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_official_save_overlap06_official_postprocess`
- confidence_mode: `streaming_subtract_one`

## Summary

- edge_count: 1
- estimated_count: 1
- point_count_mean: 1972502
- rmse_mean: 0.18883437
- rmse_max: 0.18883437
- p90_mean: 0.37081145
- scale_mean: 1.1348413
- scale_std: 0
- scale_range: 1.1348413 .. 1.1348413
- rotation_angle_deg_mean: 3.0865017
- rotation_angle_deg_max: 3.0865017
- translation_norm_mean: 0.3886433
- translation_norm_max: 0.3886433

## Edges

| edge | parent | current | overlap | points | scale | rot deg | trans | rmse | p90 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | window_000 | window_001 | 6 | 1972502 | 1.1348413 | 3.0865017 | 0.3886433 | 0.18883437 | 0.37081145 |
