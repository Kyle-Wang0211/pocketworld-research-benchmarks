## Why

PocketWorld has a working 6 mm TSDF mesher and a newly available AliceVision
FuseCut path, but there is no controlled evidence that FuseCut produces a better
surface from the same reconstruction evidence.  A preregistered cap50 comparison
is needed before any product adoption or larger migration is justified.

## What Changes

- Add a research-only, fail-closed A/B harness for 6 mm TSDF versus FuseCut.
- Freeze cap50 as 115 valid photographs: 93 reconstruction frames and 22
  held-out evaluation frames.
- Keep every input, camera, scale, mask, seed, evaluation rule, and environment
  fixed; the meshing backend is the only experimental variable.
- Record exact input, code, binary, environment, command, resource, and output
  identities before accepting results.
- Apply the original strict B0 non-inferiority thresholds without post-result
  tuning; run the 413-frame gate only if cap50 passes.
- Add repository-local OpenSpec, `uv.lock`, DVC identity/graph metadata, and an
  MLflow run ledger for reproducibility.
- Do not change product code or execute the unapproved B4-B7 work.

## Capabilities

### New Capabilities

- `meshing-backend-ab`: Reproducible, controlled comparison of two mesh-fusion
  backends under one immutable input and evaluation contract.

### Modified Capabilities

None.

## Impact

The change is confined to research scripts, tests, experiment specifications,
and run metadata in `pocketworld_research_benchmarks`.  It uses the existing
arm64 AliceVision meshing executable and the existing Python scientific runtime.
It does not modify the PocketWorld application, shipping ABI, or user data.
