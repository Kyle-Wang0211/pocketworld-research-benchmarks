# Change: Strengthen geometric consistency through the smooth field only

## Why the previous attempt was rejected, with the mechanism

User verdict 2026-09-03: the anchored version
(`anchor-mapanything-to-casdiffmvs`) has the least ghosting; the consensus
version (`consensus-on-anchorfree-pixels`) is worse, "your metric is the
problem".  Both statements are correct and the mechanism is now measured.

The official multi-view confidence rewards agreement, and smoothing or noising
a surface can buy agreement, so it cannot choose a winner.  Two of my own
hypotheses about the visible defect were also refuted:

- "averaging blurs detail" -- refuted.  High-frequency content (median
  |z - blur5x5(z)| / z) went UP: consensus 1.14x, the 8-iteration variant
  1.49x relative to the anchored version.  Nearest-neighbour partner sampling
  injects noise, it does not blur.
- "nearest sampling quantises depth into stairs" -- refuted.  Zero adjacent
  pixel pairs have identical depth; 7x7 windows hold 49 distinct values in
  every version.

The actual defect: the consensus knife averaged ONLY anchor-free pixels and
left anchored pixels untouched, and the CasDiffMVS fusion mask is blotchy, so a
depth step appeared along the mask boundary.  Cross-boundary over within-region
relative adjacent depth jump: consensus 3.65, anchored 1.29, 8-iteration 1.13;
about 8,000 boundary pixel pairs per frame at 0.6% relative depth, which is
~2.7 cm at 4.5 m and reads as patchy layering on a white wall.

General rule taken from this: never apply a treatment to a hard subset of
pixels; act on the whole image, use a smooth weight, or put the evidence into a
smooth parametric field.

## Three rulers, calibrated on the user's verdicts (`three_rulers.py`)

1. SEAM   cross-boundary / within-region adjacent depth jump along the anchor
          mask.  Catches subset treatments.
2. LAYERS fraction of pixels where partner views deposit a second surface
          separated by more than max(2 cm, 1% z) with at least 15% of the
          samples.  This is ghosting proper.
3. DETAIL high-frequency content relative to the reference version.  Catches
          both added noise and blur.

The rejected version scores badly on SEAM and DETAIL; the preferred version
scores clean on both.  A candidate earns the user's eyes only if LAYERS drops
while SEAM and DETAIL stay put.

## Method (`joint_smooth_field.py`)

Same smooth per-view log-depth field as the anchored version, but its data term
now carries the cross-view evidence as well: at anchored pixels the target is
log z_mvs - log z_base; at anchor-free pixels the target is the log of the
consensus depth implied by agreeing partners (official 2%/2% test) minus
log z_base.  Weighted Laplacian solve at half resolution (lambda 4, two Huber
IRLS passes), three outer rounds re-deriving the targets.  The depth map's
per-pixel relationships are never modified -- only a smooth field multiplies
them -- so surface cleanliness cannot change by construction.

## Result recorded 2026-09-03

| ruler | anchored (user's best) | consensus (rejected) | this change |
|---|---|---|---|
| SEAM | 1.175 | 3.650 | 1.170 |
| LAYERS | 0.7162 | 0.6123 | 0.6250 |
| DETAIL | 1.0000 | 1.1418 | 1.0023 |

Control: with the cross-view term switched off (`--w_cross 0`) the solve
reproduces the anchored version and stops changing after round 0, confirming
the cross-view term is the only active variable.

Official consistency (reported for locating only): 0.259 -> 0.221 over three
rounds; field spread within a view 5.2%; displacement from the affine base
p50 1.05%; high-frequency vs the raw affine base 0.9855.

Points 25,150,854 (unchanged); PLY 679,073,269 bytes SHA-256 `f9adbff5…`;
compute 87 s.  Page: `verdict_page/mapanything_joint_smooth_field_20260903/`
(POSITION `377ed803…3498cc`, RGB `032587ec…71561e`).

User verdict: pending.

## Stop conditions

No point deleted, no per-pixel averaging of the depth map, no model change.
The official self-consistency metric may not be used to choose a winner.
