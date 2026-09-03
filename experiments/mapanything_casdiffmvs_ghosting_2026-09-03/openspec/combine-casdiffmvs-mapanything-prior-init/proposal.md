# Change: CasDiffMVS with MapAnything depth as the refinement initialisation

## Why

User verdict 2026-09-03 on the official CasDiffMVS run
(`reproduce-casdiffmvs-official-blendmvg-nv10`): "没有任何重影", but the white
wall sticks to the suitcase and backpack (textureless wall depth pulled toward
foreground objects).  MapAnything has the opposite profile: clean wall/object
separation and complete walls, but cross-view inconsistency.  The user asked
how to combine the two.  The ghost-wall campaign (research repo,
`HANDOFF_ghost_layer_and_retrain_2026-08-20.md`) established that post-hoc
filtering cannot fix this ("根治只在出生前"), so the combination is done at
depth-estimation time: keep CasDiffMVS's photometric refinement and fusion,
but start the refinement from MapAnything's depth instead of the coarse
cost-volume argmax.

## Method

1. `make_prior_maps.py`: for CasDiffMVS view s (source index), MapAnything
   frame f = `capture_order_source_to_frame[s]` (verified by image correlation
   1.0 on 4 views).  MapAnything `depth_z[f]` (392x518 upright model image) is
   mapped back through the exact crop/resize and the ROTATE_270 inverse to the
   landscape 768x576 CasDiffMVS working image, then fitted per view by a robust
   affine `z_cas ≈ a·z_map + b` on pixels kept by the official fusion
   (`mask/*_final.png`).  Fit: a p50 3.75 (3.43–3.93), b p50 0.40,
   relative residual p50 1.1% (per-view p95 1.8%), p90 3.1%; prior covers 93%
   of pixels (MapAnything mask).
2. `casdiffmvs_prior_driver.py`: upstream `CasDiffMVS.forward` copied verbatim
   (test path) with one hook: at stage 1 the initial depth `depth_predictions[-1]`
   is replaced by the prior (bilinear to stage resolution, clamped to the view's
   depth range) where the prior is non-zero.  Same loader, same official
   arguments, same seed 123, same checkpoint (official blendmvg), same
   `filter.py` fusion (0.3/0.5/0.5, geo≥3, 1.0 px, 0.01, averaging).

## Result recorded 2026-09-03

- Prior replaced 94% of stage-1 pixels; prior vs coarse depth differ by 1.6%
  median (p95 4.1%).
- Inference 57.6 s; fused points 35,007,196 (PLY 525,108,122 bytes, SHA-256
  `90f2d87c…`); per-view final-mask survival median 0.649 vs official 0.671.
- Page: `verdict_page/casdiffmvs_blendmvg_mapanything_prior_20260903/`
  (POSITION `76ba17b7…7a6108`, RGB `a82dbbd0…37c401e`).
- User verdict: pending.  Next variants if needed: inject the prior only where
  the coarse confidence is low (textureless), or also at stage 2.
