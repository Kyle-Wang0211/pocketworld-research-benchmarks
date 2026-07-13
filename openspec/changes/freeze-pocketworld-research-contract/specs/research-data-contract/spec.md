## ADDED Requirements

### Requirement: Repository and sparse ownership are exact
The system SHALL use DVC only in the isolated `pocketworld_research_benchmarks` worktree, SHALL extend sparse checkout only to the new `data/pocketworld_captures` subtree, and SHALL reject repository-root, historical top-level `data`, or scratchpad-root selections.

#### Scenario: Exact root is accepted
- **WHEN** preservation starts
- **THEN** Git and DVC resolve to the isolated research root based on `0a1931658ffff4d2e606b87b197656fe8a14025d`

#### Scenario: Broad selection is rejected
- **WHEN** a requested add resolves to a broad or historical root
- **THEN** no data is copied or added

### Requirement: Sensitive storage remains local
Capture and experiment bytes SHALL remain on the encrypted local volume, SHALL use a dedicated local DVC cache, SHALL configure no DVC remote, and SHALL remain outside Git payloads. Empty remote state and absence of sensitive network transfer SHALL be verified as separate facts.

#### Scenario: Local-only DVC verifies
- **WHEN** preservation completes
- **THEN** `dvc remote list` is empty and the command log contains no sensitive-data network operation

#### Scenario: Git payload is safe
- **WHEN** staged files are inspected
- **THEN** no JPEG, DB, WAL, SHM, PLY, NPZ, or capture payload is staged, including by force-add

### Requirement: Ignored asset behavior is proven before real copy
The system SHALL use a tiny fixture matching existing ignored `photos_highres`, DB, PLY, and NPZ patterns to prove DVC pointer behavior without force-adding binary bytes.

#### Scenario: Ignore probe passes
- **WHEN** the fixture is DVC-added
- **THEN** only pointer/ignore metadata is Git-visible and the binary fixture remains untracked by Git

### Requirement: Asset identity is deterministic and fail closed
Every asset SHALL have a unique POSIX relative path, role, bytes, lowercase SHA-256, DVC OID, license status, platform qualification, evidence role, and non-commercial-lineage flag. Verification SHALL stream one file at a time and reject absolute/traversal paths, symlinks, duplicates, missing/extra files, or content mismatch.

#### Scenario: Exact collection verifies
- **WHEN** file set, bytes, and hashes match
- **THEN** canonical JSON output is stable across repeated runs

#### Scenario: Unsafe or changed collection fails
- **WHEN** any unsafe path, symlink, duplicate, extra, missing, or changed byte is present
- **THEN** verification fails without updating expected identity

### Requirement: Full reproducibility truth is mandatory
Each contract SHALL record Git root/branch/commit/dirty-diff hash; code/script hashes; producer stack; consumer target stack; ordered inputs; effective config and hash; command; seeds/determinism; Python/uv lock and hardware/backend; model source/revision/weight hash/license evidence; metrics/thresholds; exclusions; stopping rules; output hashes; deviations; and verdict.

A verdict-eligible contract SHALL declare `contract_kind` and `validation_scope=decision_contract`, use closed unique identifiers and evidence roles, contain nonempty runnable code/config/command, finite metric thresholds and observations, stopping rules, and preserved `verdict_input`/`verdict_output` evidence. Contract JSON SHALL be canonical and SHALL reject duplicate keys and non-finite numbers. Verification SHALL rehash repository-local code, config, verifier lock, verdict evidence, and single-file DVC OIDs without opening provisional raw evidence.

#### Scenario: Historical and target stacks differ
- **WHEN** an old artifact predates COLMAP 4.1.0
- **THEN** its producer stack remains historical/unknown and 4.1.0 appears only as consumer target policy

#### Scenario: Required evidence is absent
- **WHEN** a required field is unknown
- **THEN** the contract records `null` plus a deviation and cannot upgrade the related verdict

### Requirement: Cap50 closure is explicit
The cap50 contract SHALL preserve 115 paired 3840×2160 JPEG/sidecars, 115 exact 1024×576 PNG inputs, live ledger, subset metadata, poses, floor IDs, ghost mask, and direct sparse PLY. It SHALL enumerate 24 unavailable names from the 139-frame feed.

#### Scenario: Selected closure verifies
- **WHEN** cap50 is checked
- **THEN** 115 pairs and 115 PNG inputs resolve exactly and the status is `preserved_incomplete_feed`

#### Scenario: Live denominator is retained
- **WHEN** the live ledger is compared to raw inputs
- **THEN** exactly 24 missing names are reported and 139 is not redefined as 115

### Requirement: Cap51 archive and replay fixture are separate
The system SHALL create a capture-archive contract for missing photos and a replay-fixture contract for DB plus pose JSONL. Photo absence SHALL NOT by itself decide replay eligibility.

#### Scenario: Capture archive records photo gap
- **WHEN** cap51 archive is verified
- **THEN** it records 0/105 photo bytes independently of replay status

#### Scenario: Current provisional replay pair is inspected
- **WHEN** scratch DB and pose JSONL are checked
- **THEN** DB image IDs, keypoint/descriptor rows, pose frame IDs, SQLite integrity, hashes, and capture identity are recorded

#### Scenario: A/B requests current provisional fixture
- **WHEN** the DB/pose bytes lack a fresh user-authorized pull and quiescence/capture-binding evidence
- **THEN** status remains `provisional_not_verdict_eligible` before metrics run

#### Scenario: Fresh canonical fixture arrives
- **WHEN** a fresh quiescent device pull passes integrity and DB/pose alignment
- **THEN** a new immutable contract ID and hashes are created rather than mutating provisional evidence

The replay decision SHALL be typed in `replay_qualification`; freshness, pull time, device/app/revision, source and ledger capture directories, quiescence or consistent backup, atomic DB/WAL, integrity, alignment, and DB/WAL/pose/SHM references SHALL NOT be hidden in free-form details. SHM SHALL be `excluded_volatile` with `replay_identity_included=false`.

### Requirement: PLY and complete NPZ inventory are preserved
The system SHALL preserve four requested output PLY files, two merge-input PLY files, five match NPZ files, `xsec_data.npz`, and `_shell_cache.npz`. Each NPZ SHALL record filename, bytes, SHA, producer, consumer, role, and inclusion reason.

#### Scenario: Requested PLY outputs verify
- **WHEN** outputs are checked
- **THEN** all four names, hashes, formats, and vertex counts match pre-copy evidence

#### Scenario: NPZ archives are safe
- **WHEN** all seven NPZ files are inspected with locked NumPy
- **THEN** `allow_pickle=False` succeeds and no object dtype is present

### Requirement: License, platform, role, and lineage are independent
Every artifact SHALL record separate license status, platform qualification, evidence role, and non-commercial lineage. Historical pure-A SHALL remain `unknown_pending_audit` until its LoFTR-derived statistics dependency is removed and a clean rerun is audited. B/C and merged evidence SHALL be commercially ineligible research upper bounds.

Code, model weights, training data, and tools SHALL be separate dependency records with exact `audit_verdict`, intended use, obligations, and immutable license evidence. A used model SHALL reference one model dependency and all training-dataset dependencies; unrelated source-code evidence SHALL NOT back model identity. Commercial candidates SHALL accept only `allow` dependencies. Clean user-owned private inputs and derived outputs MAY be included only with a rights basis and rights-evidence SHA-256.

#### Scenario: Historical pure-A is reported
- **WHEN** `floor_planesweep.ply` is summarized
- **THEN** it is Mac-only, license-unknown pending audit, and not product-qualified

#### Scenario: Non-commercial lineage is reported
- **WHEN** B/C or merged evidence is summarized
- **THEN** LoFTR-indoor/ScanNet lineage is explicit and excluded from commercial gates

### Requirement: Effective configuration is normalized
The system SHALL create a repository-relative `effective-config.json`, record historical `grid_m=0.01` over script default `0.02`, and mark hard-coded scratch scripts as evidence sources that are not directly runnable.

#### Scenario: Runnable metadata is scanned
- **WHEN** versioned contract/config is checked
- **THEN** it contains no `/private/tmp` or mobile-container path while immutable raw evidence may retain original bytes

### Requirement: Source stability and SQLite consistency are explicit
Provisional persistent DB/WAL copy SHALL use pre/post hash and stat checks. The transient SHM wal-index SHALL be excluded from replay-fixture identity and retained only as drift evidence. Canonical fixture SHALL require producer quiescence or a consistent backup/checkpoint, followed by read-only integrity and DB/pose alignment checks on a clone rather than the scratch source.

#### Scenario: Source changes during copy
- **WHEN** any source stat or hash changes
- **THEN** the new destination is rejected and no snapshot claim is made

### Requirement: Predictive resource gates prevent exhaustion
Before every batch, the system SHALL know batch bytes and require free disk of at least `15 GiB + 2×batch_bytes + 256 MiB`, free memory of at least 20%, and serial one-file-at-a-time processing.

#### Scenario: Worst-case budget fails
- **WHEN** predicted workspace-plus-cache amplification crosses the disk floor
- **THEN** the batch is not started

#### Scenario: Memory gate fails
- **WHEN** system-wide free memory is below 20%
- **THEN** processing pauses before loading the next file

### Requirement: Same-disk limitation and cache rollback are safe
The contract SHALL state that local DVC is not disaster recovery. Rollback SHALL NOT automatically prune or delete dedicated content-addressed cache objects.

#### Scenario: Preservation completes or fails
- **WHEN** a handoff is written
- **THEN** single-disk risk and user-reviewed cache cleanup instructions remain explicit

### Requirement: README cannot imply commercial qualification
Before any product gate, the experiment README SHALL visibly separate pure-A metrics from LoFTR-derived upper-bound metrics and SHALL state that historical pure-A is pending a standalone license audit/rerun.

#### Scenario: Reader sees headline metrics
- **WHEN** README performance claims are displayed
- **THEN** no `+112%` merged result is presented as zero-license or commercially shippable
