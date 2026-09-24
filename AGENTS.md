# Project Guardrails

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

