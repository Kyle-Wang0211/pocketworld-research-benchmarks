# DA3-BASE Image-Only Official Reproduction

日期：2026-06-06

这条研究线只记录一件事：尽量一比一复刻官方 DA3-BASE image-only 路线，并把每一步的中间产物、文字报告、图片报告、表格和判断依据独立归档。它不混入外部 pose、AR/VIO、depth camera，也不把 pose-conditioned `K35@476x742` sweep 结果当作 image-only 结论。

## 路线契约

- model: `DA3-BASE`
- input contract: `image_only`
- window size: `K35`
- official preprocess: `process_res=504`, `process_res_method=upper_bound_resize`, patch-aligned to `280x504` for the current 16:9 capture
- forbidden DA3 inputs: `extrinsics`, `intrinsics`
- DA3 outputs used by this route: `depth`, `confidence`, `pred_intrinsics`, `pred_extrinsics`, `processed_images`
- downstream policy: every later stage must consume the stage outputs as recorded here; no hidden cleanup is allowed before the diagnostic stage that explicitly owns it

## Folder Map

| Folder | Role |
|---|---|
| `00_route_contract/` | Evidence that this route is official image-only, not pose-conditioned CoreML. |
| `01_stage01_official_depth_conf_photometric/` | Stage 01 outputs: original RGB, DA3 processed RGB, depth, confidence, highlight/dark overlay, summary panels, tables, raw official prediction arrays. |
| `02_stage02_official_camera_pose_geometry/` | Stage 02 workspace: DA3-predicted intrinsics/extrinsics/camera-pose diagnostics. |
| `source_pointers/` | Capture manifest, input manifest, and K-window selection used by this route. |
| `STAGES_ZH.md` | Full stage-by-stage reproduction map. |

## Current Status

Stage 01 is archived for `window_000` with 35 frames:

`cap-1, cap-3, cap-5, cap-7, cap-21, cap-23, cap-29, cap-31, cap-33, cap-35, cap-37, cap-39, cap-42, cap-44, cap-48, cap-50, cap-52, cap-54, cap-56, cap-74, cap-78, cap-80, cap-96, cap-103, cap-105, cap-107, cap-109, cap-114, cap-116, cap-118, cap-122, cap-124, cap-126, cap-128, cap-131`

Stage 02 is intentionally not filled yet. Its job is to inspect the camera geometry predicted by DA3 before any point-cloud or fusion step.

## Important Separation

`K35@476x742` remains useful as a pose-conditioned / external-pose-compatible research reference. It is not the authority for this image-only route. The official image-only authority in this folder is the `280x504` K35 target produced by official `process_res=504 upper_bound_resize` semantics for the current 16:9 capture.
