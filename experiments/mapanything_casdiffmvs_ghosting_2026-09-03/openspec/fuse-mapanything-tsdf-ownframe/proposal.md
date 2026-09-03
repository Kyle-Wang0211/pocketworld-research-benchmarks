# Change: TSDF fusion of official MapAnything per-view outputs in the model's own frame

## Objective

Produce a single-surface true-colour point cloud from the unmodified official
Apache MapAnything image-only outputs (predicted depth_z, predicted K,
predicted cam2world, official mask including edge mask) by multi-view TSDF
integration, without any confidence pruning, downsampling, external camera
data, or per-frame rescaling.  The user lifted the "pure official raw output"
restriction on 2026-09-03 ("任何方法都行，只要没有重影、肉眼正常").

Authority for the step: MapAnything maintainer Nik-V9, issue #76 (2025-11-16):
"We have found TSDFusion to very effective in getting meshes from MapAnything
predictions."  Implementation: Open3D (MIT) `ScalableTSDFVolume` (CPU) and
`t.geometry.VoxelBlockGrid` (CUDA); call pattern and the 7.8 mm / 40 mm
reference parameters mirror Depth-Anything-3's Apache-2.0 bench utils
(`src/depth_anything_3/bench/utils.py`, `ScalableTSDFVolume(voxel 4/512,
sdf_trunc 0.04)`).

Why the model's own frame: the layer audit
(`audit-mapanything-layer-attribution`) showed the predicted depth is only
cross-view consistent under the predicted K and predicted poses; substituting
COLMAP K and/or poses makes the official consistency metric worse.

## Frozen identities

- Per-view inputs: `/root/mapanything_layer_audit_A_imgs132_up_20260903/`
  (official `model.infer` replay of `/root/imgs132_up`, commit
  `3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9`, checkpoint revision
  `00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a`, 132 views at 392x518,
  25,150,854 official-mask pixels; tensor SHA-256 list in `SHA256SUMS.npy.txt`).
- Scripts: `/root/tsdf_fuse_mapanything.py` (CPU), `/root/tsdf_fuse_gpu.py`
  (CUDA), `/root/ply_to_verdict_bins.py` (mechanical PLY -> viewer bytes).
  Local copies under `_host_experiments.nosync/mapanything_layer_audit_20260903/`.
- Open3D 0.19.0.

## Variants run 2026-09-03

| variant | backend | voxel | sdf_trunc | weight | points | PLY SHA-256 | time |
|---|---|---|---|---|---|---|---|
| reference | ScalableTSDFVolume CPU | 7.8125 mm | 40 mm | > 0 | 2,968,480 | `836bbb80…eb42e` | 20 s, 3.9 GB RSS |
| dense | VoxelBlockGrid CUDA | 3 mm | 40 mm | >= 1 | 19,569,198 | `45b9f5b8…b56b5` | 41 s, 96,769 active blocks |
| denser | VoxelBlockGrid CUDA | 2 mm | 40 mm | >= 1 | 43,199,189 | `0d068af9…46d1b` | 11 s, 219,584 active blocks, 7.2 GB RSS; kept on remote only (2.2 GB PLY, above the 20–30M band) |

The 3 mm CPU attempt hit `std::bad_alloc` at 23 GB RSS (legacy volume
allocates full units along every truncated ray); the CUDA backend is the
Open3D-documented path for fine voxels.  CUDA integrate requires (uint16
depth, uint8 colour); depth is quantised at 0.2 mm (`depth_scale` 5000),
two orders of magnitude below the voxel.

Viewer pages (mechanical byte copy, node matrix = the official exporter's
180-degree X rotation):

- `verdict_page/mapanything_tsdf_fusion_ownframe_20260903/` (7.8 mm reference,
  POSITION `aa84fe9d…59f46`, RGB `4dd0a127…5ac94`)
- `verdict_page/mapanything_tsdf_gpu_3mm_ownframe_20260903/` (3 mm,
  POSITION `c12c6ab1…313db`, RGB `729c60c5…af683`)

## Required gates

- No vertex synthesized, moved, or deleted after extraction; point count is
  whatever the isosurface yields at the chosen voxel size.
- Only one full-resolution page loaded at a time on the 18 GB Mac.
- Numeric consistency cannot accept visual quality.  The user's inspection of
  floor, white walls, suitcase, mirror/reflective areas and the long axis is
  the only ghosting verdict.

## Stop conditions

- Stop if the saved tensor hashes change, the official mask is altered, or any
  confidence/percentile pruning is introduced.
- Do not overwrite historical artifacts.  Do not touch the production phone.

## User verdict

Pending at the time of writing.
