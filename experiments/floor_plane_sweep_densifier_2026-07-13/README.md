# Floor densification: known-plane plane-sweep vs detector-free rescue (cap50, 2026-07-13)

**All experiments run on Mac (M3 Pro, torch-MPS) — no remote GPU box. No production code touched.**

> [!WARNING]
> **Commercial-use boundary:** the historical table and images below are research evidence,
> not a shipment gate. `floor_rescue_band_colored.ply`, the B/C routes, and every
> `maxed`/merged result contain LoFTR-indoor/ScanNet non-commercial lineage and may only
> be described as a non-commercial research upper bound. The plane-sweep algorithm core
> is model-free photometric geometry, but the historical `fr_planesweep.py` run still
> reads a LoFTR-derived rescue PLY for coverage statistics. The 2026-07-15 clean rerun
> below removes that dependency and consumes only first-party images, poses, intrinsics,
> the product sparse cloud, and the known floor plane. It is clean with respect to learned
> matcher lineage, but remains a host research result until the A16 tiled implementation
> and product integration pass their acceptance tests.

## Clean pure-A result (cap50, 2026-07-15)

The new structural runner includes the floor and never reads LoFTR matches or LoFTR-derived
point clouds. A 10-view base pass is preserved exactly. A 48-view rescue pass may create a
point only when the base pass failed and the rescue evidence exceeds the frozen base medians
(`ZNCC >= 0.850047`, parallax `>= 10.241 deg`, at least 3 mutually consistent views). Every
pair in the accepted view clique must independently satisfy `ZNCC >= 0.70`.

| metric | product SIFT | historical plane-sweep | **clean pure-A owner + rescue24** |
|---|---:|---:|---:|
| Floor points | 5,845 | 12,672 | **13,488** |
| Plane-sweep 5cm cells | — | 1,459 | **1,596** |
| New cells absent from SIFT | — | 847 | **1,001** |
| SIFT union cells | 1,101 | 1,948 | **2,102 (+90.92%)** |
| ZNCC median / P10 | — | 0.7906 / 0.7189 | **0.8644 / 0.7859** |
| Views / parallax median | — | 4 / 15.10 deg (star set) | **4 / 14.21 deg (all-pairs clique)** |
| Points farther than 1um from floor | — | not recorded | **0** |
| LoFTR-derived inputs consumed | — | yes, coverage comparator | **no** |

This supersedes LoFTR as a dependency for **floor coverage**, not as a general matcher.
Plane-sweep only owns certified planar structure. Non-planar weak-texture objects still need
the separate D-route detector-free matcher with commercially clean code, weights, data, and
runtime provenance. Do not delete that capability or conflate it with floor plane-sweep.

The historical and current parallax medians are not directly comparable: the historical
star set required each member to agree only with one reference view, while the clean runner
requires every accepted pair to agree. The current 14.21-degree median is measured on the
strict set and remains far above the frozen 5-degree gate.

The exact command, hashes, rejection counts, memory peak, and comparison are stored in
`runs/cap50_pure_a_wall_ceiling_20260714/verdict_pure_a_floor_owner_rescue48_20260715.json`.

## Problem
cap50's floor is weakly textured → production SIFT leaves holes + a "ghost layer"
(sub-floor double-floor shell from depth ambiguity). Goal: densify the floor with
**more good points, no quality drop**, purely photometric (Android/HarmonyOS have no LiDAR).

## Historical headline result (research only)

| | SIFT (prod baseline) | LoFTR rescue (non-commercial) | **plane-sweep + maxed (non-commercial merged upper bound)** |
|---|---|---|---|
| Floor coverage | 2.75 m² | +0.70 m² (+25%) | **5.84 m² (+112%)** |
| Good points | 5845 | 1435 | **18,076 (1cm) / 55,192 (5mm)** |
| New holes filled (SIFT=0) | — | 0.70 m² | **3.09 m² (4.4×)** |
| Sub-floor ghost points | 3540 (4.7%) | (inherits) | **0** |

The historical scripts report that retained points pass the gates below, without quality
relaxation. These numbers have not yet been regenerated from the new hashed data contract,
so they must not be promoted to a production or commercial claim.

## The winner: plane-sweep on the known ARKit floor plane

Not feature matching — **verification on a known plane**. The floor plane (n,d) is
certified (from ARKit / SfM plane fit). Lay a regular grid on the plane; for each 3D
grid point take a plane-induced-homography patch, reproject into every 4K view
(`K_highres` + ARKit pose), bilinear sample. **Quality gate = strict multi-view
photometric consistency**: cheirality + patch fully in-frame + real texture per view
(std≥6/255) + max mutually-consistent view set with ZNCC≥0.70 across ≥3 views spanning
≥5° parallax. Color = median of consistent-view center pixels.

Turns "match weak texture" (hard) into "verify a plane point" (easy). Density limited
only by photometric consistency → arbitrarily dense (ZNCC median stays 0.79 at 2/1/0.5cm
→ gate does NOT loosen with density; densifying only adds real points).

**Three strategic wins:**
1. **Resolves depth ambiguity** → points locked to the certified plane, depth noise = 0,
   no bas-relief shell / double-wall / fuzzy contour. Cross-section proof
   (`ghost_crosssection.png`): production has a thick ±60mm slab + sub-floor ghost band;
   plane-sweep is a razor-thin single plane, zero sub-floor points.
2. **Potentially ship-friendly algorithm core**: pure geometry/shader with no learned-model
   dependency, cross-platform in principle (C++/Dawn/WGSL), and embarrassingly-parallel
   multi-view NCC. The clean rerun now removes all LoFTR-derived statistics inputs; A16
   validation and product integration remain outstanding.
3. **Generalizes to any known plane** (walls, ceiling — ARKit plane anchors on-device).

## Honest limits
- **Planar surfaces only** (floor/walls/ceiling). Non-planar content (objects, furniture)
  is correctly REJECTED (patches don't align off-plane) → left to feature matching. Natural
  complement: flat low-texture surfaces → plane-sweep; textured objects → SIFT/detector-free.
- **Precise ghost REMOVAL is NOT solved universally.** plane-sweep is precise about what it
  BUILDS (verified on-plane points), not about identifying old ghost points to delete.
  "Cull off-plane points in the floor footprint" is a blunt heuristic that would kill real
  objects-on-floor. Only the "below-the-plane = ghost" physical prior (nothing real below a
  floor) gives a precise-ish cull, and only for single-level floors — breaks on multi-level /
  strongly-reflective / mis-fit-plane scenes. Universal ghost targeting remains the hard
  (coin-flip) problem the L1/L2 ghost campaign wrestled with.
- **Pure zero-texture surfaces still fail** (no photometric signal to verify) — but real
  indoor surfaces (wood floor, plaster, wallpaper) have enough micro-texture.
- **On-device memory**: 66×4K = 1.6GB > phone jetsam ~3GB headroom → needs streaming/tiling
  (plane-sweep is naturally tileable by floor region).

## Supporting levers (matcher-agnostic, pure CPU geometry — portable to any matcher/A16)
- **Native resolution** (LoFTR 640→1024): +48% new holes, reproj IMPROVES 1.09→0.91px.
  (Expanding candidate pairs = net negative, dropped.)
- **Finer #12 quantization** (GRID 8→4) + polluted-track split: floor good points 1435→3480
  (+142%), quality up (nview≥3 0.24→0.44), survives 2px stricter gate.
- Dead ends: conf<0.2 (stored data exhausted, = noise), track-completion 3rd view (floor 21 pts).

## Matcher licensing (separate non-planar detector-free branch)
- ⚠️ Current Kornia **LoFTR-indoor = ScanNet-trained = non-commercial ToU = SHIP BLOCKER.**
- Candidate audit path: **ELoFTR / MatchAnything with Apache-2.0 code and
  MegaDepth-outdoor weights**. Repository license, exact weight provenance/terms,
  transitive dependencies, export/runtime behavior, and mobile quality all require
  independent verification before this may be called commercially eligible.
- RoMa-outdoor (MIT/MegaDepth): strongest recall, keep as Mac offline branch (DINOv2 CoreML hard).
- GIM (MIT, cleanest license/best zero-shot). MASt3R/DUSt3R = CC-BY-NC → rejected.
- RoMa/DKM **indoor/ScanNet weights are non-commercial** — only use outdoor/MegaDepth.
- ⚠️ HF `zju-community/efficientloftr` checkpoint is BROKEN (200-330px garbage matches) —
  use official ZJU3DV repo weights, re-verify.

## Files
- `fr_planesweep_wall_ceiling.py` — clean tiled structural runner for floor/walls/ceiling;
  per-point view selection, bounded image cache, exact all-pairs clique, and strict rescue gate.
- `fit_structural_planes.py` — derives sweep domains from the first-party sparse cloud and
  known floor metadata; never consumes matcher rescue outputs.
- `test_fr_planesweep_wall_ceiling.py` — deterministic geometry, clique, cache-selection,
  floor-domain, and rescue-gate tests.
- `fr_planesweep.py` — **the plane-sweep densifier** (`GS` env var = grid size). Core result.
- `fr_common.py` — shared geometry + gates (Sampson/MAGSAC/reproj<3/tri≥2/GRID/floor plane).
- `build_floor_rescue.py` — data prep (poses.json, production_floor.ply, floor frames).
- `fr_match_loftr.py` / `fr_select_pairs.py` — LoFTR matching (Kornia indoor, MPS) + pair selection.
- `fr_triangulate.py` — #12 quantize + #14 MAGSAC + ARKit multi-view DLT + gates.
- `fr_improved.py` — finer grid + polluted-track split (Lever C).
- `fr_color_render.py` / `fr_render_maxed.py` — production-faithful colorize (px·scale−0.5
  bilinear, avg over obs, round) + top-down true-color render.
- `fr_merge.py` / `fr_quality.py` — merge A∪B∪C + adversarial quality check.
- `ghost_xsec.py` / `ghost_render.py` — floor cross-section (ghost proof).
- `*.png` — true-color overlays; `*.ply` — colored result clouds; `*_stats.json` — metrics.
- ⚠️ `fr_coverage_map.py` imports `fr_planesweep` without `__main__` guard → re-runs it;
  add a guard before reuse. Intermediate `*.npz` are gitignored (regenerate via scripts).

## Repro
`python3.11` (system python3=3.14 has a broken cv2/vtk). Needs cap50 frames + poses
(see `poses.json`, `floor_frame_ids.json`) + highres photos (gitignored `photos_highres/`).
