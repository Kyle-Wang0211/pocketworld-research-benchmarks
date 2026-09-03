## ADDED Requirements

### Requirement: Consensus refinement deletes nothing and uses only model outputs

The refinement SHALL consume only the saved official per-view outputs and the
official mask, SHALL keep every masked pixel as a point with its original
colour, and SHALL use only the predicted intrinsics and poses for all
projections.

#### Scenario: Valid refinement run

- **WHEN** the saved tensors match their recorded SHA-256 list
- **THEN** the run records per-frame scales, consistency statistics before and
  after with the official metric, the unchanged point count, and the PLY hash

### Requirement: Candidate presentation and verdict

The viewer SHALL copy vertex positions and colours byte-for-byte and SHALL state
the full chain; only the user's visual inspection determines the verdict.

#### Scenario: Visual verdict

- **WHEN** the page is presented
- **THEN** a candidate not explicitly passed by the user is recorded as
  candidate or failed, never as fixed
