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

The three immutable skeleton identities are:

- `contracts/cap50-floor-plane-sweep-v1.json` — preservation-only evidence for
  the selected 115-frame closure within a 139-frame live feed; the exact 24
  missing names remain explicit.
- `contracts/cap51-capture-archive-provisional-v1.json` — the independent photo
  archive gap, currently 0/105 images; it does not decide replay eligibility.
- `contracts/cap51-incremental-ba-fixture-provisional-v1.json` — the current
  DB/pose evidence, blocked until a fresh capture-bound, quiescent pull creates
  a new immutable identity.

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

Only dependencies with immutable license evidence, commercially permissive
status, and clean noncommercial lineage may enter a future product gate.

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
