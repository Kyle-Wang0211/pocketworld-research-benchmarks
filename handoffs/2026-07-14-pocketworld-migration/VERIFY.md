# 交接核验：A 被动只读 + B 可控测试

以下命令均不得 fetch、pull、checkout、reset、clean、安装或修改设备。A 阶段不应写工作树；B 阶段的 pytest/Flutter 工具可能更新 ignored `.pytest_cache`、`.dart_tool`、build 或 SDK cache，只能在 A 通过后运行，并必须核对前后 Git 状态没有新的 tracked/staged 变化。

## A1. 包与说明文件

```zsh
PKG='/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/handoffs/2026-07-14-pocketworld-migration'
cd "$PKG"
shasum -a 256 -c PACKAGE_SHA256.txt
jq -e '.schema_version == 1 and .status == "safe_checkpoint_incomplete"' STATE.json
```

核对全局配置只读取所需行，不输出其他可能敏感配置：

```zsh
rg -n '^\[agents\]|^max_threads\s*=|^max_depth\s*=' /Users/kaidongwang/.codex/config.toml
```

预期静态配置为 32/1；这不证明当前或新任务的服务端运行时槽位。只能由新任务的实际调度结果确认，且不得为探测上限创建无意义工作。

## A2. 研究 worktree、OpenSpec 与 DVC

```zsh
R='/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714'
cd "$R"
GIT_OPTIONAL_LOCKS=0 git branch --show-current
GIT_OPTIONAL_LOCKS=0 git log -1 --format='%H %T %s'
GIT_OPTIONAL_LOCKS=0 git status --porcelain=v2
BASE='eeb258c980c18193b3dbb64432bca89e480e4ddb'
GIT_OPTIONAL_LOCKS=0 git merge-base --is-ancestor "$BASE" HEAD
actual=$(GIT_OPTIONAL_LOCKS=0 git diff --name-only "$BASE"..HEAD | sort)
expected=$(printf '%s\n' \
  handoffs/2026-07-14-pocketworld-migration/HANDOFF.md \
  handoffs/2026-07-14-pocketworld-migration/PACKAGE_SHA256.txt \
  handoffs/2026-07-14-pocketworld-migration/START_PROMPT.md \
  handoffs/2026-07-14-pocketworld-migration/STATE.json \
  handoffs/2026-07-14-pocketworld-migration/VERIFY.md | sort)
test "$actual" = "$expected"
openspec validate freeze-pocketworld-research-contract --strict
dvc status --json
dvc data status --json
test -z "$(dvc remote list)"
test "$(find data experiments -name '*.dvc' -type f | wc -l | tr -d ' ')" = 14
```

## A3. 产品 E worktree

先执行本节中 branch、HEAD、status 和 SHA/OpenSpec 命令；测试命令移到 B 阶段。

```zsh
P='/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/shutter-v2-thermal-p0-20260714'
cd "$P"
GIT_OPTIONAL_LOCKS=0 git branch --show-current
GIT_OPTIONAL_LOCKS=0 git rev-parse HEAD
GIT_OPTIONAL_LOCKS=0 git status --porcelain=v2
shasum -a 256 \
  lib/capture/manual_capture_ledger.dart \
  lib/capture/sfm_thermal_scheduler.dart \
  test/manual_capture_ledger_test.dart \
  test/sfm_thermal_scheduler_test.dart
openspec validate shutter-v2-thermal-p0 --strict
```

预期 HEAD `58d7f47ede6295f6d0bcb9d422bce17f44301647`，且只有四个指定未跟踪文件。

## A4. cap51 候选 DB

```zsh
DB='/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures/cap51/fresh_device_pull_2026-07-14T085404+0800/retry/sfm_live.db'
stat -f '%z %m %N' "$DB"
shasum -a 256 "$DB"
sqlite3 -readonly "$DB" 'PRAGMA quick_check;'
```

预期：134975488 bytes；SHA `af1bd571d81cf27228e6b1bd8faa9617a1734bf0d32c1c67ec849c4bc7f5ba97`；`ok`。这只证明本地候选文件，不会自动把 fixture 升级为 verdict-eligible。

## A5. 算法共享脏树（避免全树 status）

```zsh
A='/Users/kaidongwang/Developer/Aether3D-cross'
cd "$A"
GIT_OPTIONAL_LOCKS=0 git rev-parse HEAD
GIT_OPTIONAL_LOCKS=0 git branch --show-current
GIT_OPTIONAL_LOCKS=0 git status --porcelain=v1 -- \
  aether_cpp/third_party/glomap_vendor/CMakeLists.txt \
  aether_cpp/third_party/glomap_vendor/bench/aether_l1_plan.h \
  aether_cpp/third_party/glomap_vendor/bench/l1_ghost_tool.cc \
  aether_cpp/third_party/glomap_vendor/bench/sfm_replay_bench.cc
shasum -a 256 \
  aether_cpp/third_party/glomap_vendor/CMakeLists.txt \
  aether_cpp/third_party/glomap_vendor/bench/aether_l1_plan.h \
  aether_cpp/third_party/glomap_vendor/bench/l1_ghost_tool.cc \
  aether_cpp/third_party/glomap_vendor/bench/sfm_replay_bench.cc
```

预期 porcelain 依次为 ` M`、`MM`、`MM`、`??`。两个 `MM` 文件已有 staged 内容；不要修改、暂存、取消暂存或提交前三个 L1 文件。不要运行 `git status --untracked-files=all`。A/B 必须另建干净 `0a8b8428fba3fbf942af01ada6d1e1252a677c6a` worktree。

## B1. 研究轻量测试（允许 ignored cache 写入）

先记录：

```zsh
R='/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714'
cd "$R"
before=$(GIT_OPTIONAL_LOCKS=0 git status --porcelain=v2)
```

测试必须从项目子目录运行：

```zsh
cd "$R/experiments/pocketworld_repro_contract_2026-07-14"
UV_OFFLINE=1 uv run --frozen pytest -q
cd "$R"
after=$(GIT_OPTIONAL_LOCKS=0 git status --porcelain=v2)
test "$after" = "$before"
```

预期：468 passed。不要从仓库根直接跑裸 `python -m pytest`。

## B2. 产品 E 轻量测试（允许 ignored cache 写入）

```zsh
P='/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/shutter-v2-thermal-p0-20260714'
cd "$P"
before=$(GIT_OPTIONAL_LOCKS=0 git status --porcelain=v2)
flutter test --no-pub --no-test-assets \
  test/manual_capture_ledger_test.dart \
  test/sfm_thermal_scheduler_test.dart
flutter analyze --no-pub \
  lib/capture/manual_capture_ledger.dart \
  lib/capture/sfm_thermal_scheduler.dart \
  test/manual_capture_ledger_test.dart \
  test/sfm_thermal_scheduler_test.dart
dart format --output=none --set-exit-if-changed \
  lib/capture/manual_capture_ledger.dart \
  lib/capture/sfm_thermal_scheduler.dart \
  test/manual_capture_ledger_test.dart \
  test/sfm_thermal_scheduler_test.dart
after=$(GIT_OPTIONAL_LOCKS=0 git status --porcelain=v2)
test "$after" = "$before"
```

预期：四个文件仍为未跟踪；55 tests passed；analyze 无问题；format 0 changed。

## C. 核验判定

- 任一 SHA、HEAD、文件集合或测试结果不一致：交接状态为 `drifted`，先报告精确差异。
- `max_threads = 32` 只证明配置文件目标；新任务未实际调度前，运行时并发状态仍是 `unverified`。
- 研究 HEAD 必须是 `eeb258c...` 的后代，且 `eeb258c..HEAD` 的允许列表严格只有本交接包五个文件；否则为 drift。
- 全部通过只代表“交接包可用”，不代表 E/A/B/C/D 完成。
