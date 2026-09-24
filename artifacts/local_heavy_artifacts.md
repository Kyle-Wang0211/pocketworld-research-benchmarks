# Local Heavy Artifacts

These files are intentionally kept out of git. They are reproducibility inputs or large intermediate tensors for the reports archived in this repo.

## Latest 414-Frame Capture

- Capture bundle: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/app_documents_latest/cap_1779949415373229`
- Baseline DA3 tensor export: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_cpu_probe`
- DA3-only vs DA3+MoGe benchmark output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229`
- MoGe auxiliary tensors: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229/moge_aux`
- Patch features CSV: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/pre_sap_uncertainty_cap_1779949415373229/patch_features.csv`

## Current Overlap Sweep

- Overlap-12 capture variant: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/overlap_sweep/cap_1779949415373229_overlap12`
- Overlap-9 capture variant: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/overlap_sweep/cap_1779949415373229_overlap09`
- Overlap-12 DA3 output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_overlap12_cpu`
- Overlap-9 DA3 output: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/mac_da3_cap_1779949415373229_overlap09_cpu`

## Official-Style DA3-BASE K35 Streaming

- Lightweight archived reports: `data/official_da3_base_k35_streaming_2026_05_30/reports/`
- Local full run directory with DA3 tensors: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_streaming_2026_05_30`
- Local vendored SelaVPR++ checkout: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/SelaVPRplusplus`
- Local vendored BoQ checkout: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/Bag-of-Queries`
- Local official DA3 streaming reference copy: `/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/vendor/official_da3_streaming`

Only manifests, summaries, reports, and scripts are committed. Large depth/confidence tensors, descriptor arrays, copied photos, local databases, and vendor checkouts are intentionally excluded.

## LOD session archive 2026-09-24

Heavy or regenerable parts of the point-cloud LOD work line. The lightweight outputs are archived in `data/lod_session_archive_2026_09_24/`; see its `README.md` and `MANIFEST.tsv`, where every item below also appears as a row with `archived_path = -`. `tree:<sha256>` is the directory hash that the README defines. `SP` = `/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/cb65ad40-6d75-486f-b32e-36830fe130aa/scratchpad` (cleared on reboot).

Kept locally, persistent:
- `~/Developer/pw_lod_data/oct_prod/`: the 36M Potree 2.0 octree (36,232,793 points). `octree.bin` is 652,190,274 B, sha256 `d12f7eb33f777797d0a63496286e4327cdaf3be095ebc79868e208dc5c3f9cb6`. `hierarchy.bin` is 543,466 B, sha256 `3a38de58956a4a0a8afd1301aa6e9fff5cc0093f364818e8d12d5151bd88062d`. `metadata.json` and `log.txt` are archived under `plans_and_contract/oct_prod_meta/`. The server copy `root@<gpu-box-a>:/root/oct_prod/` has the same hashes (`plans_and_contract/oct_remote.sha256`). To retrieve it, run `plans_and_contract/fetch.sh oct_prod`, then check it with `oct_prod.local.sha256`. To rebuild it, run PotreeConverter 2.0 (or the on-device port on Aether3D `feat/pointcloud-lod-build`) on the PLY below.
- `~/Developer/pw_clouds_20260923/pc_t3_ep0_36M.ply`: 543,492,077 B, sha256 `ff512c502f7647baf7ede5f5631cf688b536115e212d1bf6dfa57fc0e154a196`. It is binary little-endian, with float32 xyz and uchar rgb. It was pulled on 2026-09-23 from `root@<gpu-box-a>:<ssh-port>:/root/arm_full_ep0/pc_t3.ply` (see `SOURCE.txt` next to it).
- `~/Developer/pw_lod_data/bench_pkg_lod_afb521e6_20260924/`: the signed arloopbench `Runner.app` with `libpw_lod_afb521e6.a`. It has 67 files, 45,942,008 B, `tree:0cf1fdfd1cabb32f7127d07074a728ed482ff27a5357ef92e6001266ec893ae4`. `Runner` has sha256 `2729e00aa6f34d132167528a04227e5b8b45c45a049e42b5942d3f4f8373e256`, which equals the installed binary (`bench_app_backups/bench_install_20260924_1149/installed_runner.sha256`). It can be rebuilt from arloopbench plus `artifact_stage/superseded/afb521e6/`.
- `~/Developer/pw_splat_ab_bench/build/mac_deps/`: Dawn macOS snapshot used by `mac/build_mac.sh`. It has 37 files, 21,764,998 B, `tree:f762834f86fa693d5d3bf5521f8f5a6f87c38600481a60ba5d2fe08f5291e6f7`. `libwebgpu_dawn.a` has sha256 `9611ccea231df5542513d64d1fc3fd8f5d0200937b96b9464cc9bd527d65c4bd`. It was copied from `Aether3D-cross/aether_cpp/build-macos-dawn` (Dawn submodule `12ee391c`). `build_mac.sh` repeats the copy when the directory is missing. The rest of `build/` and `build_lod/` is Xcode derived data.

Server only (vast box `<gpu-box-a>:<ssh-port>`; it went offline 2026-09-24 and the instance is kept, not destroyed):
- `/root/oct_216M/` holds the 216M octree (216,655,968 points). `octree.bin` is 3,899,807,424 B, sha256 `3b8c87ec62723894d3f9e83fcd00fbc0fb553d7110fb3ea0e9b7506200cf53dd`. `hierarchy.bin` is 2,662,154 B, sha256 `037a9045e36821cc573762fb86f010c60fb3b8f5e46dec9ae3b88041dd36e59b`. `metadata.json` has sha256 `b2fc91cb20fe2c2606bb719cc9064787d95b26f82f4c295459ec1ebd8f790e4a`, and `log.txt` has sha256 `912f93766a7c4eeece969e0ffd20589413e1f9a755d049d2e64787a8dd76587d`. The local copy was deleted with the user's consent on 2026-09-24 (`plans_and_contract/oct_216M.REMOVED.txt`). To retrieve it, run `plans_and_contract/fetch_chunked.sh`, then check it against `oct_216M.local.sha256`.

Scratch items that are still local while their owners use them (`SP/lod171/`, production 171 work):
- `SP/lod171/control3/`: the control build's Runner and App.framework. It is 184,246,080 B, `tree:67d45254d553e9143e4b71a92c8698b9ceb0f199388eff9d7be97d347676e400`, and has an internal `files.sha256`.
- `SP/lod171/cmp/Runner168` (82,884,224 B, sha256 `4e5c135c0971f17ae1ffa621adf9e6b938cbff1e2b8b5621e6c6854fd559661f`) and `SP/lod171/cmp/RunnerVerify` (82,891,760 B, sha256 `94d4644a9144371c83e27976bb9dbf7eae8093525da8c3a8ebdb56e82498ee25`) are Mach-O copies used for comparison.
- `SP/lod171/cmp/n168.txt` and `nctl.txt` are 34,702,124 B each and identical (sha256 `b8c95576d25f1b1a7c49ac9079e43af7bb3f8d175e993a92bd44a1f34888f314`). They are `nm` dumps of the two Runners. To regenerate them, run `nm` on the binaries above.

Scratch build products deleted after archiving (all rebuildable):
- `SP/bline/build-clang/` (16,705,526 B, AppleClang) and `build-gcc/` (2,825,439 B, g++-16): Release CMake/Ninja builds of `~/Developer/Aether3D-lodasync/aether_cpp`, the worktree of Aether3D `feat/pointcloud-lod-async`, covering `aether_pointcloud_lod` and its tests. The configure and build output is archived as `agent_evidence/bline/build-*.log`. To rebuild, run `cmake -G Ninja -DCMAKE_BUILD_TYPE=Release` on that branch.
- `SP/aline/bq/` (763,328 B): `.o` files and `pwlod_build_cli` built from `agent_evidence/aline/src_full.tgz`. The build commands are in `agent_evidence/aline/tools/qbuild.sh` and `srv_build.sh`.
- `SP/aline/run/fx_vlas/{octree,hierarchy}.bin` (450,000 B and 1,980 B): converter output on the fixture.
- `SP/lodint/buildA_copy/App_A2` (8,456,368 B, sha256 `02a6de166b68fe161396b35d7d7f30ebd008478a4a5e83c4d8316bd2d0054a4a`): a copied app binary.
- `SP/lodshell/smoke/smoke_ios_arm64` (10,049,560 B), `SP/lodshell/hostrun/host_test` (9,899,560 B) and `smoke/*.o`: link-smoke binaries. Rebuild them with `agent_evidence/lodshell/smoke/build.sh`.

Third-party inputs are also deleted from scratch; MANIFEST records each one's URL and revision. They are: the papers (arXiv 2604.04737; Schütz et al. PG 2020), cesium/cesium-native/android games-samples files, wgpu 30.0.0 source, entwine @e43b3dfa, the potree-core master tarball, Potree @5636cd47 and flutter/packages @fbc80a62002.
