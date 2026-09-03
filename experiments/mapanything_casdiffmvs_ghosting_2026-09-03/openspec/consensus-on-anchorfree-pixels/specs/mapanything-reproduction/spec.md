## ADDED Requirements

### Requirement: Only anchor-free pixels are averaged

The refinement SHALL leave every anchored pixel's depth unchanged, SHALL apply
the official consistency thresholds and averaging formula only to anchor-free
pixels, and SHALL keep the point set identical to the raw MapAnything cloud
with original colours.

#### Scenario: Valid run

- **WHEN** the anchored native depths and the CasDiffMVS fusion masks come from
  the recorded runs
- **THEN** the run records the anchor coverage, the fraction of anchor-free
  pixels with a consistent partner, the relative depth change, the official
  consistency before and after both overall and on anchor-free pixels, the
  point count and the PLY hash

### Requirement: Candidate presentation and verdict

The viewer SHALL copy vertex positions and colours byte-for-byte and SHALL state
the full chain; only the user's visual inspection determines the verdict.

#### Scenario: Visual verdict

- **WHEN** the page is presented
- **THEN** a candidate not explicitly passed by the user is recorded as
  candidate or failed, never as fixed
