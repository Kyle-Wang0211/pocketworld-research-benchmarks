## ADDED Requirements

### Requirement: Anchoring keeps every MapAnything pixel and only moves depth

The anchoring SHALL keep every MapAnything-mask pixel as a point with its
original colour, SHALL change depth only through a smooth per-view offset field
fitted to CasDiffMVS fusion-kept depths, and SHALL unproject with the
production COLMAP cameras.

#### Scenario: Valid anchoring run

- **WHEN** the prior maps, the CasDiffMVS depths and fusion masks come from the
  recorded runs
- **THEN** the run records anchor coverage, offset-field statistics, the
  official multi-view consistency before and after, the point count and the
  PLY hash

### Requirement: Candidate presentation and verdict

The viewer SHALL copy vertex positions and colours byte-for-byte and SHALL state
the full chain; only the user's visual inspection determines the verdict.

#### Scenario: Visual verdict

- **WHEN** the page is presented
- **THEN** a candidate not explicitly passed by the user is recorded as
  candidate or failed, never as fixed
