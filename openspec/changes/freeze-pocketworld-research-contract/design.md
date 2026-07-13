## Context

The independent research Git root is based on `0a1931658ffff4d2e606b87b197656fe8a14025d`; the original checkout has 6,339 untracked entries and about 133 GB of data. Work therefore occurs only in sparse worktree `codex/pocketworld-repro-contract-20260714`, with exact-path staging and no broad copy/add operation.

Cap50 has a complete 115-frame selected closure but an incomplete 139-frame live-feed archive. Cap51 has two distinct concerns that must not be conflated: its capture archive is missing 105/105 photos, while the host replay executable actually consumes `sfm_live.db` plus `sfm_fed_frames.jsonl` as pose JSONL. The current scratch pair has 105 DB images (`image_id` 1–105), 105 pose records (`frameId` 0–104), complete keypoint/descriptor rows, and SQLite `integrity_check=ok`; nevertheless, the user explicitly requires a fresh device pull and new hashes before A/B, so current bytes remain provisional.

Four requested PLY outputs and seven discovered NPZ files are ignored by Git. The historical `fr_planesweep.py` run produced accepted points without a learned matcher, but the script still reads a LoFTR-derived rescue PLY for coverage statistics. Therefore the historical run is not yet a standalone license-clean executable closure. B/C and merged outputs contain LoFTR-indoor/ScanNet lineage and are non-commercial research evidence.

The host has about 21 GiB free on a 98%-full encrypted APFS volume and 18 GB RAM. Capture data contains a private indoor environment, trajectories, timestamps, and potentially identifying content. No sensitive asset bytes may leave the host; public package-index metadata access for tool locking is a separate, logged action and must not include project paths or data.

## Goals / Non-Goals

**Goals:**

- Preserve every available irreproducible byte in explicit bounded collections without modifying source bytes.
- Create separate cap50, cap51 capture-archive, and cap51 replay-fixture contracts.
- Give each asset ordered relative identity, role, bytes, SHA-256, DVC OID, evidence role, license status, platform qualification, and lineage status.
- Preserve the four requested PLY files and all seven discovered NPZ files with an auditable inclusion inventory.
- Require full reproducibility metadata: Git/code identity, producer and target stacks, effective config/hash, command, seed/determinism, environment/lock, model/license evidence, metrics/thresholds, exclusions, stopping rules, outputs, deviations, and verdict.
- Use a streaming verifier, locked NPZ inspection, serial batches, and predictive resource gates.

**Non-Goals:**

- Phone access, fresh device copy, A/B execution, plane-sweep rerun, product/algorithm edit, model download, MLflow run, or product qualification.
- Claiming same-disk DVC is disaster recovery.
- Treating missing cap51 photos as the replay blocker; the replay blocker is absence of a fresh, capture-bound, quiescent DB/pose fixture.
- Claiming the historical pure-A run is license-verified or cross-platform-qualified before removing its LoFTR-derived statistics dependency and rerunning.
- Preserving duplicate tar/expanded images, duplicate PLY copies, broad logs, or the whole scratchpad.

## Decisions

### 1. Local-only DVC with precise sparse ownership

Initialize DVC only in the isolated research Git root. Extend sparse checkout only to `data/pocketworld_captures`; do not materialize historical sibling data. Before real data, use a tiny ignored `.npz/.db/.ply/photos_highres` fixture to prove DVC creates pointers without requiring `git add -f` of binary bytes. Binary force-add is prohibited.

Use dedicated cache `/Users/kaidongwang/.cache/dvc/pocketworld-research-contract-20260714`, configured by `dvc cache dir --local`; tracked DVC policy prefers `reflink,hardlink,copy`. There is no remote. The dedicated content-addressed cache is never automatically pruned or deleted during rollback.

### 2. Separate durable collections

```text
data/pocketworld_captures/
  cap50/
    raw/photos_highres/
    derived/work_1024x576/
    private_manifests/
    sfm/
  cap51/
    capture_archive_provisional/
    incremental_ba_fixture_provisional/

experiments/floor_plane_sweep_densifier_2026-07-13/
  contract/
  intermediates/matches/
  intermediates/merge_inputs/
  outputs/
```

Cap50 preserves 115 JPEG/JSON pairs, 115 exact PNG inputs, the 139-frame feed ledger, subset metadata, ghost mask, sparse PLY, and references to tracked poses/floor IDs.

Cap51 capture archive records 0/105 image bytes, the 81-frame bundle, feed ledger, and sparse PLY. Cap51 replay fixture preserves DB/WAL/SHM plus the feed ledger as pose JSONL, with explicit DB-image/pose alignment evidence. Pre/post source hash and stat stability are required; DVC grouping identifies final bytes but does not prove source-time atomicity.

The experiment inventory preserves four requested outputs, two merge inputs, five match NPZ files, `xsec_data.npz`, and `_shell_cache.npz`. The last two are diagnostic/cache roles, not automatic run dependencies. The inventory records producer, consumer, inclusion reason, and evidence role for every NPZ.

### 3. Three immutable contracts

- `cap50-floor-plane-sweep-v1`: `preserved_incomplete_feed`; valid only for the selected 115-frame closure.
- `cap51-capture-archive-provisional-v1`: records the photo archive gap; it says nothing by itself about replay executability.
- `cap51-incremental-ba-fixture-provisional-v1`: records current DB/pose alignment but is `provisional_not_verdict_eligible` because the bytes were not freshly pulled from a quiescent producer under the new contract. A morning pull creates a new immutable contract ID and hashes.

### 4. Separate license, platform, role, and lineage axes

Each asset/run records:

- `license_status`: `verified_eligible`, `ineligible`, or `unknown_pending_audit`;
- `platform_qualification`: `mac_only`, `cross_platform_unverified`, or an explicit verified platform set;
- `evidence_role`: input, intermediate, diagnostic, output, or research upper bound;
- `lineage_contains_noncommercial`: Boolean plus named sources.

Historical pure-A is `unknown_pending_audit`, `mac_only`, and has non-commercial statistics lineage because `fr_planesweep.py` reads a LoFTR-derived rescue PLY. B/C and merged outputs are `ineligible` for commercial shipment and `research_upper_bound`. No report may collapse these axes into one optimistic label.

### 5. Producer truth is distinct from target policy

Contracts record the actual historical producer stack without rewriting it to the user's new target. `producer_stack` may contain 4.0.4/3.14-dev/unknown with deviations. `consumer_target_stack` records COLMAP 4.1.0. Future A binds algorithm identity `0a8b8428`; future Ceres source-of-truth is submodule tag 2.2. Neither target is retroactively assigned to old artifacts.

### 6. Verifier and NPZ safety

The base verifier uses Python 3.11 and streams hashes in fixed chunks. The repository-local `uv.lock` also pins NumPy 2.4.2 for `allow_pickle=False` and object-dtype inspection of NPZ evidence. Tests precede implementation for path safety, exact file sets, deterministic JSON, contract gates, and NPZ rejection.

Normalized `effective-config.json` uses only repository-relative asset IDs. Historical scripts with hard-coded scratch paths are explicitly `evidence_source_not_runnable`; parameterizing them is a later change.

### 7. Predictive resource and privacy gates

Before every collection, compute `batch_bytes` and require:

```text
free_bytes >= 15 GiB + 2 * batch_bytes + 256 MiB
free_memory_percent >= 20
```

The factor of two covers worst-case workspace plus cache copies even though APFS reflink is expected. Process serially, one file at a time. Use `DVC_NO_ANALYTICS=1`; verify empty remote separately from the logged network-action inventory. Public dependency resolution is allowed only for package names/versions, never asset data or private paths.

## Risks / Trade-offs

- **Same-disk loss remains open** → State it in every verdict; later authorize an encrypted external-drive remote.
- **Cap51 source triplet may not be a single SQLite moment** → Preserve pre/post stable bytes as provisional; canonical fixture requires quiescent/checkpointed pull plus integrity/alignment checks.
- **Sparse/ignore rules can tempt force-add** → Probe exact ignored suffixes first; staged payload guard rejects JPEG, DB, PLY, NPZ, or photo bytes.
- **Historical pure-A claim can be misread** → Mark license unknown and add a prominent README boundary before any product gate.
- **Target stack can overwrite historical truth** → Store producer and consumer target stacks separately.
- **Dedicated cache can outlive a failed worktree** → Never auto-delete cache objects; record exact recovery/cleanup instructions for user review.

## Migration Plan

1. Amend and strictly validate OpenSpec; create normalized contract skeletons.
2. TDD the streaming verifier and locked NPZ inspector.
3. Expand sparse checkout only to the new capture root; initialize DVC and probe ignored suffix behavior/reflink.
4. Compute predictive disk budgets and source manifests.
5. Clone, hash, and DVC-add each bounded ownership unit serially.
6. Generate all three contracts, NPZ inventory, normalized config, DVC/network/resource reports, and README license boundary.
7. Run tests, DVC/OpenSpec/Git payload checks, then independent spec and quality reviews.
8. Commit only metadata and pointers. On failure, remove only newly materialized worktree data/pointers after evidence review; never auto-delete cache or source bytes.

## Open Questions

- Morning device access must identify the exact cap51 capture directory and produce a fresh DB plus pose JSONL (or prove the existing pose ledger belongs to that exact capture) with new hashes, pull time, quiescence/integrity evidence, and DB/pose alignment.
- No encrypted external backup target has been authorized, so single-disk recovery remains unresolved.
