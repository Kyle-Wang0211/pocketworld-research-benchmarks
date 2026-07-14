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

Cap51 capture archive records 0/105 image bytes, the 81-frame bundle, feed ledger, and sparse PLY. Cap51 replay fixture preserves persistent DB/WAL bytes plus the feed ledger as pose JSONL, with explicit DB-image/pose alignment evidence. The `-shm` wal-index is transient coordination/cache state, not replay input or persistent database identity; its observed drift is retained as audit evidence rather than copied into the fixture. Pre/post source hash and stat stability are required. Integrity queries run only against a stable clone or SQLite backup, never the scratch source. DVC grouping identifies final bytes but does not prove source-time atomicity. See SQLite's official [WAL-mode file format](https://www.sqlite.org/walformat.html#the_wal_index_or_shm_file), which states that the wal-index is transient and reconstructible from the WAL.

The experiment inventory preserves four requested outputs, two merge inputs, five match NPZ files, `xsec_data.npz`, and `_shell_cache.npz`. The last two are diagnostic/cache roles, not automatic run dependencies. The inventory records producer, consumer, inclusion reason, and evidence role for every NPZ.

### 3. Three immutable contracts

- `cap50-floor-plane-sweep-v1`: `preserved_incomplete_feed`; valid only for the selected 115-frame closure.
- `cap51-capture-archive-provisional-v1`: records the photo archive gap; it says nothing by itself about replay executability.
- `cap51-incremental-ba-fixture-provisional-v1`: records current DB/pose alignment but is `provisional_not_verdict_eligible` because the bytes were not freshly pulled from a quiescent producer under the new contract. A morning pull creates a new immutable contract ID and hashes.

Each contract declares `contract_kind` and `validation_scope`. Replay truth is a
typed top-level qualification, not a collection of booleans in evidence
`details`. A valid replay decision binds a new contract ID to fresh authorized
device-pulled DB/WAL/pose bytes, source app revision and capture identity,
quiescence or consistent backup, integrity, and alignment; SHM is always
excluded from replay identity. Experiment A additionally fixes the algorithm
identity to `0a8b8428fba3fbf942af01ada6d1e1252a677c6a`, requires the production
default to remain disabled, fixes the sole control variable to
`AETHER_INCREMENTAL_GLOBAL_BA` (`unset` versus `1`), and requires an explicit
proof that no other control variable differs between arms.

### 4. Separate license, platform, role, and lineage axes

Each asset/run records:

- `license_status`: `verified_eligible`, `ineligible`, or `unknown_pending_audit`;
- `platform_qualification`: `mac_only`, `cross_platform_unverified`, or an explicit verified platform set;
- `evidence_role`: input, intermediate, diagnostic, output, or research upper bound;
- `lineage_contains_noncommercial`: Boolean plus named sources.

Historical pure-A is `unknown_pending_audit`, `mac_only`, and has non-commercial statistics lineage because `fr_planesweep.py` reads a LoFTR-derived rescue PLY. B/C and merged outputs are `ineligible` for commercial shipment and `research_upper_bound`. No report may collapse these axes into one optimistic label.

Commercial auditing is layered on the generic research verdict. Code, model
weights, training datasets, and tools have separate dependency identities,
`audit_verdict`, intended use, obligations, and immutable evidence. Only
`allow` dependencies qualify a candidate. The cap50 LoFTR Apache code surface is
not evidence for the indoor weights or ScanNet dataset; those surfaces remain
blocked/insufficient and explicitly linked by the model record.

A commercial candidate must explicitly assert that its declared execution
dependency closure is complete. Every runnable code entry and the command name
the dependency IDs they execute; the command also names every and only runnable
code ID, the one effective-config ID, and every and only used model ID. The
declared dependency set must equal this code/command/model/dataset/runtime
closure, so an empty surface or unreferenced padding cannot satisfy the gate.
Every dependency license file and every model weight/license file is an
immutable repository-relative path with a verified hash. This is a strict
declared-closure gate, not automatic binary or dynamic-runtime dependency
discovery; a candidate cannot claim completeness without independent evidence
that its declaration covers the real execution surface.

### 5. Producer truth is distinct from target policy

Contracts record the actual historical producer stack without rewriting it to the user's new target. `producer_stack` may contain 4.0.4/3.14-dev/unknown with deviations. `consumer_target_stack` records COLMAP 4.1.0. Future A binds algorithm identity `0a8b8428`; future Ceres source-of-truth is submodule tag 2.2. Neither target is retroactively assigned to old artifacts.

### 6. Verifier and NPZ safety

The base verifier uses Python 3.11 and streams hashes in fixed chunks. The repository-local `uv.lock` also pins NumPy 2.4.2 for `allow_pickle=False` and object-dtype inspection of NPZ evidence. Tests precede implementation for path safety, exact file sets, deterministic JSON, contract gates, and NPZ rejection.

Normalized `effective-config.json` uses only repository-relative asset IDs. Historical scripts with hard-coded scratch paths are explicitly `evidence_source_not_runnable`; parameterizing them is a later change.

Contract loading rejects duplicate keys, non-finite JSON, and noncanonical
bytes. This includes rejecting numeric overflow such as `1e9999`, which a normal
JSON parser could otherwise convert to infinity. Metric decisions bind every
threshold to an exact `(metric_id, artifact_id)` observation, require a finite
numeric observation, evaluate `>`, `>=`, `<`, `<=`, and `==`, and require the
stored verdict decision to equal the computed pass/fail result. Multiple metrics
may legitimately reference one output artifact.

Command identity is closed independently of verdict status: each code entry has
a stable ID and dependency IDs, effective config has a stable ID, and the known
command references every and only runnable code, the exact config, every
declared used model, and its execution dependencies.

`verify-contract` and `gate-verdict` always validate current repository truth,
including provisional contracts. They verify the declared Git root, branch,
commit ancestry, and tracked/staged dirty diff; rehash every non-null code,
config, verifier-lock, preserved-evidence, DVC, commercial license, and model
weight/license claim; and also rehash a materialized repository-local
`source_evidence_only` file. Missing unpreserved external source evidence may
remain unavailable, but preserved evidence is never skipped. All repository
file checks use no-follow, mutation-detecting reads.

### 7. Predictive resource and privacy gates

Before every collection, compute `batch_bytes` and require:

```text
free_bytes >= 15 GiB + 2 * batch_bytes + 256 MiB
free_memory_percent >= 20
```

The factor of two covers worst-case workspace plus cache copies even though APFS reflink is expected. Process serially, one file at a time. Use `DVC_NO_ANALYTICS=1`; verify empty remote separately from the logged network-action inventory. Public dependency resolution is allowed only for package names/versions, never asset data or private paths.

## Risks / Trade-offs

- **Same-disk loss remains open** → State it in every verdict; later authorize an encrypted external-drive remote.
- **Cap51 DB/WAL pair may not be a single SQLite moment** → Preserve only pre/post stable persistent bytes as provisional; exclude volatile SHM from fixture identity. Canonical fixture requires a quiescent pull or a consistent SQLite backup/checkpoint plus integrity/alignment checks on a clone.
- **Sparse/ignore rules can tempt force-add** → Probe exact ignored suffixes first; staged payload guard rejects JPEG, DB, PLY, NPZ, or photo bytes.
- **Historical pure-A claim can be misread** → Mark license unknown and add a prominent README boundary before any product gate.
- **Target stack can overwrite historical truth** → Store producer and consumer target stacks separately.
- **Dedicated cache can outlive a failed worktree** → Never auto-delete cache objects; record exact recovery/cleanup instructions for user review.

## Migration Plan

1. Amend and strictly validate OpenSpec; create normalized contract skeletons.
2. TDD the streaming verifier and locked NPZ inspector.
3. Expand sparse checkout only to the new capture root; initialize DVC and probe ignored suffix behavior/reflink.
4. Compute predictive disk budgets and source manifests.
5. Clone, hash, and DVC-add each bounded ownership unit serially; never open the original SQLite source with a normal WAL reader.
6. Generate all three contracts, NPZ inventory, normalized config, DVC/network/resource reports, and README license boundary.
7. Run tests, DVC/OpenSpec/Git payload checks, then independent spec and quality reviews.
8. Commit only metadata and pointers. On failure, remove only newly materialized worktree data/pointers after evidence review; never auto-delete cache or source bytes.

## Open Questions

- Morning device access must identify the exact cap51 capture directory and produce a fresh DB plus pose JSONL (or prove the existing pose ledger belongs to that exact capture) with new hashes, pull time, quiescence/integrity evidence, and DB/pose alignment.
- No encrypted external backup target has been authorized, so single-disk recovery remains unresolved.
