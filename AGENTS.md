# Project Guardrails

## Active PocketWorld reconstruction direction (user-signed 2026-07-17)

The active north star is an all-out effort to reproduce or surpass the visible
surface coherence of RealityScan using a commercially clean, image-only,
cross-platform, fully local pipeline. Research effort, engineering effort, and
token cost are not limiting factors. Existing product constraints still apply:
no LiDAR/sceneDepth dependency, no cloud reconstruction/training dependency,
and no silent regression in user-visible quality or production runtime.

This is a permanent architecture rule, not a proposal to rediscover:

- Optimize one reconstruction architecture as a whole. Never create a private
  acceptance or publication gate for each mechanism.
- The current SfM/SIFT path, B known-plane evidence, D detector-free evidence,
  P0-P3 evidence, and any future method are proposal/evidence providers only.
  C is an execution backend only. None owns product-visible geometry.
- One source-agnostic global birth controller is the sole authority allowed to
  create a user-visible Point3D/surfel identity.
- Never directly append or union a source-specific point cloud into the product
  PLY. Never compensate with a source-specific cleanup pass after publication.
- All sources must meet in one observation-site, track, visibility, and surface
  evidence graph before geometry is born. Evidence may remain provisional and
  participate internally without becoming user-visible geometry.
- Prevent floating points, ghost walls, and duplicate layers at their generation
  mechanism. Do not generate them first and delete them later.
- Preserve every accepted user photo and keep registration at 100%. Withholding
  an unproven 3D hypothesis from the visible cloud is not deletion of a frame.
- Success means more *correct, surface-supported* geometry with RealityScan-class
  or better visual coherence, not a larger point count by itself.
- Every visual comparison must hold images, production poses/finalize behavior,
  gauge, viewer, camera, and point size constant, and requires user visual review
  before the next algorithm layer is promoted.

Do not present source-specific B/D/P0-P3 gates as a future direction again. If
an experiment still has such a gate, treat it only as historical diagnostic
evidence, not as the target product architecture.

## Canonical device captures (frozen 2026-07-17)

Before accessing the iPhone for cap40, cap41, cap50, or cap51, always read
`data/pocketworld_captures/device_capture_registry.json` and verify the recorded
canonical local path and SHA-256 values. These four captures have already been
recovered from the device. Reuse the local frozen copies; do not list, copy, or
pull the same capture from the phone again unless a required canonical file is
actually absent or fails its recorded SHA-256. Never overwrite an existing
pull. The registry maps the product capture numbers to their full
`cap_<timestamp>` device identities, so do not rediscover that mapping from UI
ordering or chat history.

## DA3 replication work

For Depth-Anything-3 / PocketWorld parity tasks, the required strategy is strict
official replication. Do not design or introduce compensating algorithms unless
the user explicitly asks for a non-official product postprocess.

Hard rules:

- Treat black slabs, thick layers, multi-view overlap, floating geometry, and
  pose/depth inconsistency as parity bugs until proven otherwise.
- First compare against the official DA3 code path and identify where local
  code diverges: image decode, preprocessing, camera conventions, intrinsics,
  extrinsics, confidence contract, official postprocess, and official export.
- Do not add custom color filtering, dark-block removal, voxel cleanup,
  connected-component deletion, plane fitting, floor protection, smoothing,
  fusion, loop alignment, or geometry repair as a substitute for official parity.
- Do not present experimental postprocess outputs as fixes for DA3 parity.
- If an experiment is useful for diagnosis, label it as diagnostic only and keep
  it out of the product/baseline path unless the user explicitly approves it.

Current accepted baseline checkpoint:

- `04cb362 Checkpoint DA3 K35 official baseline`
