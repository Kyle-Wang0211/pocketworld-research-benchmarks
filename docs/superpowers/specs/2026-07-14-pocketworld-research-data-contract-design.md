# PocketWorld Research Data Contract Design

Status: approved for unattended Mac-only execution by the user on 2026-07-14. Phone access and device tests remain deferred until morning review.

The authoritative proposal, requirements, design decisions, resource gates, and implementation checklist live in:

- `openspec/changes/freeze-pocketworld-research-contract/proposal.md`
- `openspec/changes/freeze-pocketworld-research-contract/specs/research-data-contract/spec.md`
- `openspec/changes/freeze-pocketworld-research-contract/design.md`
- `openspec/changes/freeze-pocketworld-research-contract/tasks.md`

## Selected approach

Use a sparse isolated Git worktree and repository-scoped DVC with a dedicated local-only content-addressed cache. Git stores only small specifications, manifests, configuration, tests, and DVC pointers. Selected sensitive bytes remain on the encrypted Mac; there is no DVC remote or asset upload. Each serial batch requires at least `15 GiB + 2×batch bytes + 256 MiB` free and 20% free-memory pressure.

This was chosen over normal Git/LFS, which would bloat or upload sensitive history, and over a plain checksum folder, which lacks DVC materialization and dependency identity. An encrypted external-drive DVC remote is a future option but is not authorized tonight.

## Frozen truth boundaries

- cap50 is a complete 115-frame selected closure but an incomplete 139-frame live feed; the missing 24 identifiers remain explicit.
- cap51 capture archive has no image bytes tonight, but replay depends on DB plus pose JSONL, not photos. Current DB/pose alignment is provisional; fresh pull, capture binding and quiescence are the verdict gate.
- cap51's SQLite `-shm` wal-index is volatile and reconstructible; it is drift evidence, not persistent fixture identity. Only stable DB/WAL source bytes are preserved, and integrity work runs on a clone/backup so a normal WAL reader cannot mutate the scratch source's SHM.
- Historical pure-A is Mac-only and license-unknown pending removal of its LoFTR-derived statistics dependency and a clean rerun.
- LoFTR-indoor B/C and every merged output containing them are non-commercial research upper bounds.
- The preserved pure-A result uses effective `grid_m=0.01`; the script default `0.02` is not the run identity.
- Same-disk DVC reduces scratchpad-loss risk but is not disaster recovery.

## Scope boundary

This change performs preservation and verification only. It does not access the iPhone, rerun experiments, modify product or algorithm code, create a production claim, initialize a remote, or transfer asset bytes. Public package metadata may be fetched for the locked verifier environment. The next independent design is shutter-v2 durable capture plus thermal P0; cap51 A/B remains blocked until the morning device pull creates a new canonical DB/pose contract.
