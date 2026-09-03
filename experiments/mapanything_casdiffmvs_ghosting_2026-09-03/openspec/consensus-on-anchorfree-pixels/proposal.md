# Change: Consensus averaging on the anchor-free pixels of the anchored cloud

## Why

`anchor-mapanything-to-casdiffmvs` pins MapAnything's depth to CasDiffMVS
geometry wherever the official CasDiffMVS fusion kept a pixel (native-grid
anchor coverage p50 0.675).  Its measured residual sits exactly in the
anchor-free remainder: official multi-view inconsistency p50 0.262 overall but
0.482 on anchor-free pixels alone.  Those pixels are the textureless walls and
the periphery, i.e. the region where MapAnything's completeness advantage lives
and where any remaining layering would show.

## Method (`consensus_on_anchorfree.py`)

Start from the anchored native depths (`depth_native_final.npy`, 392x518,
production COLMAP cameras upright).  Anchor mask is the CasDiffMVS
`mask/*_final.png` sampled into the native grid through the same mapping as
`export_native_anchored.py`.  Anchored pixels are left untouched.  Anchor-free
pixels get the official consistency test (abs 0.02 + rel 0.02) against every
frustum-overlapping view and the same `(Σ consistent reprojected depths + ref)
/ (n+1)` averaging used by the consensus run and by COLMAP/DiffMVS fusion, two
iterations.  Nothing is deleted; the point set stays identical to the raw
MapAnything cloud; colours are the original per-pixel image colours.

## Result recorded 2026-09-03

- 98.6% of anchor-free pixels found at least one consistent partner; relative
  depth change on them p50 0.50% (iteration 1), 0.25% (iteration 2).
- Official multi-view inconsistency, fraction of pixels below 0.5, p50:
  overall 0.262 → 0.218; anchor-free only 0.482 → 0.371; mean confidence
  0.643 → 0.690.
- Points 25,150,854 (unchanged); PLY 679,073,269 bytes SHA-256 `70b5eef9…`;
  compute 28.5 s.
- Page: `verdict_page/mapanything_anchored_consensus_20260903/`
  (POSITION `39ca8745…596349`, RGB `032587ec…71561e`).
- User verdict: pending.

## Stop conditions

Do not delete points, do not change the model or the official thresholds, and
do not touch anchored pixels.  Numeric consistency cannot accept visual
quality; only the user's inspection decides.
