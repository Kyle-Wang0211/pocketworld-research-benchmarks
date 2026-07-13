## Why

The cap50 plane-sweep evidence and cap51 incremental-BA fixture currently depend on an ephemeral scratchpad, untracked binary artifacts, and incomplete input identity. A local, content-addressed research contract is required now so later E/A/B experiments cannot silently change inputs, lose evidence, or overstate non-commercial results as a shippable baseline.

## What Changes

- Add a versioned schema and deterministic verifier for ordered input, configuration, environment, model/license, metric, artifact, and verdict identity.
- Freeze the available cap50 capture inputs, sparse input, four requested PLY outputs, and all associated NPZ files in a local-only DVC dataset with SHA-256 manifests.
- Separate cap51 capture-archive evidence from the actual replay fixture (`sfm_live.db` plus pose JSONL); preserve both provisionally, but require a fresh, capture-bound, quiescent device pull with new hashes before A/B verdict use.
- Separate license status, platform qualification, evidence role, and non-commercial lineage. Historical pure-A remains license-unknown until its LoFTR-derived statistics dependency is removed and independently rerun; B/C and merged evidence remain non-commercial upper bounds.
- Pre-register predictive disk, memory, privacy, provenance, and verification gates. No DVC remote, sensitive upload, phone access, experiment execution, or product-code change is part of this change; public package-index access may occur only for named development dependencies and is logged separately.
- Keep large capture data, databases, PLY, and NPZ bytes out of Git; Git stores only DVC pointers, manifests, schema, small configuration, documentation, and tests.

## Capabilities

### New Capabilities

- `research-data-contract`: Defines deterministic asset identity, eligibility labels, local DVC ownership, privacy constraints, and fail-closed verification for PocketWorld experiments.

### Modified Capabilities

None.

## Impact

- Repository: `pocketworld_research_benchmarks` only, on an isolated branch/worktree based on `0a1931658ffff4d2e606b87b197656fe8a14025d`.
- New local tooling: repository-local DVC metadata and a Python 3.11 verifier with a repository-local lock for its test environment.
- Local storage: selected assets are cloned/content-addressed on the same Mac; no remote backup is claimed, and work stops before free disk falls below the pre-registered safety floor.
- Downstream experiments: cap51 A/B remains blocked until a fresh DB/pose fixture is capture-bound, hashed, integrity-checked, and aligned; E shutter/thermal design, B wall/ceiling plane-sweep, C A16, and D detector-free remain separate changes.
