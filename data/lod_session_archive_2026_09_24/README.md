# LOD session archive, 2026-09-24

> **2026-09-24 redaction (force-pushed over b8f97ff).** This branch was pushed while the repository was public.
> Server address and SSH port, the phone's device identifiers and the owner's e-mail were replaced by
> placeholders (`<gpu-box-a>`, `<ssh-port>`, `<device-coredevice-id>`, `<device-udid>`, `<user-email>`) in the
> 11 files marked REDACTED in `MANIFEST.tsv`. Two items were withdrawn and are **not** in this branch any more:
> `mac_lod_bench/pw_splat_ab_bench.bundle` (its history carries a device id and e-mail; the full repo stays on
> the owner's machine) and `disk_cleanup_dedup_20260923/` (a listing of files on the owner's disk). Sections
> below that mention them describe what was withdrawn.


Self-authored code, results and reports of the point-cloud LOD work line (Potree-style octree
LOD: Mac bench, frozen viewer C ABI, iOS static-lib staging, arloopbench/production integration,
on-device octree build) from Claude session `cb65ad40` and its sub-agents. Snapshot taken
2026-09-24 18:08 CST. Nothing was re-run or edited: every file is a byte-identical copy of the
original (sha256 checked on both sides at copy time), except `mac_lod_bench/pw_splat_ab_bench.bundle`,
which is a `git bundle --all` made at archive time.

Sources:

| Prefix used below | Location |
|---|---|
| `<SP>` | `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/cb65ad40-6d75-486f-b32e-36830fe130aa/scratchpad/` (cleared on reboot) |
| `<LD>` | `~/Developer/pw_lod_data/` (kept locally; the engine and production agents still use it) |
| `<BENCH>` | `~/Developer/pw_splat_ab_bench/` (local git repo, no remote; kept locally) |

- **`MANIFEST.tsv`** has columns `archived_path, original_path, size_bytes, sha256, note`.
  Archived rows give the archived path. Rows with `archived_path = -` are files deliberately
  **not** archived: build products, third-party files, papers, symlinks and heavy data. Their `note`
  gives the reason and the upstream URL/revision or the rebuild route. For a directory,
  `sha256` is `tree:<sha256>`, computed over the LC_ALL=C-sorted lines `"<file sha256>  ./<relpath>"`,
  with symlinks written as `"link  ./<relpath> -> <target>"`.
- Heavy data kept outside git is listed in `artifacts/local_heavy_artifacts.md`, section
  "LOD session archive 2026-09-24".
- Live directories: `<SP>/lod171/`, `<LD>/artifact_stage/` and `<LD>/contract/` were still being written by other
  agents when this snapshot was taken. The archive holds their state as of the snapshot time.

## Code, branches and commits this archive refers to

| Repo | Branch | Head at archive time | What |
|---|---|---|---|
| Aether3D (public) | `feat/pointcloud-lod-core` | `d89b74f3` | PR #98, runtime LOD core (octree/select/stream) |
| Aether3D | `feat/pointcloud-lod-async` | `d2514519` | async node loader + Potree limits (vendored into the bench at `1af9a2c`) |
| Aether3D | `feat/pointcloud-lod-viewer` | remote `afb521e6`; **`ee942e08` is local-only** (receipt says `engine_branch_pushed: false`) | GPU viewer behind the frozen `pwlod_viewer.h` ABI; source of every `libpw_lod_*.a` below |
| Aether3D | `feat/pointcloud-lod-build` | `d87b5806` | on-device octree build (port of PotreeConverter 2.0), the A line |
| pocketworld (private) | `feat/lod-viewer` | `56f3bb94` | production LOD viewer integration |
| pocketworld | `feat/lod-on-dense-168` | `44bf12f6` | build 171 = 168 snapshot `86a45cf` + LOD in place of the dense viewer |

## Topics

### `mac_lod_bench/` (44 files, 10.9 MB)
- `pw_splat_ab_bench.bundle`: full history of `<BENCH>` (16 commits, `main` = HEAD =
  `b792d57447ba5058ab0935e781d399f7efa825c3`, clean tree). Restore it with
  `git clone pw_splat_ab_bench.bundle pw_splat_ab_bench`. It contains the Mac/iOS bench sources,
  the vendored `aether_pointcloud_lod` (with `PROVENANCE.txt` per-file sha256), the analyzers, the
  device plan and all result files, including the PNG contact sheets.
- `tracked/`: plain copies of the tracked reports, plans and result text, so they can be read without
  unbundling: `REPORT_20260923.md`, `LOD_DEVICE_PLAN_20260923.md` (plan r3),
  `results_mac_20260923/` and `results_mac_20260924_async_adaptive/` (JSON/TXT/JSON.GZ only; PNGs
  are in the bundle), `run*.json`, `points_run*.json` and `cloud_run*.json`.
- `<BENCH>/build/` and `<BENCH>/build_lod/` are Xcode/CMake derived data and are not archived.
  `build/mac_deps` (the Dawn snapshot) is in the heavy list.

### `plans_and_contract/` (17 files)
- `LOD_ARLOOPBENCH_PLAN_20260924.md`: plan for integrating LOD into arloopbench and production.
- `contract/`: the frozen engine/shell C ABI header, with each version's sha file:
  `pwlod_viewer.v1.h` (a1e1bcff…), `pwlod_viewer.v2.h` (4b047f1f…), and `pwlod_viewer.h`, which at the
  snapshot is **v3** (4e867aa3…). Each `.sha256` file names its header `pwlod_viewer.h`.
- 36M/216M octree transfer records: `fetch.sh` (resumable rsync), `fetch_chunked.sh`
  (256 MiB chunks, sha256 checked on both ends), `rsync_oct_prod.log`, `fetch_216M.log`,
  `oct_prod.local.sha256`, `oct_remote.sha256`, `oct_216M.local.sha256`, and `oct_216M.REMOVED.txt`
  (the local 216M copy was deleted with the user's consent on 2026-09-24).
- `oct_prod_meta/`: `metadata.json` and `log.txt` of the 36M octree `<LD>/oct_prod/`. The `.bin`
  files are in the heavy list.

### `bench_app_backups/` (20 files)
- `bench_backup_20260924_113445/`: pre-change backup of the arloopbench files touched by the LOD
  integration. `~/Developer/arloopbench` is not a git repo, so this is the only copy of the old
  state. It includes the hidden `.sync_from_integration.sh`. `SHA256SUMS.original` covers the backup;
  `SHA256SUMS.after` covers the same paths after the change.
- `bench_install_20260924_1149/`: `devicectl` listings of the bench container `Documents`/`Library`
  before and after the install, plus `installed_runner.sha256`.

### `artifact_stage/` (36 files, 5.6 MB)
Snapshot of `<LD>/artifact_stage/vendor/aether_lod/`, the iOS arm64 drop of the LOD viewer that the
coordinator copies into product `vendor/aether_lod/`. Every `.a` (about 1 MB) is kept together
with its receipt (engine revision, sources, flags, reproducibility), `nm` symbol list, the
`build_ios_lod.sh` that built it, and the headers. All come from Aether3D `feat/pointcloud-lod-viewer`:

| Library | Engine commit | ABI | Location |
|---|---|---|---|
| `libpw_lod_ee942e08.a` | `ee942e08f52b9f198dcd3012519ae515669e94fd` | 3 | `libs/ios-arm64/` (current) |
| `libpw_lod_afb521e6.a` | `afb521e6730e8f3539235fb9c4ba215b685c5623` | 2 | `superseded/afb521e6/` (the one in `<LD>/bench_pkg_lod_afb521e6_20260924`) |
| `libpw_lod_740c1ddd.a` | `740c1dddf3a0399bf154a2aa66b36b0d175a727d` | 2 | `superseded/740c1ddd/` |
| `libpw_lod_9496aa39.a` | `9496aa391f326f699206c69fdecdbbc67c8895e3` | 1 | `superseded/9496aa39/` |

`include/dawn/webgpu.h` and `include/dawn/LICENSE` are Dawn's (BSD-3-Clause, submodule `12ee391c`). They are
kept only because the stage is the exact integration drop.

### `mac_correctness_runs/` (65 files, 50 MB)
Mac correctness renders of `<BENCH>` for 36M and 216M. The arms are `ref`, `ctrl` and `px150`, and the
views are overview, orbit_mid, pan_mid, leaf, leaf_only and leaf_no_origin. Each run has its `lod_mac*.json`: v1 is `mac_correct_*` and v2 is
`mac_correct2_*`. The contact sheets derived from these runs are in `results_mac_20260923/` in the bundle.

### `agent_evidence/` (209 files, 25 MB)
- `lodint/`: integration agent. A/B builds with and without LOD (`build*_sha.txt`,
  `build*_strings.txt`, logs), `strings` dumps of the two app binaries, Dawn `wgpu*` definition lists,
  undefined-symbol list, `preinstall_checks.sh`. The copied app binary `buildA_copy/App_A2` is excluded.
- `lodshell/`: Flutter shell agent. Commit-message drafts `msg*.txt`, `.bak` copies of the
  Dart sources before editing, `final/` Dart sources and tests, iOS link smoke sources
  (`smoke/`, including negative controls `neg_v1`, `neg_n2` and `neg_n3` with mutated headers), and the host test
  `hostrun/`. `.o` files, executables and upstream files are excluded (see MANIFEST).
- `bline/`: B line, async loading and adaptive point size. Mac smoke, I/O A/B and correctness v5 JSON,
  point-size contact sheets, `io_split.py`, `sum3.py`, preflight/submodule/configure logs,
  `pr100/` (compare JSON and a source snapshot of `pointcloud_lod_build` for Aether3D d89b74f3…d87b5806),
  and `ffi_forensics/` (symbol forensics of the product ffi archive against Dawn; see `NOTES.txt`).
  The build trees `build-gcc/`, `build-clang/`, the binary `t` and the upstream Potree copy `raw/` are excluded.
- `aline/`: A line, on-device octree build. `run/` (timing, peak RSS, preflight, profiling,
  thread/chunk grid, t12-vs-t1 equivalence), `tools/` (server/Mac drivers, lossless and colour
  verifiers, octree comparator), `src.tgz`/`src_full.tgz` (the exact source snapshots that were built;
  force-added despite the repo `.gitignore` on `*.tgz`), `cmk.cfg.log`. Excluded: `bq/` (object files
  and the `pwlod_build_cli` executable) and the fixture octree `run/fx_vlas/*.bin`.
- `lod171/`: production build 171 packaging evidence. Control/verify build logs,
  `cmp_168_vs_control3.txt`, per-file lists `files168.txt`/`filesctl.txt`, disassembly/strings/size
  comparisons in `cmp/`, `control_build_side_effects/tracked.patch`, the SwiftPM side-effect record, the
  stale SwiftPM state before cleanup (plugin list and generated `Package.swift`), the XDG settings used by
  the release gate (negative and positive), the ledger README before the fix, `tools/cmp_bundles.sh`, and
  commit-message drafts. Excluded: `control3/` (the 180 MB binary package), `cmp/Runner168` and `cmp/RunnerVerify`
  (82 MB Mach-O each), `cmp/n168.txt`/`nctl.txt` (34.7 MB identical `nm` dumps),
  `stale_spm_state/product_bundles/` and the symlinks into the pub cache or `~/Library`.
- `b_async_wip_20260923_2340/`: the B line's work-in-progress async loader patch (`tracked.patch`)
  and `test_async.cpp`, taken from `<LD>` before it was committed to `feat/pointcloud-lod-async`.

### `disk_cleanup_dedup_20260923/` (8 files, 24 MB): not LOD
These are records of the 2026-09-23 APFS-clone dedup of three device-backup roots
(`~/Documents/progecttwo/.device_backups.nosync`, `~/pw_device_backups`, `~/Developer/device-backups`),
run by a disk-cleanup sub-agent of the same session:
- `roots_hashes.raw` and `roots_hashes_after.raw`: every file's sha256 before and after the dedup (sorted, they are identical).
- `roots_stat.tsv`: inode, link count, size and path.
- `rootsB_plan.tsv`: the plan, with columns canonical, duplicate, size and sha256. `rootsB_pilot.tsv` holds its first 200 rows and `rootsB_rest.tsv` holds the rest.
- `rootsB_ready`: the marker file. It holds the plan's total bytes (21,754,674,365) and row count (12,556).

They record which backup files are now clones of one another.

## What was deliberately NOT archived
- **Third-party material.** These are recorded in MANIFEST with URL and revision.
  - Papers: `lean3d.pdf` (arXiv 2604.04737) and `pc/schuetz2020.pdf`/`.txt` (Schütz et al., PG 2020).
  - Upstream code and docs: `<SP>/ptcloud/*`. Note that `sel.md` is cesium-native's own `selection-algorithm-details.md`, not a note of ours.
  - `src/` (wgpu 30.0.0), `entwine/` (@e43b3dfa), `pc.tar.gz` (potree-core master, truncated), `bline/raw/` (Potree @5636cd47), and the flutter/packages and three.js files in `lodshell/`.
- **Build products and binaries.** These are listed in MANIFEST with sha256.
- **Heavy data**, listed in `artifacts/local_heavy_artifacts.md`:
  - the 36M octree and source PLY;
  - the 216M octree, which is on the server only;
  - the bench Runner.app package;
  - the Dawn snapshot.
- Legal/patent material: none was found in scope. A grep for 专利/patent/法律/legal matched only
  `illegal ...` strings, Dawn symbol names and the Apache-2.0 license text inside `src_full.tgz`.
  Secrets: a scan for `ghp_`, `github_pat_`, `sk-`, `AKIA`, `PRIVATE KEY`, JWT and Google/Slack key
  shapes found none. The only `password` hits are identifiers in `strings` dumps of app binaries.
