# worktree_freeze_2026-07-17 — 重启后两棵共享 dirty worktree 的冻结快照

背景:2026-07-17 Mac 重启,/private/tmp 全部 pw_* 易失产物(交接文件 §12 所列 ~8GB)丢失。
本目录把两棵共享 dirty worktree 的未提交状态银行化,防止下一次事故造成不可恢复损失。
**本冻结是只读快照,不代表这些 WIP 已被整理/验收;原 worktree 仍是权威工作副本,禁止 reset/clean。**

## pocketworld_shutter_v2/
- 源:~/.config/superpowers/worktrees/pocketworld/shutter-v2-thermal-p0-20260714(branch codex/shutter-v2-thermal-p0-20260714)
- HEAD.txt / git_status.txt / tracked_modified.patch(含 E+B/C/D 产品接线全部 tracked 文本 diff)
- sha256_manifest.tsv:全部 76 个 modified+untracked 文件(排除 ios/build/)的 size+SHA256
- untracked_files/:全部 untracked 源码原样副本(bcd_*.dart、tests、tools 等)
- 注意:vendor/aether_ffi/libs/ios-arm64/sfm/libglomap_core.a 是二进制 modified,patch 不含内容,SHA 在 manifest 中

## aether_incremental_ba/
- 源:~/.config/superpowers/worktrees/Aether3D-cross/incremental-ba-ab-20260714(branch codex/incremental-ba-ab-20260714,frozen base 0a8b8428)
- HEAD.txt / git_status_summary.txt / git_status_bench_colmap.txt / tracked_modified.patch(vendored COLMAP + bench harness 全部 tracked diff)
- untracked_files/:bench/ 与 colmap-src 下 7 个 untracked 源文件
- bench_runs_evidence/:bench_runs 全部 344 个文本证据(verdict/run_config/log/SHA256SUMS/metrics JSON),含 A OFF/ON/ON-finalize5 铁案
- bench_runs_sha256_all.txt:bench_runs 全部 1216 个文件(含 ~2GB 大二进制 cloud.ply/metrics.npz 等)的 SHA256——大二进制本体未入库,可按此清单核验/再生
