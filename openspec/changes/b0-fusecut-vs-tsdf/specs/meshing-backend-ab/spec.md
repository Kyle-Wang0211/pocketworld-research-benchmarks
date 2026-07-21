## ADDED Requirements

### Requirement: Immutable Common Input

The experiment SHALL use the same immutable depth cache, model cache, image
manifest, camera set, masks, scale, reconstruction list, and held-out list for
both routes.

#### Scenario: Route input differs

- **WHEN** any route-bound input identity differs from the preregistered value
- **THEN** execution or comparison SHALL stop with
  `ROUTE_INPUT_NOT_EQUIVALENT` and SHALL NOT emit a quality conclusion

### Requirement: Single Experimental Variable

The experiment SHALL vary only the meshing backend: frozen 6 mm TSDF versus
frozen AliceVision FuseCut.  It SHALL NOT apply per-route ICP, Sim(3), scale
fitting, cleanup, smoothing, hole filling, or post-result parameter tuning.

#### Scenario: Controlled cap50 comparison

- **WHEN** both formal routes execute
- **THEN** all registered controls SHALL match and only `meshing_backend` SHALL
  differ

### Requirement: Fixed cap50 Split

The cap50 universe SHALL contain exactly 115 valid photographs, with 93 frames
used for reconstruction and the fixed 22-frame set at local indices
`4,9,...,109` used only for held-out evaluation.

#### Scenario: Held-out leakage

- **WHEN** a held-out frame appears as a reconstruction reference, source, or
  neighbor
- **THEN** preregistration SHALL fail before either mesh route starts

### Requirement: Correct Depth and Coordinate Semantics

The common depth SHALL be positive-finite camera-Z in the optimized SfM model
frame.  The FuseCut adapter SHALL convert Z depth to Euclidean ray distance and
demonstrate round-trip relative error no greater than `1e-6`.  Evaluation SHALL
use the common model frame without route-specific alignment.

#### Scenario: Adapter semantics are incorrect

- **WHEN** the round-trip bound fails or raw camera-Z is written as ray distance
- **THEN** the FuseCut route SHALL be invalid and SHALL NOT be compared

### Requirement: Strict Non-Inferiority Gates

The evaluator SHALL apply the original B0 strict thresholds: each coverage
delta at least `-0.02`; unsupported-over-20-mm delta at most `+0.02`; median
AbsRel delta at most `+0.005`; P95 AbsRel delta at most `+0.02`; median normal
error delta at most `+2 degrees`; double-shell rate delta at most `+0.01`;
double-shell P95 separation delta at most `+0.005 m`; FuseCut non-manifold edge
fraction at most `1e-4`; and finite vertices and faces.

#### Scenario: Any gate fails

- **WHEN** one or more strict gates fail
- **THEN** the cap50 verdict SHALL be FAIL and the 413-frame gate SHALL NOT run

### Requirement: Symmetric Local-Degenerate-Face Sanitation

The evaluator SHALL report raw topology and SHALL apply the identical frozen
predicate `triangle_double_area > np.finfo(np.float64).eps` to both route meshes
before ray casting.  It SHALL record input, excluded, and evaluated face counts.
This sanitation SHALL NOT weld, repair, remesh, smooth, align, or otherwise
change either route.  Local zero-area faces SHALL NOT introduce an unregistered
whole-mesh gate.  Bad shape, empty input, non-finite vertices, invalid indices,
a single-triangle specimen, or fewer than two remaining positive-area triangles
SHALL leave metrics undefined.

#### Scenario: Large mesh contains isolated zero-area faces

- **WHEN** at least two positive-area triangles remain after the shared filter
- **THEN** both routes SHALL continue through the same evaluator, exclusions
  SHALL be reported, and non-manifold topology SHALL be decided only by its
  preregistered strict gate

#### Scenario: No usable mesh remains

- **WHEN** fewer than two positive-area triangles remain after filtering
- **THEN** evaluation SHALL stop with `METRIC_UNDEFINED` and emit no quality
  conclusion

### Requirement: Improvement Claim Gate

A claim that FuseCut better preserves weakly supported surfaces SHALL require
all non-inferiority gates plus a paired held-out-frame bootstrap of 10,000 draws
with seed `20260721`, whose 95% lower confidence bound is at least `+0.05` for
both low-texture and weak-support coverage.

#### Scenario: Confidence bound is insufficient

- **WHEN** either lower bound is below `+0.05`
- **THEN** the report SHALL NOT claim improved weak-surface preservation

### Requirement: Formal Resource and Provenance Enforcement

Every formal phase SHALL verify the preregistration contract, exact child argv,
source bundle, native binary, Python environment, prior phase statuses, and
output identities.  A phase SHALL start only with at least 15 GiB available and
SHALL stop below 6 GiB, above 12 GiB peak RSS, above 4 GiB swap growth, or after
four hours.

#### Scenario: Formal identity drifts

- **WHEN** code, binary, environment, command, prerequisite, or attested output
  differs from its frozen identity
- **THEN** the phase SHALL fail closed and preserve its evidence

### Requirement: Reproducible Experiment Ledger

The repository SHALL contain a valid OpenSpec change, a checked `uv.lock`, DVC
input/dependency identities, and an MLflow run recording parameters, metrics,
resources, artifact identities, deviations, and verdict.

#### Scenario: Governance record is absent

- **WHEN** any required reproducibility record is absent before meshing
- **THEN** the formal experiment SHALL not start

### Requirement: Calibrated Claim Scope

The final report SHALL describe the measurements as held-out observation
consistency and SHALL NOT call them independent ground-truth completeness or
accuracy.

#### Scenario: Experiment completes

- **WHEN** a cap50 comparison verdict is produced
- **THEN** the report SHALL include the limitation, all exact commands and
  identities, failed attempts, deviations, resource evidence, and the decision
  whether the conditional 413-frame gate is authorized
