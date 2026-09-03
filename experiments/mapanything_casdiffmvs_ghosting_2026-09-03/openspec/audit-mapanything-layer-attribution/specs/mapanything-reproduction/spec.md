## ADDED Requirements

### Requirement: Layer attribution uses official outputs and official metric only

The diagnostic SHALL replay the pinned upstream image-only inference with the
demo's exact arguments, SHALL persist the raw per-view output tensors
unchanged, and SHALL evaluate cross-view consistency only with the upstream
`compute_multiview_depth_confidence` function at its default thresholds.

#### Scenario: Valid diagnostic replay

- **WHEN** the upstream commit is `3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9`,
  the checkpoint revision is `00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a`, and
  the ordered input manifest matches the frozen identity
- **THEN** the replay saves every tensor-valued output key for all 132 views and
  records inference time, peak CUDA memory, and the demo-export vertex count

#### Scenario: Substitution attribution

- **WHEN** predicted depth is held fixed and predicted K and/or predicted pose
  are replaced by the production COLMAP reference brought to model resolution
  through the official `preprocess_inputs`
- **THEN** the diagnostic reports the official per-frame consistency statistic
  for every substitution and does not modify, filter, or export any geometry

### Requirement: Diagnostic results do not constitute a candidate

The diagnostic SHALL NOT produce a point cloud, GLB, PLY, or viewer page, and
its numbers SHALL NOT be used to claim that ghosting has been reduced.

#### Scenario: Reporting

- **WHEN** the diagnostic finishes
- **THEN** the report names the first layer at which geometry departs from the
  reference, states every unproven inference as unproven, and leaves the
  quality verdict to the user's visual inspection
