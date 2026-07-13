# Floor densification: known-plane plane-sweep vs detector-free rescue (cap50, 2026-07-13)

**All experiments run on Mac (M3 Pro, torch-MPS) — no remote GPU box. No production code touched.**

## Problem
cap50's floor is weakly textured → production SIFT leaves holes + a "ghost layer"
(sub-floor double-floor shell from depth ambiguity). Goal: densify the floor with
**more good points, no quality drop**, purely photometric (Android/HarmonyOS have no LiDAR).

## Headline result

| | SIFT (prod) | LoFTR rescue | **plane-sweep + maxed** |
|---|---|---|---|
| Floor coverage | 2.75 m² | +0.70 m² (+25%) | **5.84 m² (+112%)** |
| Good points | 5845 | 1435 | **18,076 (1cm) / 55,192 (5mm)** |
| New holes filled (SIFT=0) | — | 0.70 m² | **3.09 m² (4.4×)** |
| Sub-floor ghost points | 3540 (4.7%) | (inherits) | **0** |

Every point passes strict gates — no quality relaxation (see below).

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
2. **Ship-friendly**: pure geometry/shader, **zero license**, cross-platform (C++/Dawn/WGSL),
   multi-view NCC is embarrassingly-parallel → ideal A16 GPU load. Closest compliant
   pure-photometric replica of competitor LiDAR density.
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

## Matcher licensing (for the non-planar detector-free rescue branch)
- ⚠️ Current Kornia **LoFTR-indoor = ScanNet-trained = non-commercial ToU = SHIP BLOCKER.**
- Ship path: **ELoFTR / MatchAnything (Apache-2.0, MegaDepth-outdoor weights, fp16 opt)** —
  only speed+cross-platform(MNN/CoreML)+license triple-clean semi-dense option.
- RoMa-outdoor (MIT/MegaDepth): strongest recall, keep as Mac offline branch (DINOv2 CoreML hard).
- GIM (MIT, cleanest license/best zero-shot). MASt3R/DUSt3R = CC-BY-NC → rejected.
- RoMa/DKM **indoor/ScanNet weights are non-commercial** — only use outdoor/MegaDepth.
- ⚠️ HF `zju-community/efficientloftr` checkpoint is BROKEN (200-330px garbage matches) —
  use official ZJU3DV repo weights, re-verify.

## Files
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
