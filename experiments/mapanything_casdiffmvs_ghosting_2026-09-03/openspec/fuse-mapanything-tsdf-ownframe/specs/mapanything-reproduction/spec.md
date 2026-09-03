## ADDED Requirements

### Requirement: TSDF fusion consumes official outputs unchanged

The fusion SHALL integrate only the official per-view `depth_z`, predicted
intrinsics, predicted cam2world poses and the official `mask` (non-ambiguous
and edge) from the pinned inference replay, and SHALL NOT apply confidence
percentile pruning, per-frame rescaling, external camera data, or
downsampling.

#### Scenario: Valid fusion run

- **WHEN** the saved tensor directory matches its recorded SHA-256 list and the
  fusion is run with an Open3D TSDF volume at a declared voxel size and
  truncation
- **THEN** the run records voxel size, truncation, weight threshold, integrated
  pixel count, extracted point count, PLY SHA-256, wall time and peak memory

#### Scenario: Altered inputs

- **WHEN** any input tensor, mask, or camera differs from the frozen replay
- **THEN** the run is not a valid candidate and must be re-labelled as a new
  experiment

### Requirement: Candidate presentation and verdict

The candidate viewer SHALL copy the extracted vertex positions and colours
byte-for-byte and SHALL state the full chain, including that TSDF is an
external fusion step recommended by the maintainer, not part of the official
demo.

#### Scenario: Visual verdict

- **WHEN** the page is presented
- **THEN** only the user's visual inspection determines whether ghosting is
  acceptable, and a candidate not explicitly passed by the user is recorded as
  "candidate" or "failed", never as "fixed"
