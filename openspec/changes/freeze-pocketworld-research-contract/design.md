## Context

The research repository is an independent Git root at commit `0a1931658ffff4d2e606b87b197656fe8a14025d`, but the original checkout contains 6,339 untracked entries and approximately 133 GB of data. The implementation therefore runs in the sparse isolated worktree `codex/pocketworld-repro-contract-20260714` and never performs broad add/copy operations against the original checkout.

The available cap50 closure is useful but incomplete relative to the live feed: 115 paired 4K JPEG/sidecar records exist, while the feed ledger names 139 frames. An exact 115-image 1024×576 preprocessing set also exists. Cap51 is more incomplete: the feed ledger names 105 images and the bundle selects 81, but no cap51 image bytes are available tonight; only a SQLite database/WAL/SHM triplet, metadata, and sparse PLY remain. The cap51 material is therefore preservation evidence, not a canonical A/B fixture.

Four requested PLY outputs and the experiment NPZ files are ignored by Git. The pure-A output is commercially plausible but only Mac/Python-tested. B/C and the merged upper-bound output use LoFTR-indoor/ScanNet evidence and are non-commercial diagnostics. The recorded pure-A run uses `grid_m=0.01`, while the script default is `0.02`; the effective value must outrank the default.

The host has about 21 GiB free on a 98%-full encrypted APFS data volume and 18 GB RAM. The capture contains a private indoor environment, full camera trajectories, and potentially identifying scene content. No remote or cloud transfer is permitted by this change.

## Goals / Non-Goals

**Goals:**

- Move the available irreproducible bytes out of the ephemeral scratchpad into a clear repository-owned layout without changing their contents.
- Give every file an ordered relative identity, byte count, SHA-256, role, eligibility label, and DVC object identity.
- Preserve raw inputs, exact preprocessing inputs, direct sparse input, the four requested output PLY files, reconstruction intermediates required by the merged output, and all relevant NPZ files.
- Make missing cap50/cap51 frames, non-commercial model evidence, and non-canonical cap51 database status impossible to overlook.
- Provide a deterministic streaming verifier and tests that fail closed on missing, changed, duplicate, absolute, or symlinked assets.
- Keep large/sensitive bytes local and out of Git while retaining at least 15 GiB free disk throughout the operation.

**Non-Goals:**

- Phone access, device copy, A/B execution, plane-sweep rerun, model download, build, MLflow run creation, product-code edit, or README performance re-claim.
- Claiming backup against disk loss; local DVC on the same encrypted volume protects identity and scratchpad lifetime, not single-disk failure.
- Treating cap51 as canonical or allowing its preserved database to produce a verdict.
- Treating LoFTR-indoor B/C or merged outputs as commercially shippable.
- Preserving `images_full.tar.gz`, AppleDouble entries, `_shell_cache.npz`, broad logs, or the whole scratchpad when an exact selected representation exists.

## Decisions

### 1. Use local-only DVC plus Git metadata

Initialize DVC only in the independent research Git root. Track selected data in multiple small ownership units rather than adding the repository, `data/`, or scratchpad wholesale. Configure no remote. Use a user-local cache path through untracked DVC local configuration; tracked configuration prefers `reflink,hardlink,copy` in that order. Verify actual materialization on APFS and abort if it becomes an unexpected full-copy expansion.

Alternatives considered:

- Git/LFS was rejected because no LFS source of truth exists, sensitive bytes must not be uploaded, and normal Git would bloat history.
- A plain checksum directory was rejected because it lacks DVC dependency identity and reliable materialization/status checks.
- An encrypted external-drive DVC remote is a future backup option, not part of tonight's same-disk preservation.

### 2. Separate capture data from experiment-specific artifacts

Use these durable roots:

```text
data/pocketworld_captures/
  cap50/
    raw/photos_highres/
    derived/work_1024x576/
    manifests/
    sfm/
  cap51/
    manifests/
    sfm/live_snapshot_provisional/

experiments/floor_plane_sweep_densifier_2026-07-13/
  contract/
  intermediates/matches/
  intermediates/merge_inputs/
  outputs/
```

The cap50 raw set contains the 115 exact JPEG/JSON pairs. The derived set contains the 115 exact 1024×576 PNG files, not the tar archive. Capture manifests include the 139-frame live ledger and explicitly list the 24 unavailable frame names. The cap51 provisional unit contains the DB/WAL/SHM triplet as one atomic group plus the 105-frame feed ledger, 81-frame bundle, sparse PLY, and explicit `0/105 images available` status.

The experiment unit contains the four requested PLY outputs; `floor_rescue_D_band.ply` and `floor_rescue_band_improved.ply` because the merged output depends on them; five match NPZ files; and `xsec_data.npz` as a diagnostic-only item. `_shell_cache.npz` is excluded because no tracked experiment path references it.

### 3. Treat existing bytes as immutable evidence

Materialize with APFS clone semantics where available, then independently stream-hash source and destination. Never rewrite sidecars to remove absolute paths during preservation; doing so would change evidence. Instead, the durable manifest records normalized relative destinations and flags embedded absolute paths as privacy/provenance findings. Future runnable configs must be separate normalized files.

### 4. Use two explicit contracts

- `cap50-floor-plane-sweep-v1`: status `preserved_incomplete_feed`, because the selected 115-frame closure is complete but 24 of 139 live-fed frames are unavailable. It can reproduce only claims bound to the 115-frame selection.
- `cap51-incremental-ba-provisional-v1`: status `provisional_not_verdict_eligible`, because 105/105 image bytes are absent and the SQLite triplet was not freshly pulled or backed up from a proven-quiescent producer. The later canonical contract must receive a new ID and fresh SHA values after a device pull.

### 5. Make commercial eligibility a typed field

Each artifact records `commercial_eligibility` and `evidence_scope`:

- pure-A `floor_planesweep.ply`: `candidate_unproven_cross_platform`;
- B/C NPZ and LoFTR-derived/merged outputs: `noncommercial_research_upper_bound`;
- cap50 production sparse and SIFT-only evidence: `input_only`, not a product verdict.

No aggregate report may promote a non-commercial component by merging it with a commercial candidate.

### 6. Deterministic verifier and schema

Create a Python 3.11, standard-library streaming verifier inside the experiment contract. It hashes one file at a time using fixed chunks, rejects absolute paths and symlinks, enforces unique POSIX relative paths, checks byte counts and SHA-256, verifies the DVC pointer/status externally, and emits canonical JSON with sorted keys. A repository-local `uv.lock` pins the verifier/test environment even though runtime dependencies are empty.

Tests are written first for canonical ordering, mutation detection, missing files, duplicates, symlink rejection, and the explicit provisional cap51 gate.

### 7. Resource and privacy gates

Before each materialization batch:

- require at least 15 GiB free disk;
- record `memory_pressure -Q`; stop if free memory is below 20%;
- process files serially and never load image/NPZ payloads wholesale;
- disable DVC analytics and verify `dvc remote list` is empty;
- keep the cache and materialized data on the encrypted local volume with user-only permissions;
- do not inspect scene pixels for this preservation change and do not upload any bytes.

## Risks / Trade-offs

- **Same-disk DVC is not disaster recovery** → State this in every contract and add an encrypted physical-drive remote only through a later approved change.
- **APFS clone/hardlink support may fall back to copy** → Test a small fixture first, inspect free space after every batch, and stop below 15 GiB.
- **Cap51 DB/WAL/SHM may not be a consistent logical snapshot** → Preserve all three together, label them provisional, and forbid verdict use; later create a quiescent backup from the fresh device pull.
- **Cap50 is incomplete relative to the live feed** → Preserve both the 115 selected closure and the 139-frame ledger; enumerate the missing 24 rather than silently shrinking the denominator.
- **Absolute paths and private spatial data remain inside immutable evidence** → Keep data local, restrict permissions, surface the risk in metadata, and use separate normalized configs for future runs.
- **DVC pointer integrity does not prove experiment semantics** → The contract also pins code revision, script hashes, effective `grid_m=0.01`, model/license scope, metrics, exclusions, and verdict eligibility.
- **A worktree can later be deleted** → Keep DVC cache outside the worktree and do not remove the worktree until pointers, manifests, and recovery commands are committed and independently verified.

## Migration Plan

1. Create and test the schema/verifier on tiny fixtures.
2. Initialize DVC locally with no remote and validate APFS link behavior on a small test asset.
3. Record pre-copy disk/memory state and source hashes.
4. Clone selected cap50/cap51/experiment assets into the durable layout in bounded batches.
5. Run source-versus-destination SHA checks, then `dvc add` each ownership unit separately.
6. Generate and verify the two contracts, missing-frame lists, DVC status, no-remote state, Git large-file guard, and absence of scratchpad paths from runnable config.
7. Commit only metadata, pointers, small manifests, tests, and documentation on the isolated branch.
8. Rollback, if any verification fails, by removing only the newly created worktree data/pointers/cache objects; never touch the original scratchpad or original repository checkout.

## Open Questions

- The canonical cap51 capture directory and image bytes can only be resolved after the user authorizes morning device access. This blocks experiment A but does not block provisional preservation.
- A separate encrypted physical-drive DVC remote would close the single-disk-loss risk, but no target drive or retention policy has been authorized.
