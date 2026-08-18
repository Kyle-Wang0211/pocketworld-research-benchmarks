# Stage 01 DA3 Depth / Confidence / Photometric Audit

Window: `window_000`, 35 frames. This stage is before camera-space PLY, Sim3, loop closure, or fusion.

## Key Visual Outputs

- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/contact_sheets/00_original_rgb_contact.jpg`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/contact_sheets/01_da3_processed_rgb_contact.png`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/contact_sheets/02_depth_linear_contact.png`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/contact_sheets/03_depth_log_contact.png`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/contact_sheets/04_confidence_contact.png`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/contact_sheets/05_highlight_dark_overlay_contact.png`
- `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/contact_sheets/06_summary_panel_contact.jpg`

## Per-Frame Outputs

- Per-frame depth images: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/per_frame/depth_linear`
- Per-frame confidence images: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/per_frame/confidence`
- Per-frame summary panels: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/per_frame/summary_panel`
- Metrics CSV: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/stage01_depth_conf_photometric_window000_2026_06_06/tables/window_000_stage01_depth_conf_highlight_metrics.csv`

## Suspect Frames From Prior Window PLY Observation

- local 19 `cap-74`: depth_mean=0.8680, conf_mean=1.3451, highlight=16.22%, saturated=13.93%, dark=2.88%
- local 20 `cap-78`: depth_mean=0.8619, conf_mean=1.3006, highlight=15.73%, saturated=14.15%, dark=4.15%
- local 21 `cap-80`: depth_mean=0.8641, conf_mean=1.3312, highlight=14.97%, saturated=13.70%, dark=4.80%

## Highest Highlight / Reflection Ratios

- local 26 `cap-109`: highlight=17.34%, sat=16.36%, depth_mean=0.8921, conf_mean=1.0583
- local 22 `cap-96`: highlight=17.12%, sat=16.38%, depth_mean=0.8326, conf_mean=1.1073
- local 27 `cap-114`: highlight=17.09%, sat=14.23%, depth_mean=0.8846, conf_mean=1.0444
- local 25 `cap-107`: highlight=16.42%, sat=15.42%, depth_mean=0.8927, conf_mean=1.0611
- local 24 `cap-105`: highlight=16.38%, sat=15.30%, depth_mean=0.8895, conf_mean=1.0663
- local 19 `cap-74`: highlight=16.22%, sat=13.93%, depth_mean=0.8680, conf_mean=1.3451
- local 20 `cap-78`: highlight=15.73%, sat=14.15%, depth_mean=0.8619, conf_mean=1.3006
- local 23 `cap-103`: highlight=15.68%, sat=9.46%, depth_mean=0.8632, conf_mean=1.0656

## Highest Dark Ratios

- local 02 `cap-5`: dark=11.36%, dark_depth_mean=0.8415, dark_conf_mean=1.0001
- local 03 `cap-7`: dark=10.94%, dark_depth_mean=0.8154, dark_conf_mean=1.0000
- local 00 `cap-1`: dark=9.99%, dark_depth_mean=0.8190, dark_conf_mean=1.0001
- local 01 `cap-3`: dark=9.70%, dark_depth_mean=0.8297, dark_conf_mean=1.0001
- local 09 `cap-35`: dark=7.37%, dark_depth_mean=0.9028, dark_conf_mean=1.0001
- local 05 `cap-23`: dark=7.09%, dark_depth_mean=0.8824, dark_conf_mean=1.0000
- local 04 `cap-21`: dark=6.53%, dark_depth_mean=0.8797, dark_conf_mean=1.0000
- local 06 `cap-29`: dark=6.39%, dark_depth_mean=0.8566, dark_conf_mean=1.0000

## Depth Range Extremes

Highest depth p99:
- local 20 `cap-78`: depth_p99=1.7577, depth_mean=0.8619
- local 26 `cap-109`: depth_p99=1.7568, depth_mean=0.8921
- local 25 `cap-107`: depth_p99=1.7554, depth_mean=0.8927
- local 27 `cap-114`: depth_p99=1.7466, depth_mean=0.8846
- local 28 `cap-116`: depth_p99=1.7447, depth_mean=0.8722

Lowest confidence median:
- local 03 `cap-7`: conf_median=1.0001, conf_mean=1.0009
- local 04 `cap-21`: conf_median=1.0001, conf_mean=1.0013
- local 08 `cap-33`: conf_median=1.0001, conf_mean=1.0011
- local 06 `cap-29`: conf_median=1.0002, conf_mean=1.0015
- local 02 `cap-5`: conf_median=1.0002, conf_mean=1.0015

