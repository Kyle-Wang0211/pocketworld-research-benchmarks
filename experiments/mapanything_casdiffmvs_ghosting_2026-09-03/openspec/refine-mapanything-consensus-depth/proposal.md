# Change: MapAnything-only consensus depth (scale alignment + averaging, no deletion)

## Objective

Reduce cross-view layering in the official MapAnything image-only output using
only the model's own outputs and its own cross-view geometry, without deleting
any point, changing the model, or introducing external cameras.  The user asked
on 2026-09-03 whether this had been tried before; it had not (the prior agent's
experiments were filters, StereoFusion bridges, voxelisation, input-conditioning
variants and read-only audits).

## Method (script `/root/mapanything_consensus_depth.py`, local copy in
`_host_experiments.nosync/mapanything_layer_audit_20260903/root/`)

- Inputs: the saved official per-view tensors of the exact baseline
  (`/root/mapanything_layer_audit_A_imgs132_up_20260903`), official mask.
- Stage A: per-frame depth scale (132 scalars) by linear least squares on
  forward-projected correspondences with the predicted poses fixed; three IRLS
  passes with log-ratio gates 0.25 → 0.125 → 0.0625.
- Stage B: for every pixel, average its depth with the depths implied along its
  ray by every other view that agrees within the official thresholds
  (abs 0.02 + rel 0.02), formula (sum of consistent reprojected depths + own)
  / (n + 1), two passes.  Pixels without a consistent partner are unchanged.
- Projection/sampling mirror `mapanything/utils/multiview_confidence.py`.
- Export: every official-mask pixel re-unprojected with predicted K/pose,
  original per-pixel colour.

## Result recorded 2026-09-03

- Stage A scales: p05 1.013, p50 1.025, p95 1.051 (min 1.006, max 1.066);
  1.3–1.5 billion correspondences per pass.
- Stage B: 99.8% of pixels have ≥1 consistent partner (median 49 partners);
  depth change p50 0.65% / p95 1.9% (pass 1), 0.26% / 1.5% (pass 2).
- Official multi-view consistency, per-frame fraction of pixels below 0.5:
  p50 0.291 → 0.193; mean confidence 0.625 → 0.712.
- Points: 25,150,854 (unchanged count); PLY SHA-256 `946d8994…`; 68.7 s.
- Page: `verdict_page/mapanything_consensus_depth_20260903/`.
- Honest expectation stated before running: layers within the 2% tolerance
  collapse; larger offsets remain.  User verdict: pending.
