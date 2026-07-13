## ADDED Requirements

### Requirement: Repository-scoped data ownership
The system SHALL initialize and use DVC only in the independent `pocketworld_research_benchmarks` Git root and SHALL NOT add the aggregate Aether3D repository, the whole research `data/` tree, or the whole scratchpad.

#### Scenario: DVC root is verified
- **WHEN** preservation begins
- **THEN** the resolved Git root and DVC root are the isolated research worktree based on commit `0a1931658ffff4d2e606b87b197656fe8a14025d`

#### Scenario: Broad add is rejected
- **WHEN** an input selection resolves to the repository root, the top-level historical `data/` tree, or the scratchpad root
- **THEN** preservation stops without adding any asset

### Requirement: Local-only sensitive storage
The system SHALL keep capture images, camera metadata, databases, PLY, and NPZ bytes on the encrypted local volume, SHALL configure no DVC remote, and SHALL keep large bytes out of Git.

#### Scenario: No remote is configured
- **WHEN** the completed contract is verified
- **THEN** `dvc remote list` is empty and no network transfer occurred

#### Scenario: Git contains only metadata
- **WHEN** Git-staged files are inspected
- **THEN** only DVC pointers, manifests, schema, small configuration, tests, and documentation are present

### Requirement: Deterministic ordered asset identity
Every preserved asset SHALL have a unique POSIX relative path, role, byte count, lowercase SHA-256, eligibility label, and DVC identity in an ordered manifest. Verification SHALL stream one file at a time and fail closed on an absolute path, symlink, duplicate path, missing file, byte mismatch, or hash mismatch.

#### Scenario: Unmodified asset verifies
- **WHEN** every destination file matches its recorded byte count and SHA-256
- **THEN** the verifier emits a deterministic success report with stable canonical JSON

#### Scenario: Asset mutation is detected
- **WHEN** one preserved byte changes
- **THEN** verification fails and identifies the relative path without updating the expected hash

#### Scenario: Unsafe path is rejected
- **WHEN** a manifest contains an absolute path, parent traversal, duplicate path, or symlinked asset
- **THEN** verification fails before accepting the contract

### Requirement: Cap50 closure is explicit
The cap50 contract SHALL preserve 115 paired 3840×2160 JPEG/sidecar records, 115 exact 1024×576 PNG preprocessing inputs, the live feed manifest, selected-subset metadata, poses, floor-frame IDs, ghost mask, and direct sparse PLY. It SHALL report that 24 of 139 live-fed frames are unavailable and SHALL bind any reproduction claim to the 115-frame selection.

#### Scenario: Cap50 selected closure is complete
- **WHEN** the cap50 contract is verified
- **THEN** all 115 JPEG stems have one sidecar, all 115 preprocessing images exist, and the selected-subset manifest resolves exactly those 115 inputs

#### Scenario: Missing live frames remain visible
- **WHEN** the 139-frame live ledger is compared with preserved raw inputs
- **THEN** the contract lists exactly 24 unavailable frame identifiers and does not redefine the live denominator as 115

### Requirement: Cap51 remains provisional until fresh device copy
The available cap51 DB/WAL/SHM triplet, 105-frame live ledger, 81-frame bundle, and sparse PLY SHALL be preserved as one provisional evidence unit. The contract SHALL record that 105 of 105 referenced image bytes are absent and SHALL be ineligible for an incremental-BA verdict.

#### Scenario: Provisional cap51 verifies
- **WHEN** the existing metadata and DB triplet match their recorded hashes
- **THEN** preservation succeeds with status `provisional_not_verdict_eligible`

#### Scenario: A/B execution is requested with provisional cap51
- **WHEN** a run attempts to use the provisional contract as its canonical fixture
- **THEN** the run is blocked before metrics are produced

#### Scenario: Fresh device fixture arrives
- **WHEN** cap51 is freshly copied from the named iPhone after user authorization
- **THEN** a new canonical contract ID and new SHA-256 values are required rather than mutating the provisional contract

### Requirement: Requested PLY and NPZ evidence is preserved without duplication
The system SHALL preserve the four requested output PLY files, the two merge-input PLY files required by the merged output, five match NPZ files, and the diagnostic `xsec_data.npz`. It SHALL NOT preserve duplicate tar/expanded images, duplicate benchmark/scratch PLY copies, or unreferenced `_shell_cache.npz` as part of the minimal closure.

#### Scenario: Four requested outputs are present
- **WHEN** the experiment artifact unit is verified
- **THEN** `production_floor.ply`, `floor_rescue_band_colored.ply`, `floor_planesweep.ply`, and `floor_maxed_colored.ply` match their pre-copy SHA-256 values

#### Scenario: NPZ safety is checked
- **WHEN** each preserved NPZ is inspected
- **THEN** it can be loaded with `allow_pickle=False` and contains no object dtype

### Requirement: Commercial evidence scope is fail closed
Every model-derived input and output SHALL record commercial eligibility. LoFTR-indoor/ScanNet B/C evidence and any merged artifact containing it SHALL be labeled `noncommercial_research_upper_bound` and SHALL NOT support a production, open-source-commercial, or cross-platform qualification claim.

#### Scenario: Pure-A output is reported
- **WHEN** `floor_planesweep.ply` is summarized
- **THEN** it is labeled `candidate_unproven_cross_platform` and not labeled delivered or production-qualified

#### Scenario: Merged output is reported
- **WHEN** `floor_maxed_colored.ply` or B/C match evidence is summarized
- **THEN** the report includes the non-commercial upper-bound label and excludes it from product gates

### Requirement: Effective configuration outranks defaults
The contract SHALL record the effective run configuration, code revision and script hashes. For the preserved pure-A result it SHALL record `grid_m=0.01` and SHALL flag the script default `0.02` as non-authoritative.

#### Scenario: Config drift is evaluated
- **WHEN** the script default differs from the preserved metrics/config evidence
- **THEN** the effective recorded value is used and the deviation is explicit

### Requirement: Resource gates prevent host exhaustion
Preservation SHALL run serially, SHALL stop before free disk falls below 15 GiB, SHALL stop when host free-memory pressure is below 20%, and SHALL test APFS link behavior before copying the full selection.

#### Scenario: Disk floor would be crossed
- **WHEN** the next preservation batch could reduce free disk below 15 GiB
- **THEN** the batch is not started and existing preserved units remain verifiable

#### Scenario: Memory pressure is unsafe
- **WHEN** the pre-batch memory check reports less than 20% free
- **THEN** hashing/materialization pauses without loading the next payload

### Requirement: Same-disk limitation is explicit
The contract SHALL state that local DVC on the same volume is not a disaster-recovery backup and SHALL provide recovery commands only for the current local cache.

#### Scenario: Preservation is complete
- **WHEN** all selected units verify locally
- **THEN** the verdict says scratchpad-loss risk is reduced but single-disk-loss risk remains open
