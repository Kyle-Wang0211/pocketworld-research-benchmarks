# Change: Layer-by-layer attribution audit of MapAnything ghosting (diagnostic only)

## Objective

Locate the first layer at which the official Apache MapAnything image-only
chain loses cross-view geometric consistency on the frozen 132-view room
capture, using only official output fields and the official multi-view depth
consistency metric.  This change produces numbers, not a candidate point cloud.
No filtering, fusion, threshold change, K/Sim(3) tuning, or export is involved.

Ledger note: the two diagnostic runs below were executed on 2026-09-03 before
this file was written; the file was written the same session to record them.
This deviates from the "ledger before run" policy and is stated here rather
than hidden.

## Frozen identities

- Upstream repository: `/root/map-anything-official-exact-src-20260902`,
  commit `3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9`, `git status` clean.
- Model: `facebook/map-anything-apache`, revision
  `00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a` (verified on 2026-09-03 to be the
  newest revision on the Hub; last weight push 2026-01-20).
- Inputs (run A): `/root/imgs132_up`, 132 JPEG, 1500x2000 upright, ordered
  manifest SHA-256 `f21362f7d4ca445a1ac6900bbe98b96d8be530dc4ed45a0cb5b031787639cec8`.
  `frame_000000.jpg` matches source `00000016.jpg` with correlation 1.0, i.e.
  this set is already in capture order.
- Sideways inputs (probe R5/R6): `/root/imgs132`, 2000x1500, same content
  stored landscape without EXIF orientation, first 8 frames only.
- Reference cameras: production COLMAP sparse model, `cameras.bin`
  `2d611390…ce1c`, `images.bin` `d6b5f85a…816e`, `points3D.bin`
  `ef41835e…012d`; 132 PINHOLE cameras at 4032x3024, median fx 2861.97 px.
  Rotated upright with the official `rotate_pinhole_90degcw` and the
  self-tested `rotate_world_to_camera` from
  `/root/mapanything_prepare_upright_colmap.py`, then passed through the
  official `preprocess_inputs` to model resolution 392x518.

## Runs

1. `/root/save_official_outputs.py` — replays the demo's `model.infer` call
   with its exact arguments (`memory_efficient_inference=True`,
   `minibatch_size=1`, bf16 AMP, `apply_mask=True`, `mask_edges=True`) and
   saves every per-view tensor to
   `/root/mapanything_layer_audit_A_imgs132_up_20260903/` (1.5 GB, SHA-256 in
   `SHA256SUMS.npy.txt`).  Inference 17.97 s, peak CUDA 17.31 GB, demo-export
   vertex count 25,150,854 (frozen exact GLB: 25,123,136; 0.11% bf16 replay
   noise, not byte-identical).
2. `/root/layer_attribution.py` — compares predicted K / pose / depth against
   the reference and evaluates the official
   `compute_multiview_depth_confidence` (2% / 2%) under substitutions
   V1 pred K + pred pose, V2 COLMAP K + pred pose, V3 pred K + COLMAP pose
   (Sim(3) to model units), V4 COLMAP K + COLMAP pose, V5 as V4 with each
   frame's depth rescaled by its COLMAP-sparse median ratio.  Output:
   `layer_attribution.json` SHA-256
   `36f6efea0ef1ee6869cad0eb6c766a92a8ebd6bd308d495c367ecb811b12f237`.
3. `/root/calib_follow_probe.py` — 8 views: image-only (R1), K given (R2),
   K + pose given non-metric (R3), single-view upright (R4), single-view
   sideways (R5), 8-view sideways (R6).  Output
   `/root/mapanything_calib_follow_probe_20260903/report.json` SHA-256
   `caf2c888ef3d5df8bcbeaddebfeafb1486cea947dd6ed95e00a40fc972dd5367`.

Local copies of scripts, JSON and logs (not the tensors):
`_host_experiments.nosync/mapanything_layer_audit_20260903/`.

## Results recorded 2026-09-03

Layer K (132 views): predicted fx p50 284.1 vs reference 370.6 at 392x518;
ratio p50 0.768 (p05 0.755, p95 0.783); ray angular error p50 6.42 deg.
Principal point agrees (cx 195.7 vs 195.5, cy 258.5 vs 259.5).

Layer pose: Sim(3) scale model/COLMAP 0.2533; camera-centre residual p50 1.9%
of trajectory diagonal (p95 3.3%); rotation error p50 3.59 deg (p95 5.48).

Layer depth scale vs COLMAP sparse: per-frame median ratio / Sim(3) scale p50
0.946 (p05 0.914, p95 0.986; min 0.832, max 1.051); spread p95/p05 1.079;
residual ratio drifts from 1.022 at image centre to 0.980 at the edge.

Official multi-view consistency, per-frame fraction of pixels with confidence
below 0.5, p50 (p95): V1 0.291 (0.657); V2 0.886 (0.991); V3 0.812 (0.949);
V4 0.629 (0.905); V5 0.601 (0.839).  Substituting true K and/or true pose
makes agreement worse, so the predicted depth is only consistent inside the
model's own distorted camera model.

Probe (8 views): fx ratio R1 0.772, R2 (K given) 0.787, R3 (K + pose) 0.787
with pose followed to 0.29 deg relative rotation; R4 single-view upright
0.774; R5 single-view sideways 0.599 (ray error 13.2 deg); R6 8-view sideways
0.589 (13.6 deg).  The calibration input is received (small shift toward it)
but not followed; the focal error is already present at single view; sideways
storage orientation roughly doubles it.

## Conclusion boundary

- First geometry-changing layer: the model's own predicted ray directions /
  intrinsics (23% focal deficit, present at single view, unchanged by view
  count, not corrected by calibration input).  Depth and pose are co-adapted
  to that camera model; the residual cross-view inconsistency (V1) is what the
  user sees as ghosting.  Pose input is followed; K input is not.
- The 2026-09-03 capture-order failure (4032x3024 source JPEGs) is explained by
  orientation, not ordering: those files are stored sideways and the model
  predicts a 41% focal deficit on sideways frames.
- Nothing here changes the user's visual verdicts.  No candidate was produced.
