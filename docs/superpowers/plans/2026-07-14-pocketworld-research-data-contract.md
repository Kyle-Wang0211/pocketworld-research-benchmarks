# PocketWorld Research Data Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve available cap50/cap51 and plane-sweep evidence as local-only, content-addressed, fail-closed research contracts without exhausting the Mac or overstating incomplete/non-commercial evidence.

**Architecture:** A sparse isolated worktree holds OpenSpec, deterministic Python tooling, manifests, and DVC pointers. Selected bytes are APFS-cloned into bounded collections and content-addressed by a user-local DVC cache with no remote; SHA-256 contract verification remains independent of DVC. Cap50 and cap51 use separate typed contracts so provisional cap51 can never unlock experiment A.

**Tech Stack:** Git worktree, OpenSpec 1.6.0, DVC 3.67.1, uv 0.11.14, Python 3.11, pytest, Ruff, encrypted APFS, SHA-256.

---

## Fixed context and gates

- Worktree: `/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714`
- Baseline: `0a1931658ffff4d2e606b87b197656fe8a14025d`
- Scratch source: `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/b3b899a4-8125-4eb7-a21a-eb3d48c3d2a8/scratchpad`
- Original research checkout is a read-only source for four ignored PLY files.
- Python: `/opt/homebrew/bin/python3.11`.
- Hard stop: less than 15 GiB free disk or less than 20% system-wide free memory.
- Prohibited: device access, DVC remote, upload, `git add -A`, whole-tree DVC add, experiment execution, model download, and edits to the original checkout.

### Task 1: Contract verifier via TDD

**Files:**

- Create: `experiments/pocketworld_repro_contract_2026-07-14/pyproject.toml`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/uv.lock`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/src/pocketworld_contract/manifest.py`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/src/pocketworld_contract/cli.py`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/tests/test_manifest.py`

- [ ] **Step 1: Initialize a Python 3.11 package and locked dev tools**

Run `uv init --package --python /opt/homebrew/bin/python3.11 experiments/pocketworld_repro_contract_2026-07-14`, then `uv add --group dev pytest ruff`. Restrict `requires-python` to `>=3.11,<3.12` and add no runtime dependency.

- [ ] **Step 2: Write the first failing tests**

```python
def test_build_collection_orders_paths(tmp_path: Path) -> None:
    (tmp_path / "b.bin").write_bytes(b"b")
    (tmp_path / "a.bin").write_bytes(b"a")
    manifest = build_collection(tmp_path, "fixture", "input_only")
    assert [item["path"] for item in manifest["assets"]] == ["a.bin", "b.bin"]


@pytest.mark.parametrize("unsafe", ["/absolute.bin", "../escape.bin", "a/../../x"])
def test_verify_rejects_unsafe_paths(tmp_path: Path, unsafe: str) -> None:
    manifest = {"schema_version": 1, "collection_id": "fixture", "assets": [{
        "path": unsafe, "role": "input_only", "bytes": 0,
        "sha256": "0" * 64, "commercial_eligibility": "input_only",
    }]}
    with pytest.raises(ContractError, match="unsafe relative path"):
        verify_collection(tmp_path, manifest)


def test_provisional_contract_cannot_unlock_verdict() -> None:
    with pytest.raises(ContractError, match="not verdict eligible"):
        require_verdict_eligible({"status": "provisional_not_verdict_eligible"})
```

- [ ] **Step 3: Run RED**

Run `uv run pytest tests/test_manifest.py -q`. Expected: import/function failure because implementation does not exist; a passing test is invalid.

- [ ] **Step 4: Implement the minimal streaming primitives**

```python
CHUNK_BYTES = 4 * 1024 * 1024


class ContractError(ValueError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise ContractError(f"unsafe relative path: {value}")
    return path
```

`build_collection` SHALL sort regular files, reject symlinks, and stream one file at a time. `verify_collection` SHALL reject duplicate/extra/missing paths and compare bytes and SHA-256. `require_verdict_eligible` SHALL accept only exact status `verdict_eligible`.

- [ ] **Step 5: Add one failing test at a time for mutation, missing/extra file, duplicate path, and symlink; make each GREEN**

Run `uv run pytest tests/test_manifest.py -q` after every red/green pair.

- [ ] **Step 6: Add CLI commands and verify tooling**

Expose `build ROOT --collection ID --eligibility LABEL --output FILE`, `verify ROOT MANIFEST`, `verify-contract CONTRACT`, and `gate-verdict CONTRACT`. Run `uv run ruff format --check src tests`, `uv run ruff check src tests`, `uv run pytest -q`, and `uv lock --check --offline`.

- [ ] **Step 7: Commit exact tool paths**

Commit as `test(research): add deterministic asset contract verifier`.

### Task 2: Schema and truthful contract skeletons

**Files:**

- Create: `experiments/pocketworld_repro_contract_2026-07-14/schemas/contract-v1.schema.json`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/tests/test_contract_schema.py`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/contracts/cap50-floor-plane-sweep-v1.json`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/contracts/cap51-incremental-ba-provisional-v1.json`

- [ ] **Step 1: Write failing tests for the required truth surface**

Require `schema_version`, `contract_id`, `status`, `git`, `upstream`, `collections`, `code`, `environment`, `models`, `effective_config`, `seeds`, `command`, `metrics`, `exclusions`, `stopping_rules`, `artifacts`, `deviations`, `privacy`, `product_qualification`, and `verdict`. Reject runnable config containing `/private/tmp` or `/var/mobile/Containers`.

- [ ] **Step 2: Run RED, then implement explicit structural and enum validation**

Allowed status values are `preserved_incomplete_feed`, `provisional_not_verdict_eligible`, `verdict_eligible`, and `invalid`. Allowed eligibility values are `input_only`, `candidate_unproven_cross_platform`, `commercially_eligible`, and `noncommercial_research_upper_bound`.

- [ ] **Step 3: Add skeletons without fabricating missing facts**

Cap50 records `selected=115`, `live_fed=139`, `missing=24`, `grid_m=0.01`, and `preserved_incomplete_feed`. Cap51 records `live_fed=105`, `selected=81`, `available_images=0`, `provisional_not_verdict_eligible`, and `fresh_device_pull_required`. Unknown command/seed/model/DVC values remain `null` with explicit deviations.

- [ ] **Step 4: Run GREEN and commit**

Run all tests/lint/lock checks and commit as `spec(research): define typed PocketWorld experiment contracts`.

### Task 3: Local DVC safety probe

**Files:**

- Create: `.dvc/config`
- Create: `.dvc/.gitignore`
- Local only: `.dvc/config.local`

- [ ] **Step 1: Record `df -h .`, `memory_pressure -Q`, and `du -sh .`; stop outside gates**

- [ ] **Step 2: Initialize only the isolated research root**

```bash
DVC_NO_ANALYTICS=true dvc init
DVC_NO_ANALYTICS=true dvc config cache.type reflink,hardlink,copy
DVC_NO_ANALYTICS=true dvc config --local cache.dir \
  /Users/kaidongwang/.cache/dvc/pocketworld_research_benchmarks
test -z "$(DVC_NO_ANALYTICS=true dvc remote list)"
```

- [ ] **Step 3: DVC-add a 4 KiB deterministic probe created through `apply_patch`**

Inspect `dvc doctor`, `dvc status --json`, free-disk delta, and configured cache types. Remove only the probe and pointer after the test; keep DVC config.

- [ ] **Step 4: Commit DVC metadata only**

Commit `.dvc/.gitignore`, `.dvc/config`, and the exact root ignore change as `chore(research): configure local-only DVC ownership`.

### Task 4: Preserve cap50 in four bounded collections

**Files:**

- Create/DVC: `data/pocketworld_captures/cap50/raw/photos_highres/`
- Create/DVC: `data/pocketworld_captures/cap50/derived/work_1024x576/`
- Create/DVC: `data/pocketworld_captures/cap50/private_manifests/`
- Create/DVC: `data/pocketworld_captures/cap50/sfm/`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/manifests/cap50-*.json`

- [ ] **Step 1: Build source manifests before copying**

Assert raw `230 files / 205162291 bytes`, work PNG `115 files / 96336651 bytes`, sparse PLY SHA `a41bd10f...f36df`, feed ledger SHA `d3970be1...1603b`, and subset SHA `bd082ce5...c324`.

- [ ] **Step 2: Re-check gates, APFS-clone only the 115 JPEG/JSON pairs, and immediately re-check disk**

Use `/bin/cp -cR` with no concurrent collection operation.

- [ ] **Step 3: Verify the destination against its source manifest before `dvc add`**

No content file may appear in `git status`; only the pointer/ignore metadata may appear.

- [ ] **Step 4: Repeat for 115 exact PNG inputs**

Exclude `images_full.tar.gz` and AppleDouble files. Assert the normalized PNG tree digest `4cb23e0152ef593a0235727d7c1a6254d2ae8c15582777fda500fd8a5ceac2d0`.

- [ ] **Step 5: Preserve feed/subset/ghost metadata and sparse PLY as separate DVC units**

Reference the already tracked `poses.json` and `floor_frame_ids.json` by Git-relative path/SHA instead of duplicating their bytes.

- [ ] **Step 6: Generate and test the exact 139/115/24 set relation**

Write a deterministic missing-frame list. Do not shrink the live denominator.

- [ ] **Step 7: Update DVC OIDs and verify cap50 remains `preserved_incomplete_feed`**

### Task 5: Preserve cap51 as provisional evidence

**Files:**

- Create/DVC: `data/pocketworld_captures/cap51/private_manifests/`
- Create/DVC: `data/pocketworld_captures/cap51/sfm/live_snapshot_provisional/`
- Create/DVC: `data/pocketworld_captures/cap51/sfm/sfm_sparse.ply`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/manifests/cap51-provisional.json`

- [ ] **Step 1: Assert pre-copy hashes for DB/WAL/SHM, feed ledger, bundle, and sparse PLY**

Use the six hashes in the OpenSpec evidence; fail before copying on any mismatch.

- [ ] **Step 2: Clone DB/WAL/SHM as one batch and hash sources again**

If any source changes between checks, delete only the new destination and stop. Never call it a consistent snapshot.

- [ ] **Step 3: Preserve metadata and sparse PLY; generate exactly 105 unavailable image basenames**

Do not fabricate `raw/photos_highres`.

- [ ] **Step 4: DVC-add and prove the verdict gate is closed**

Structural verification must pass, while `gate-verdict` exits non-zero with `fresh_device_pull_required`.

### Task 6: Preserve plane-sweep PLY/NPZ evidence

**Files:**

- Create/DVC: `experiments/floor_plane_sweep_densifier_2026-07-13/outputs/`
- Create/DVC: `experiments/floor_plane_sweep_densifier_2026-07-13/intermediates/merge_inputs/`
- Create/DVC: `experiments/floor_plane_sweep_densifier_2026-07-13/intermediates/matches/`
- Create: `experiments/floor_plane_sweep_densifier_2026-07-13/contract/assets.sha256`
- Create: `experiments/floor_plane_sweep_densifier_2026-07-13/contract/effective-config.json`
- Create: `experiments/floor_plane_sweep_densifier_2026-07-13/contract/eligibility.json`

- [ ] **Step 1: Clone four requested PLY files from the original checkout and assert hashes/vertex counts**

Expected hashes begin `3eaabe2b`, `043536cc`, `1113af4a`, `81dc1bc4`; expected vertices are `5845`, `1435`, `12672`, `18222`.

- [ ] **Step 2: Preserve merge inputs with hashes `3569d382...22ee` and `74d3a669...717d`**

- [ ] **Step 3: Preserve five match NPZ files plus `xsec_data.npz` serially**

Verify each with `numpy.load(path, allow_pickle=False)` and reject object dtype. Exclude `_shell_cache.npz`.

- [ ] **Step 4: Write eligibility/effective config before DVC add**

Record `grid_m=0.01`. Pure-A is `candidate_unproven_cross_platform`; B/C and merged evidence are `noncommercial_research_upper_bound` because they contain LoFTR-indoor/ScanNet evidence.

- [ ] **Step 5: DVC-add outputs, merge inputs, and matches separately, checking free disk after each**

### Task 7: Full deterministic verification

**Files:**

- Modify: `experiments/pocketworld_repro_contract_2026-07-14/contracts/*.json`
- Create: `experiments/pocketworld_repro_contract_2026-07-14/reports/preservation-verification.json`

- [ ] **Step 1: Run pytest, Ruff, and `uv lock --check --offline`**

- [ ] **Step 2: Run `dvc status --json`, granular `dvc data status`, `dvc repro --dry`, and assert empty remote list**

Do not call nonexistent `dvc cache verify` in DVC 3.67.1.

- [ ] **Step 3: Strictly validate OpenSpec and confirm Git tracks no JPEG, DB, PLY, or NPZ payload**

- [ ] **Step 4: Scan only runnable metadata, not immutable DVC sidecars, for transient absolute paths and credentials**

- [ ] **Step 5: Record final disk/memory state, cache path, versions, contract hashes, DVC OIDs, and same-disk limitation**

### Task 8: Independent review and exact-path commit

- [ ] **Step 1: Give a fresh-context read-only reviewer the spec, diff, test logs, DVC status, inventory, disk delta, and verification report**

- [ ] **Step 2: Resolve every material finding and rerun Task 7**

- [ ] **Step 3: Stage exact paths only; never use `git add -A`**

- [ ] **Step 4: Commit as `research(data): freeze PocketWorld cap50 and provisional cap51 evidence`**

- [ ] **Step 5: Leave experiment A blocked for the morning fresh device pull**

The handoff names iPhone `1B290474-D354-5B4C-AAB0-0805AC5DC832`, app `com.kyle.PocketWorld`, the expected 105-frame set, and the rule that the fresh fixture gets a new contract ID and new hashes. It SHALL NOT invoke `devicectl` tonight.
