## 1. Contract Tooling

- [ ] 1.1 Add the Python 3.11 contract package metadata and generate a repository-local `uv.lock` with no unreviewed runtime dependency.
- [ ] 1.2 Write failing tests for canonical ordering, missing/mutated files, duplicate/absolute/parent-traversal paths, symlinks, and provisional cap51 verdict rejection.
- [ ] 1.3 Implement the streaming manifest verifier until all contract tests pass with one-file-at-a-time memory use.
- [ ] 1.4 Add JSON schema and eligibility vocabulary for asset identity, DVC identity, privacy, commercial scope, effective config, metrics, deviations, and verdict.

## 2. Local DVC Safety Setup

- [ ] 2.1 Record disk and memory baselines and abort if free disk is below 15 GiB or free-memory pressure is below 20%.
- [ ] 2.2 Initialize DVC only in the isolated research worktree, disable analytics, configure a user-local cache and tracked `reflink,hardlink,copy` preference, and confirm there is no remote.
- [ ] 2.3 Run a small APFS materialization fixture and verify hash equality, link behavior, DVC status, and bounded disk growth before copying capture assets.

## 3. Cap50 Preservation

- [ ] 3.1 Clone and hash the 115 paired 4K JPEG/sidecar files into `data/pocketworld_captures/cap50/raw/photos_highres` without rewriting bytes.
- [ ] 3.2 Clone and hash the 115 exact 1024×576 PNG inputs into `data/pocketworld_captures/cap50/derived/work_1024x576`, excluding the tar and AppleDouble duplicate representation.
- [ ] 3.3 Preserve the 139-frame live ledger, selected-subset metadata, poses, 66 floor-frame IDs, ghost mask, and direct sparse PLY; generate the exact 24-frame missing list.
- [ ] 3.4 Add cap50 ownership units to DVC separately and verify source/destination/DVC identities.

## 4. Cap51 Provisional Preservation

- [ ] 4.1 Clone the DB/WAL/SHM triplet as one provisional raw unit and preserve the 105-frame feed ledger, 81-frame bundle, and sparse PLY.
- [ ] 4.2 Generate a cap51 manifest that records `0/105` referenced image bytes available and status `provisional_not_verdict_eligible`.
- [ ] 4.3 Add the provisional unit to DVC and prove the verifier blocks incremental-BA verdict use.

## 5. Plane-Sweep Evidence Preservation

- [ ] 5.1 Preserve the four requested output PLY files and verify their pre-copy SHA-256 and vertex metadata.
- [ ] 5.2 Preserve the two merge-input PLY files, five match NPZ files, and `xsec_data.npz`; verify every NPZ with `allow_pickle=False` and no object dtype.
- [ ] 5.3 Record pure-A as `candidate_unproven_cross_platform`, B/C and merged evidence as `noncommercial_research_upper_bound`, and effective `grid_m=0.01` as authoritative over the script default.
- [ ] 5.4 Add experiment ownership units to DVC separately and verify no duplicate tar, duplicate PLY copy, or `_shell_cache.npz` entered the closure.

## 6. Final Verification and Handoff

- [ ] 6.1 Verify both contracts, canonical JSON stability, DVC status, empty DVC remote list, `uv lock --check --offline`, and a clean OpenSpec validation.
- [ ] 6.2 Scan tracked/staged files for large binary payloads and scan runnable config for `/private/tmp` or mobile-container absolute paths.
- [ ] 6.3 Record final disk/memory state, DVC OIDs, artifact hashes, deviations, same-disk backup limitation, and exact recovery commands.
- [ ] 6.4 Run an independent read-only review against the specification and correct every material finding before committing the metadata-only change.
