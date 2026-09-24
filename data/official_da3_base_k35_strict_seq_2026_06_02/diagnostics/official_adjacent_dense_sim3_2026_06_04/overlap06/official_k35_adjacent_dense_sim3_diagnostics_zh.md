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

- edge_count: 14
- estimated_count: 14
- point_count_mean: 1787223.4
- rmse_mean: 0.090599082
- rmse_max: 0.18883437
- p90_mean: 0.14172412
- scale_mean: 1.0238753
- scale_std: 0.058709576
- scale_range: 0.94438075 .. 1.1348413
- rotation_angle_deg_mean: 2.3903789
- rotation_angle_deg_max: 4.3835578
- translation_norm_mean: 0.16624716
- translation_norm_max: 0.3886433

## Edges

| edge | parent | current | overlap | points | scale | rot deg | trans | rmse | p90 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | window_000 | window_001 | 6 | 1972502 | 1.1348413 | 3.0865017 | 0.3886433 | 0.18883437 | 0.37081145 |
| 1 | window_001 | window_002 | 6 | 1485918 | 1.0152245 | 3.0837247 | 0.088623512 | 0.072564566 | 0.11464949 |
| 2 | window_002 | window_003 | 6 | 2082996 | 1.046439 | 2.764318 | 0.16706207 | 0.070820497 | 0.10254047 |
| 3 | window_003 | window_004 | 6 | 1491041 | 0.9634852 | 1.0836622 | 0.10369225 | 0.083045165 | 0.13684236 |
| 4 | window_004 | window_005 | 6 | 1994838 | 0.95814946 | 1.210629 | 0.095040411 | 0.078038728 | 0.11353492 |
| 5 | window_005 | window_006 | 6 | 2061066 | 0.98617112 | 2.6678074 | 0.12065997 | 0.073141413 | 0.10361288 |
| 6 | window_006 | window_007 | 6 | 1603551 | 1.0110077 | 2.5496278 | 0.067376401 | 0.12156197 | 0.15311735 |
| 7 | window_007 | window_008 | 6 | 1801778 | 0.96627402 | 4.3835578 | 0.099858853 | 0.08399456 | 0.14685371 |
| 8 | window_008 | window_009 | 6 | 1331357 | 1.0337369 | 2.8214074 | 0.18989569 | 0.12103701 | 0.16091343 |
| 9 | window_009 | window_010 | 6 | 1478041 | 1.0407631 | 3.3289214 | 0.11807889 | 0.10479165 | 0.15005192 |
| 10 | window_010 | window_011 | 6 | 1934415 | 1.1137688 | 2.3603681 | 0.30881855 | 0.058822646 | 0.089330394 |
| 11 | window_011 | window_012 | 6 | 1697967 | 1.0095459 | 2.7596529 | 0.15609051 | 0.06773934 | 0.11820593 |
| 12 | window_012 | window_013 | 6 | 2055848 | 1.1104665 | 1.1224899 | 0.28963612 | 0.076116217 | 0.11374482 |
| 13 | window_013 | window_014 | 6 | 2029809 | 0.94438075 | 0.24263671 | 0.13398374 | 0.067879027 | 0.10992849 |
