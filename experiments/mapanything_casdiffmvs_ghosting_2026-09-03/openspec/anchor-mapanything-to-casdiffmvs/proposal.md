# Change: MapAnything as the presentation, CasDiffMVS as the geometric anchor

## Why

User direction 2026-09-03 after judging `combine-casdiffmvs-mapanything-prior-init`
the best version so far ("粘连少了非常多"): the final presentation must be
MapAnything's cloud (it shows the whole room; CasDiffMVS only the central region),
and CasDiffMVS should only be used to make MapAnything ghost-free.

## Method (`anchor_mapanything_to_casdiff.py`)

Per view, in the CasDiffMVS working image (768x576, production COLMAP camera):

- `z_map`: MapAnything depth mapped into this camera (output of
  `make_prior_maps.py`; per-view affine already applied; 0 where MapAnything
  masked).
- Anchors: pixels kept by the official fusion of the prior-initialised
  CasDiffMVS run (`mask/*_final.png`), with that run's refined depth `z_mvs`.
- Solve a smooth offset field h in log-depth:
  minimise Σ_anchors w (log z_map + h − log z_mvs)² + λ |∇h|² (λ = 4 at
  half resolution, two Huber IRLS passes), i.e. keep MapAnything's relative
  shape everywhere and pin it to the multi-view-consistent MVS depths where
  they exist; h extends harmonically into anchor-free regions.
- `z = exp(log z_map + h)` for every MapAnything pixel; unproject with the
  COLMAP intrinsics/pose into the common COLMAP world frame; original colours;
  export stride 0.75 to stay in the 20–30M band.  No point deleted, no model
  changed.

## Result recorded 2026-09-03

- Anchor coverage per view p50 0.629 (p05 0.260, p95 0.752); MapAnything
  coverage p50 0.935.
- Offset field: median ≈ 0 (affine already removed the per-view scale), spread
  within a view (p95 − p05) p50 0.051 — the FOV-type distortion now corrected
  where anchors exist; anchor residual after solve p50 0.05%.
- Official multi-view consistency in the COLMAP frame, fraction of pixels
  below 0.5, p50 (p95): affine-only MapAnything 0.449 (0.716) → anchored
  0.268 (0.616); mean confidence 0.51 → 0.65.  Residual inconsistency sits in
  the anchor-free 37% (textureless walls / periphery).
- Points 30,553,793; PLY 824,952,622 bytes SHA-256 `84bbdc30…`; 1 min 41 s.
- Page: `verdict_page/mapanything_anchored_to_casdiff_20260903/`
  (POSITION `e4d0ad11…49a4d`, RGB `46870812…f7b6ff`).
- The first export (stride 0.75 on the 768x576 grid) produced regular density
  stripes on flat surfaces (non-integer stride aliasing), verified NOT to be in
  the depth data (per-view depth images clean).  Replaced by
  `export_native_anchored.py`: the same affine + offset field applied on
  MapAnything's native 392x518 grid, unprojected with the upright production
  COLMAP cameras → point set identical to the raw MapAnything cloud
  (25,150,854 points, original colours), only depth changed.  Native-grid
  official consistency: affine-only 0.471 → anchored 0.262 (mean 0.52 → 0.64).
  PLY SHA-256 `9d4d033e…`; page `verdict_page/mapanything_anchored_to_casdiff_20260903/`
  now holds this native export.
- User verdict: pending.  Next if walls still layer: apply the MapAnything
  consensus averaging (official 2%/2% thresholds) in the COLMAP frame to the
  anchor-free pixels only.
