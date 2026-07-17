# U3 #7 — off-plane multi-depth competition vs the flattened-chair false positive

**Diagnostic only.** No candidate added/removed, no production threshold selected,
no birth decision made. For the编排者 / user to adjudicate; this task only produces
scripts, numbers, viewers, a manifest and SHA-256 sums.

## Question

U3 #5 identified that the pure-A floor plane-sweep verifies each 1 cm grid cell at
**exactly one depth** (the certified floor plane; `depth_competition_offsets_m == ()`
in the certified config is the root cause). A chair/treadmill standing on the floor
therefore gets *flattened* onto the floor plane: its multi-view ZNCC clique passes at
floor depth and a ghost floor point is born. Can **multi-depth competition** — score
each cell at parallel depths along the floor normal and only birth the floor point
when floor depth *uniquely* wins — kill the chair without gutting the real floor?

## Method (pinned semantics, verbatim)

The depth-competition machinery **already exists** in the pinned `f2fc9a1`
`sweep_surface` (`unique_depth_winner` + the per-offset alternative scoring); it is
simply disabled. This experiment imports the pinned generator from its git blob
(SHA `d34a8bd3…`, never modified) and drives it per-point over the frozen
13,488-point union (`union_baseline.ply`, SHA `fdf5b105…`), reusing
`project_centers` / `select_point_views` / `score_point_hypothesis` /
`largest_consistent_clique` / `unique_depth_winner` exactly as `sweep_surface` calls
them.

For each accepted floor cell we score 16 parallel hypotheses at
`±{3,5,8,12,18,25,35,50} cm` along the certified floor normal. Each off-plane
hypothesis re-selects its own supporting sub-clique from the same candidate views
(the pinned behaviour). A cell **survives** (is born) only if floor depth beats every
scoreable competitor by the required rule; otherwise the cell is a **hole**.

Populations:
- **chair ROI** X∈[0.25,1.05], Z∈[−1.70,−0.55]: all 2,466 accepted cells (642 are
  chair-color false positives by the same blue-grey heuristic as #5).
- **clean floor**: 745 warm-brown (wood) cells sampled outside the ROI (stride 14 over
  10,422), to measure collateral damage to genuine floor.

Fidelity: every replayed floor score reproduces the frozen union tuple
(`views,parallax,zncc,candidate_views`) — **0 mismatches / 3,211 points** — after
snapping each 7-decimal PLY vertex back to its exact float64 grid coordinate
(max PLY→grid error 8.2e-8 m). Run: 103.8 s, peak RSS 1.80 GB, peak decoded image
1.59 GB (all Mac-local, 4K serial via the bounded 64-image LRU).

## Result — depth competition does NOT cleanly kill the chair

Pinned rule (`center_views ≥ alt_views` **and** `center_ncc ≥ alt_ncc + 0.02`):

| population | n | FP kill | **floor retention** | hole rate |
|---|---|---|---|---|
| chair ROI FP (642) | 642 | **92.1 %** (591 holed) | — | — |
| chair ROI wood floor | 1,824 | — | **23.8 %** | 76 % |
| clean floor (out-of-ROI) | 745 | — | **30.9 %** | 69 % |

It kills 92 % of chair false positives — but only by **holing ~70 % of genuine
wood floor**. `viewer_roi_falsepos_holes.png`: AFTER, holes (blue ×) blanket the
whole ROI, chair *and* surrounding floor alike; 486 sparse survivors remain and 51
chair-color FP are still born. Collateral floor loss (~69 %) is as bad as the #5
median-fusion prototype (28 % retention).

### Why — the floor plane is not the unique photometric depth even on clean floor

Worst-case floor advantage = `floor_ncc − max(competitor_ncc)` over all 16 offsets
(≤ margin ⇒ the cell is holed):

| population | median | p90 | frac ≤0.02 | frac ≤0.05 |
|---|---|---|---|---|
| clean wood floor | **−0.027** | +0.052 | 79 % | 90 % |
| chair ROI wood | −0.035 | +0.041 | 84 % | 92 % |
| chair ROI FP | −0.049 | +0.008 | 92 % | 96 % |

For a **majority of genuine clean-floor cells the floor depth already loses** to some
off-plane hypothesis (median advantage is *negative*). The chair-FP distribution is
only slightly worse (−0.049 vs −0.027) and **overlaps clean floor almost completely**.
There is no margin, direction, or view-rule that separates them — a full
(view-dominance × direction × margin∈{0.02…0.20}) sweep (`decision_sweep.json`) never
exceeds a separation product of **0.41**; its best point (positive-offsets-only,
ncc-only, margin 0.02) still holes **50 % of clean floor** to reach 83 % FP kill.

Mechanism: **low parallax + self-similar wood-grain / repetitive texture.** Parallel
planes a few cm apart reproject to nearly the same textured pixels, so ZNCC cannot
localise depth — the classic low-parallax / bas-relief depth ambiguity. The per-offset
kill attribution confirms it fires on photometric coincidences, not real structure:
the single most frequent "winning" competitor against chair FPs is **+0.50 m** (123 of
591) — a plane half a metre off the floor out-correlating it is a repetitive-texture
alias, not the chair seat.

### Reconciliation with the §7.5 height probe ("8/10 floor still won")

The §7.5 probe concluded the floor usually wins. That is because the probe **froze the
floor's accepted clique** and reprojected *those same floor-consistent views* to each
elevated hypothesis — a test biased toward the floor. The certified `sweep_surface`
depth competition (this experiment) instead lets **each off-plane depth re-select its
own best-correlating sub-clique**; under that faithful semantics the floor rarely wins
uniquely, for chair *and* clean floor alike. So the two results are not contradictory —
they measure different operators, and the operator that ships in `sweep_surface` is the
aggressive one that cannot be turned on without gutting the certified floor.

## Verdict for adjudication

Multi-depth competition **does** attack the flattened chair (92 % FP kill) but is
**too blunt to ship as a floor-birth gate on cap50**: at the certified 0.02 margin it
falsely holes ~70 % of the genuine floor, and no operating point in the swept rule
space separates chair from clean floor, because on this low-parallax repetitive-texture
capture the floor plane is *not* the unique ZNCC depth even where the floor really is.
Depth competition alone will not cleanly kill the chair. A real fix needs an
independent per-view depth/occlusion signal (free-space carving, per-view depth maps,
or opposition evidence) rather than a photometric parallel-plane contest — the same
gap #5 flagged (plane-sweep candidates carry no free-space / opposition evidence).

## Files

- `offplane_depth_competition.py` — driver (imports pinned blob; reuses its functions).
- `decision_sweep.py` — post-hoc rule sweep over the scored offsets (no re-scoring).
- `render_viewers.py` — true-color before/after + hole/retention viewers.
- `depth_competition.jsonl` — per-cell rows: floor score, 16 competitor scores, survive
  flags under three rules.
- `stats.json`, `decision_sweep.json`, `manifest.json`, `SHA256SUMS.txt`.
- `roi_all_scored.ply` / `roi_survivors_pinned.ply` / `roi_holes_pinned.ply`.
- `viewer_roi_truecolor_before_after.png`, `viewer_roi_falsepos_holes.png`,
  `viewer_clean_floor_retention.png`.

Reproduce:
```sh
/opt/homebrew/bin/python3.11 experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/offplane_depth_competition.py
/opt/homebrew/bin/python3.11 experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/decision_sweep.py
/opt/homebrew/bin/python3.11 experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition/render_viewers.py
```
