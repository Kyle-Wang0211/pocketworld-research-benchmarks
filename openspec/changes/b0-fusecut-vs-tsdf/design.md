## Context

The source prompt is `B0_TO_B3_EXECUTE_PROMPT.md`.  The later user amendment
selects the complete cap50 material instead of the earlier 48-frame plumbing
sample because cap50 contains 115 valid local photographs.  The immutable common
cache is `20260722_cap50_115_common_v3`: its input contract SHA-256 is
`d760407e4852c36eb8a2d209d342fce79e1a4ef0726cc46692edcd75928cf711`,
the camera-Z depth cache is
`e33407e5e5e627b0a84bc04b99e22014200595568805264c61eaebf624ca40d8`,
and the model cache is
`345f9a540e0759103b0682b3e9bd9c957bb9831196a2f3cb2eea454641e54b8c`.
The fixed physical scale is `1.007804831494465` metres per model unit.

There is no independent geometric ground truth.  Results therefore measure
held-out observation consistency, not true completeness or ground-truth
accuracy.

## Goals / Non-Goals

**Goals:**

- Decide whether FuseCut passes every strict non-inferiority gate relative to
  the current 6 mm TSDF on cap50.
- Make the comparison reproducible and auditable from immutable identities.
- Preserve failed, stopped, and invalid attempts rather than overwriting them.
- Allow the 413-frame gate only after a cap50 pass.

**Non-Goals:**

- Tuning either backend after inspecting output.
- Per-route ICP, Sim(3), scale fitting, cleanup, smoothing, or hole filling.
- Product integration, B4-B7 migration, or replacement of TSDF.
- Claiming independent geometric truth from held-out photographs.

## Decisions

### One common input, one experimental variable

Both routes consume the same 93-name reconstruction list, 22-name held-out
list, `dmcache.npz`, `model_cache.npz`, image-root manifest, cameras, masks,
coordinate frame, scale, and seed.  The only differing factor is
`meshing_backend`: current physical 6 mm TSDF versus AliceVision FuseCut with a
frozen command.  Exact hashes are checked again at every formal phase.

Alternative rejected: independent route preprocessing or tuning.  It would
confound the backend comparison.

### Held-out split and leakage prevention

Local indices `4, 9, ..., 109` are held out, yielding 22 frames; the remaining
93 frames reconstruct the mesh.  Held-out frames cannot be reference images,
source images, or neighbors during reconstruction.  They are consumed only by
the common evaluator.

### Depth and coordinate semantics

The common cache stores positive-finite camera-Z depth in the optimized SfM
model frame.  TSDF consumes camera-Z directly.  The FuseCut adapter performs the
required deterministic conversion to Euclidean ray distance:

`d_ray = d_z * sqrt(((u-cx)/fx)^2 + ((v-cy)/fy)^2 + 1)`.

The adapter round-trip relative error must be at most `1e-6`.  Evaluation stays
in the common model frame; no per-route alignment is allowed.

### Preregistered gates

FuseCut must satisfy all of these deltas relative to TSDF: total, low-texture,
and weak-support coverage each at least `-0.02`; unsupported surface over 20 mm
at most `+0.02`; median AbsRel at most `+0.005`; P95 AbsRel at most `+0.02`;
median normal error at most `+2 degrees`; double-shell rate at most `+0.01` and
P95 shell separation at most `+0.005 m`.  Its non-manifold edge fraction must be
at most `1e-4`, and vertices/faces must be finite.

Any claim of improved weak-surface preservation additionally requires paired
frame bootstrap with 10,000 draws and seed `20260721`, with the 95% lower bound
at least `+0.05` for both low-texture and weak-support coverage while every
non-inferiority gate passes.

Alternative rejected: relaxing the cap50 gates because it is smaller than the
413-frame scene.  The original strict thresholds remain fixed.

### Symmetric local-degenerate-face sanitation

The first formal evaluation attempt stopped before producing any quality metric
because the TSDF output contained 17 local triangles with double area at or
below `float64` epsilon among 1,328,679 faces.  The original B0 gates did not
register “any zero-area face” as a whole-mesh rejection criterion.  That failed
attempt remains immutable evidence and is not reinterpreted as an algorithm
result.

The corrected evaluator applies one frozen rule to both routes before ray
casting: report raw topology, then exclude only triangles whose double area is
non-finite or `<= np.finfo(np.float64).eps`.  It records input, excluded, and
evaluated face counts.  Bad shape, empty input, non-finite vertices, invalid
indices, a single-triangle specimen, or fewer than two remaining positive-area
triangles still make metrics undefined.  Non-manifold topology does not abort
evaluation because it is an explicit strict comparison gate.  No welding,
repair, remeshing, smoothing, coordinate change, or route-specific operation is
allowed.

Because the correction changes executable evaluator semantics, the next formal
attempt SHALL use a new preregistration and run root and SHALL repeat both mesh
routes under the same commands.  The failed run and its logs remain preserved.

### Fail-closed execution and provenance

Every phase runs through the monitored wrapper, which revalidates the exact
preregistered child argv, source bundle, native binary, Python environment,
prior statuses, and output attestations before accepting a PASS.  Resource
limits are 12 GiB peak RSS, 4 GiB swap growth, four hours wall time, at least
15 GiB free before a phase, and a stop below 6 GiB.

Repository-local `uv.lock` freezes Python dependency resolution.  DVC records
the external large-input identity manifest and the phase dependency graph.
MLflow records the contract identity, parameters, status, metrics, resource
observations, and small evidence artifacts; it does not replace DVC or the
immutable filesystem artifacts.

## Risks / Trade-offs

- **Held-out views are not independent geometry** -> Report only observation
  consistency and explicitly retain this limitation.
- **FuseCut requires a Z-to-ray adapter** -> Enforce a numerical round-trip test
  and preserve adapter provenance.
- **Different backend representations are unavoidable** -> Hold upstream
  evidence and downstream evaluation constant; name the backend as the sole
  variable.
- **Resource exhaustion could truncate a route** -> Monitor and stop at frozen
  thresholds; classify it as `TIMEOUT`, `DISK_GUARD`, or resource failure, not
  as evidence of impossible algorithmic quality.
- **Dirty/untracked research code is mutable** -> Hash the complete executable
  source bundle and reject drift at phase launch.
- **A few local zero-area triangles could mask all metrics** -> Apply the same
  frozen face predicate to both routes, preserve raw topology, record all
  exclusions, and reject only when fewer than two usable faces remain.

## Migration Plan

1. Freeze dependencies, OpenSpec requirements, DVC identities, MLflow run, and
   a new preregistration contract before any mesh output exists.
2. Prepare held-out evaluation input once.
3. Run TSDF, then FuseCut export and meshing, sequentially.
4. Evaluate both with the same prepared held-out data and compare against the
   frozen gates.
5. Preserve every artifact and status.  Run 413 frames only after a cap50 PASS.
6. If the result does not justify adoption, retain TSDF and stop; product
   migration requires a separate approved change.

## Open Questions

- Whether cap50 passes strongly enough to authorize the conditional 413-frame
  gate; this is determined only by the frozen evaluator.
- Whether a passing 413-frame result warrants a separate product-adoption ADR.
