## ADDED Requirements

### Requirement: Upstream CasDiffMVS run is unmodified and fully identified

The run SHALL use a pristine clone of cvg/diffmvs at a recorded commit, an
official checkpoint with a recorded SHA-256, the frozen MVSNet-format input with
a per-file SHA-256 list, and the user-signed OFFICIAL real-scene arguments,
including the official `filter.py` fusion.

#### Scenario: Valid official run

- **WHEN** the upstream commit, checkpoint hash and input hash list are recorded
  and `test.py` is invoked with the OFFICIAL arguments
- **THEN** the fused `pc.ply` is preserved unchanged and its point count, wall
  time and hash are recorded

### Requirement: Candidate presentation and verdict

The viewer SHALL copy the fused vertex positions and colours byte-for-byte and
SHALL state the full chain; only the user's visual inspection determines the
verdict.

#### Scenario: Visual verdict

- **WHEN** the page is presented
- **THEN** a candidate not explicitly passed by the user is recorded as
  candidate or failed, never as fixed
