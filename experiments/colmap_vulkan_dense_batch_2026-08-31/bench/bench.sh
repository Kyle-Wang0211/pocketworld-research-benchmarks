#!/bin/bash
# 稠密单 ref benchmark —— 带强制一致性校验的唯一合法入口。
# =====================================================================
# 2026-08-30 事故:pw_official_dense_moltenvk_host_probe 是 CMake 的
# EXCLUDE_FROM_ALL 目标,`make` 默认**不重建它**。改完 shader 跑 benchmark,
# 跑的是上一次编译的旧二进制,里面嵌的是旧 SPIR-V —— 当天 3 个性能数字
# (63.8s / 58.2s / 并发 86s)全部作废,而且因为跑的是同一个二进制,
# 还伪造出一个"barrier 值 5.6 秒"的假收益和"深度图逐字节相同"的假证明。
#
# 唯一可靠的判据:让 MoltenVK dump 出运行时**实际加载**的 SPIR-V,
# 与 bundle 里的逐字节比对。哈希不一致 ⇒ 拒绝输出任何耗时数字。
set -euo pipefail

WT=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/colmap-vulkan-dense-20260826
BUILD=~/.codex/builds/pw-dense-xorwow-2000-20260829
BUNDLE="$WT/vendor/official_dense/vulkan_shader_bundle"
LABEL="${1:?用法: bench.sh <标签> [模式=photo_ref0]}"
MODE="${2:-photo_ref0}"
OUT=~/Documents/progecttwo/_host_experiments.nosync/dense_bench_${LABEL}
DUMP=$(mktemp -d)
trap 'rm -rf "$DUMP"' EXIT

echo "── [1/6] 编译 shader → SPIR-V ────────────────────────────"
cd "$BUILD" && make pw_official_dense_shaders 2>&1 | grep -E "Built target|error" | tail -2

echo "── [2/6] 更新 manifest pin 并执行官方冻结 ─────────────────"
cd "$WT"
# 🔴 四处锁,对**任何**改动过的 shader 通用(2026-08-30 起不再只认 sweep:
#    改 mat_ops/rotate_f32.comp 时 regenerate 会报 "source identity changed")。
python3 - <<PY
import json, io, re, hashlib, os
GEN = "$BUILD/generated/shaders/"
BUNDLE = "$BUNDLE"
WT = "$WT"

fm_path = os.path.join(BUNDLE, "frozen_manifest.json")
fm = json.load(io.open(fm_path, encoding="utf-8"))

runtime_p = os.path.join(WT, "vendor/official_dense/vulkan_runtime/vulkan_runtime.cc")
bundle_p  = os.path.join(WT, "vendor/official_dense/vulkan_shader_bundle/shader_bundle.cc")
runtime_s = io.open(runtime_p, encoding="utf-8").read()
bundle_s  = io.open(bundle_p,  encoding="utf-8").read()

changed = []
for entry in fm["shaders"]:
    kind = entry["kind"]
    rel  = entry["source_path"]
    src_file = os.path.join(WT, "vendor/official_dense", rel)
    spv_file = os.path.join(GEN, "spirv", rel + ".spv")
    if not os.path.exists(spv_file):
        continue
    src = hashlib.sha256(io.open(src_file, "rb").read()).hexdigest()
    spv_bytes = io.open(spv_file, "rb").read()
    spv = hashlib.sha256(spv_bytes).hexdigest()
    if entry["source_sha256"] == src and entry["spirv_sha256"] == spv:
        continue
    changed.append(rel)
    entry["source_sha256"] = src
    entry["spirv_sha256"]  = spv
    entry["word_count"]    = len(spv_bytes) // 4

    q = re.escape(rel)
    pat_rt = re.compile(r'(\{PipelineKind::' + kind + r', "' + q +
                        r'",\s*\n\s*)"[0-9a-f]{64}"(,\s*\n\s*)"[0-9a-f]{64}"')
    runtime_s, n1 = pat_rt.subn(
        lambda m: m.group(1) + '"' + src + '"' + m.group(2) + '"' + spv + '"', runtime_s)
    assert n1 == 1, "kShaderManifest %s 未命中 (n=%d)" % (rel, n1)

    pat_bd = re.compile(r'(' + kind + r',\s*\n\s*"' + q +
                        r'",\s*\n\s*)"[0-9a-f]{64}"(,\s*\n\s*)"[0-9a-f]{64}"')
    bundle_s, n2 = pat_bd.subn(
        lambda m: m.group(1) + '"' + src + '"' + m.group(2) + '"' + spv + '"', bundle_s)
    assert n2 == 1, "shader_bundle.cc %s 未命中 (n=%d)" % (rel, n2)

io.open(fm_path, "w", encoding="utf-8").write(json.dumps(fm, indent=2) + "\n")
io.open(runtime_p, "w", encoding="utf-8").write(runtime_s)
io.open(bundle_p,  "w", encoding="utf-8").write(bundle_s)
print("   pin 更新: " + (", ".join(changed) if changed else "(无变化)"))
PY

REGEN=$(mktemp -d)
python3 "$BUNDLE/regenerate_frozen_bundle.py" --output "$REGEN"
cp "$REGEN"/assets/*.spv "$BUNDLE/assets/"
cp "$REGEN/shader_bundle_data.inc" "$BUNDLE/"
rm -rf "$REGEN"

echo "── [3/6] 🔴 显式重建 probe(EXCLUDE_FROM_ALL,make 不会自动建) ──"
cd "$BUILD" && make pw_official_dense_moltenvk_host_probe 2>&1 | grep -E "Built target|error" | tail -2

echo "── [4/6] 契约测试 ────────────────────────────────────────"
ctest 2>&1 | grep -E "tests passed|tests failed"

echo "── [5/6] 🔴 运行并 dump,校验加载的 SPIR-V 就是 bundle 里的 ──"
mkdir -p "$OUT"
LOG="$OUT/run.log"
MVK_CONFIG_SHADER_DUMP_DIR="$DUMP" PW_DENSE_PROBE_OUTPUT_ROOT="$OUT" \
  PW_DENSE_PROBE_REAL_MODE="$MODE" "$BUILD/pw_official_dense_moltenvk_host_probe" > "$LOG" 2>&1 || true

WANT=$(shasum -a 256 "$BUNDLE/assets/sweep_sweep_full_openmvs_pcg.comp.spv" | cut -d' ' -f1)
HIT=no
for f in "$DUMP"/*.spv; do
  [ -f "$f" ] || continue
  [ "$(shasum -a 256 "$f" | cut -d' ' -f1)" = "$WANT" ] && HIT=yes
done
if [ "$HIT" != yes ]; then
  echo "❌ 校验失败:运行时加载的 sweep SPIR-V ≠ bundle 里的 ${WANT:0:16}"
  echo "   dump 到的:"; for f in "$DUMP"/*.spv; do echo "     $(shasum -a 256 "$f"|cut -c1-16)"; done
  echo "   ⇒ 拒绝输出耗时数字(这正是 08-30 事故的形态)"
  exit 1
fi
echo "✅ 运行时加载的 sweep = ${WANT:0:16} (与 bundle 一致)"

echo "── [6/6] 结果 ────────────────────────────────────────────"
OK=$(grep -o '"ok":[a-z]*' "$LOG" | tail -1)
MS=$(grep -o '"execution_ms":[0-9]*' "$LOG" | tail -1 | cut -d: -f2)
if [ "$OK" != '"ok":true' ]; then
  echo "❌ 运行失败: $(grep -o '"detail":"[^"]*"' "$LOG" | tail -1)"; exit 1
fi
printf "标签=%s  模式=%s  耗时=%s ms (%.1f s)\n" "$LABEL" "$MODE" "$MS" "$(echo "$MS/1000"|bc -l)"
printf "%s\t%s\t%s\t%s\n" "$(date +%H:%M:%S)" "$LABEL" "$MS" "${WANT:0:16}" >> ~/Developer/dense-bench-20260830/ledger.tsv
echo "已记入 ledger.tsv"
