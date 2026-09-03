## ADDED Requirements

### Requirement: Corrections reach the cloud only through a smooth per-view field

Any depth correction SHALL be applied as a smooth per-view field multiplying the
MapAnything depth, and SHALL NOT modify per-pixel depth relationships by
averaging, filtering or resampling the depth map.

#### Scenario: Valid correction

- **WHEN** cross-view evidence or anchor evidence is available
- **THEN** it enters the data term of the smooth field solve, and the exported
  depth is the base depth multiplied by the solved field

#### Scenario: Subset treatment is forbidden

- **WHEN** a treatment would apply to a hard subset of pixels such as a mask or
  a threshold region
- **THEN** it is rejected, because the subset boundary becomes a depth seam;
  the evidence goes into the smooth field instead

### Requirement: Candidates are screened by three calibrated rulers

A candidate SHALL be measured for seam ratio along the anchor-mask boundary,
separated-layer fraction, and high-frequency content relative to the reference
version, and SHALL only be presented when the separated-layer fraction improves
while the other two stay within a small margin of the reference.

#### Scenario: Screening

- **WHEN** a candidate is produced
- **THEN** the three rulers are recorded together with the official
  self-consistency value, and the official value is explicitly marked as
  unusable for choosing a winner

#### Scenario: Visual verdict

- **WHEN** a screened candidate is presented
- **THEN** only the user's visual inspection decides, and a candidate not
  explicitly passed is recorded as candidate or failed, never as fixed
