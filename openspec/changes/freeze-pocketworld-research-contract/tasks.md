## 1. Contract Tooling and Schema

- [ ] 1.1 TDD a Python 3.11 streaming verifier for canonical ordering, exact file sets, path/symlink safety, mutation, and provisional verdict gates.
- [ ] 1.2 Add locked NumPy 2.4.2 NPZ inspection and reject pickle/object dtype with failing-first tests.
- [ ] 1.3 Add schema/tests for full reproducibility truth and separate license/platform/role/lineage axes.
- [ ] 1.4 Create normalized cap50, cap51 archive, and cap51 replay-fixture skeletons with null+deviation for missing evidence.

## 2. Sparse and DVC Safety Setup

- [ ] 2.1 Expand sparse checkout only to `data/pocketworld_captures` and record baseline disk/memory.
- [ ] 2.2 Initialize DVC at the isolated research root, use dedicated local cache, tracked `reflink,hardlink,copy`, analytics disabled, and no remote.
- [ ] 2.3 Probe ignored photos/DB/PLY/NPZ plus reflink behavior on tiny fixtures; prove no binary force-add is needed.
- [ ] 2.4 Compute each real batch byte count and enforce `15 GiB + 2×batch + 256 MiB` and 20% memory gates.

## 3. Cap50 Preservation

- [ ] 3.1 Clone/hash 115 JPEG/sidecar pairs and 115 exact PNG inputs in separate serial DVC units.
- [ ] 3.2 Preserve private feed/subset/ghost metadata and sparse PLY; reference tracked poses/floor IDs by Git SHA.
- [ ] 3.3 Generate and test the exact 139/115/24 relation and normalized effective config.
- [ ] 3.4 Record DVC OIDs and verify `preserved_incomplete_feed` without upgrading historical claims.

## 4. Cap51 Archive and Replay Fixture

- [ ] 4.1 Preserve the photo archive gap, bundle, feed ledger, and sparse PLY as capture-archive evidence.
- [ ] 4.2 Preserve persistent DB/WAL bytes and the feed ledger as pose JSONL with pre/post source stability checks; record SHM drift but exclude SHM from fixture identity.
- [ ] 4.3 Record SQLite integrity, 105 DB image/keypoint/descriptor rows, image IDs 1–105, pose IDs 0–104, and capture binding.
- [ ] 4.4 Prove replay remains `provisional_not_verdict_eligible` only because fresh pull/quiescence identity is missing.

## 5. Plane-Sweep PLY and NPZ Evidence

- [ ] 5.1 Preserve/verify four outputs and two merge inputs with names, hashes, formats, and vertices.
- [ ] 5.2 Inventory and preserve all seven NPZ files with producer/consumer/role/inclusion evidence and locked safe-load checks.
- [ ] 5.3 Record effective `grid_m=0.01`, historical producer versus COLMAP 4.1.0 target, and hard-coded scripts as non-runnable evidence sources.
- [ ] 5.4 Record historical pure-A as license unknown pending audit and B/C/merged evidence as non-commercial upper bounds.
- [ ] 5.5 Add a prominent README boundary separating pure-A and merged metrics before product use.

## 6. Final Verification and Review

- [ ] 6.1 Verify three contracts, tests/lint/offline lock, DVC status/no remote, OpenSpec, Git payload, normalized paths, and resource/network logs.
- [ ] 6.2 Record cache path, DVC OIDs, hashes, deviations, same-disk risk, and non-destructive cleanup/recovery commands.
- [ ] 6.3 Complete independent spec review followed by code-quality review and resolve all findings.
- [ ] 6.4 Commit exact metadata/pointer paths only; leave fresh cap51 pull and experiment A blocked for morning device authorization.
