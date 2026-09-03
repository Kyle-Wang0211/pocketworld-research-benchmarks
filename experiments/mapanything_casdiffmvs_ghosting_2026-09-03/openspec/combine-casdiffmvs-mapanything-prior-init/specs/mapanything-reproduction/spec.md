## ADDED Requirements

### Requirement: Prior injection is the only difference from the official run

The combined run SHALL differ from the official CasDiffMVS run only in the
depth used to initialise the diffusion refinement, and SHALL record the prior
alignment statistics, the fraction of pixels replaced, and the fused point
count and hash.

#### Scenario: Valid combined run

- **WHEN** the prior maps are built from the frozen MapAnything tensors with the
  verified source-to-frame mapping and the official fusion masks
- **THEN** inference uses the unmodified upstream checkpoint, loader, arguments,
  seed and fusion, and the output is preserved unchanged

### Requirement: Candidate presentation and verdict

The viewer SHALL copy vertex positions and colours byte-for-byte and SHALL state
the full chain; only the user's visual inspection determines the verdict.

#### Scenario: Visual verdict

- **WHEN** the page is presented
- **THEN** a candidate not explicitly passed by the user is recorded as
  candidate or failed, never as fixed
