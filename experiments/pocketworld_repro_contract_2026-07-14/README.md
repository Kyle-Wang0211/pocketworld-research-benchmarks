# PocketWorld reproducibility contract

This uv project builds and verifies deterministic manifests for local research
asset collections. It reads only the collection root named on the command line;
it does not contact devices, DVC, or research data services.

```text
uv run pocketworld-contract build ROOT --collection ID \
  --license-status LABEL \
  --platform-qualification LABEL \
  --evidence-role LABEL \
  [--lineage-contains-noncommercial] \
  --output FILE
uv run pocketworld-contract verify ROOT MANIFEST
uv run pocketworld-contract verify-contract CONTRACT
uv run pocketworld-contract gate-verdict CONTRACT
```

`FILE` must resolve outside `ROOT`; otherwise the generated manifest would
immediately become an unverified extra collection file.

Collection manifests use canonical UTF-8 JSON and list every regular file by
safe POSIX-relative path, byte count, SHA-256 digest, deterministic role, and
caller-supplied license status, platform qualification, evidence role, and
noncommercial-lineage flag. Symlinks are rejected.

## Versioned contracts

The schema is versioned at `schemas/contract-v1.schema.json` and is also shipped
as a package resource so installed verification never depends on a source-tree
relative lookup. Contract JSON is canonical UTF-8 (sorted, compact, one trailing
newline). Unknown truth is represented as `null` plus an exact JSON-pointer
deviation; placeholders such as `unknown` are rejected.

Contract commands reject duplicate JSON keys, `NaN`/infinities, noncanonical
whitespace, numeric overflow such as `1e9999`, and a missing final newline. A
`verdict_eligible` contract must use
`validation_scope=decision_contract` and close runnable code/config/command,
finite preregistered metrics, stopping rules, preserved `verdict_input` and
`verdict_output` evidence, and every referenced ID. Each threshold is bound to
an exact `(metric_id, artifact_id)` observation; all supported comparison
operators are evaluated and the stored pass/fail decision must match. A known
command must name every and only runnable code ID, its exact config ID, every
declared used model ID, and its dependency IDs.

Verification is not deferred for provisional contracts. It checks the declared
Git root, branch, commit ancestry, and tracked/staged dirty diff, then rehashes
every non-null repository-local code/config/lock claim, every preserved evidence
and DVC claim, and any materialized repository-local source-evidence claim.
Commercial dependency license evidence and model weight/license evidence are
also rehashed when present. Missing unpreserved external source evidence may
remain unavailable; preserved evidence is never skipped. Symlinks are rejected.

The three immutable skeleton identities are:

- `contracts/cap50-floor-plane-sweep-v1.json` — preservation-only evidence for
  the selected 115-frame closure within a 139-frame live feed; the exact 24
  missing names remain explicit.
- `contracts/cap51-capture-archive-provisional-v1.json` — the independent photo
  archive gap, currently 0/105 images; it does not decide replay eligibility.
- `contracts/cap51-incremental-ba-fixture-provisional-v1.json` — the current
  DB/pose evidence, blocked until a fresh capture-bound, quiescent pull creates
  a new immutable identity.

The replay fixture uses typed `replay_qualification` fields rather than truth
hidden in `details`. A future replay verdict requires a new non-provisional ID,
a fresh authorized device pull, proven source app/capture identity, quiescence
or a consistent backup, an atomic DB/WAL snapshot, integrity and DB/pose
alignment, and preserved DB/WAL/pose identities. Experiment A additionally
requires exact algorithm revision
`0a8b8428fba3fbf942af01ada6d1e1252a677c6a`, a default-disabled production
gate, `AETHER_INCREMENTAL_GLOBAL_BA=unset` versus `1`, and proof that this is the
only arm difference. SQLite SHM remains `excluded_volatile` and is never part of
replay identity.

The consumer target is COLMAP 4.1.0 plus a Ceres 2.2 source submodule. A target
version is never retroactively written into historical producer truth.

## Commercial boundary

None of these skeletons is product-qualified. The accepted points in the
historical `floor_planesweep.ply` are photometric, but its historical statistics
path read a LoFTR-indoor/ScanNet-derived rescue PLY. It therefore remains
Mac-only, license-unknown pending a standalone clean rerun, and excluded from
the commercial gate. LoFTR-derived rescue, B/C/D, matcher NPZ, and merged output
evidence is explicitly noncommercial research-upper-bound evidence. Metadata
records marked `not_applicable` do not replace the underlying private capture
license axes, which remain embedded in each referenced source manifest.

Code, model weights, training datasets, and tools are separate dependency
surfaces. Each records the exact audit verdict (`allow`, `conditional`,
`conflict`, `block`, or `insufficient-evidence`), intended use, obligations, and
immutable license evidence. Only `allow` dependencies with verified commercial
open-source status and clean lineage may enter a product candidate. Preserved
user-owned private inputs and derived outputs may support that gate only with an
explicit rights basis and rights-evidence hash. The cap50 LoFTR code remains
insufficiently evidenced, while LoFTR-indoor weights and ScanNet training lineage
are explicitly blocked; an Apache code license does not qualify either one.

A commercial candidate must explicitly declare a nonempty, complete execution
dependency closure. The declared set must exactly equal dependencies referenced
by runnable code, command, models, training datasets, and runtimes; empty
surfaces, unresolved references, and unreferenced padding fail. Dependency
license files and model weight/license files must be repository-relative and
hash-verified. This is a declared-closure check, not automatic discovery of
hidden dynamic or binary dependencies; independent evidence is still required
before asserting that the declaration covers the real execution surface.

## NPZ inspection and resource limits

`pocketworld_contract.npz.inspect_npz` is pinned to NumPy 2.4.2. It opens a
regular file with no symlink following, validates ZIP/NPY headers before loading,
rejects object dtype and pickle, applies per-member and total decoded-size
limits, loads one numeric member at a time with `allow_pickle=False`, and checks
source identity before and after inspection. Real NPZ evidence is not opened by
the unit suite; tests use tiny generated archives only.

All real preservation and inspection remains serial. Stop before the next file
when system-wide free memory is below 20%, and never trade host stability for a
claimed result.
