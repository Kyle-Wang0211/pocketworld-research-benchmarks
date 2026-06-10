#!/usr/bin/env bash
# Run K=90 iPhone bench → R2-R5 oracle → coarse PLY
#
# Prereqs (already in this turn):
# - iPhone has com.kyle.pocketworldOnnxBench.k35476742 installed (DA3 K90 414f bench)
# - User has pulled da3_bench_run_*/ from iPhone Documents via Finder to:
#     ${IPHONE_RUN_DIR}/da3_bench_run_*
# - 414 source jpgs at ${SOURCE_JPGS_DIR} (000000.jpg .. 000413.jpg)
#
# Usage:
#   bash run_k90_iphone_oracle.sh /path/to/da3_bench_run_xxxxx

set -euo pipefail

IPHONE_RUN_DIR="${1:?usage: $0 <da3_bench_run_dir>}"
REPO="/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks"
DA3_SRC="/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3/src"
DA3_VENDOR="/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3/da3_streaming"

# DA3-BASE weights snapshot (downloaded earlier; reuse K=35 path)
K35_DIR="${REPO}/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/da3base_official_streaming_k35_overlap18_full414_mac_2026_06_05"
SALAD_CKPT="${K35_DIR}/weights/dino_salad.ckpt"
DA3_BASE_SNAPSHOT="${K35_DIR}/weights"   # dir containing model.safetensors + config.json
CAPTURE_DIR="${REPO}/data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict"
MANIFEST="${CAPTURE_DIR}/da3_input_manifest.json"
# Use bench app's test_images dir — already has 000000.jpg..000413.jpg in cap-N sort,
# the same data iPhone fed to DA3 inference.
SOURCE_JPGS_DIR="/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_da3_bench/assets/test_images"

# Output dir for K=90 oracle
TODAY=$(date +%Y_%m_%d)
OUT_DIR="${REPO}/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/da3base_official_streaming_k90_overlap45_iphone_${TODAY}"
mkdir -p "${OUT_DIR}/_tmp_results_unaligned"

echo "=== convert iPhone window outputs → oracle chunks ==="
python3 "${REPO}/tools/python/da3_iphone_window_outputs_to_oracle_chunks.py" \
  --iphone-run-dir "${IPHONE_RUN_DIR}" \
  --source-images-dir "${SOURCE_JPGS_DIR}" \
  --output-dir "${OUT_DIR}/_tmp_results_unaligned" \
  --input-height 280 --input-width 504

echo
echo "=== run oracle resume (R2-R5: SALAD loop + Sim3 + LoopOptimizer + fusion) ==="
python3 "${REPO}/tools/python/da3base_official_streaming_oracle_resume.py" \
  --capture-dir "${CAPTURE_DIR}" \
  --manifest "${MANIFEST}" \
  --output-dir "${OUT_DIR}" \
  --vendor-dir "${DA3_VENDOR}" \
  --da3-src-dir "${DA3_SRC}" \
  --da3-base-snapshot "${DA3_BASE_SNAPSHOT}" \
  --salad-ckpt "${SALAD_CKPT}" \
  --chunk-size 90 \
  --overlap 45 \
  --mps-chunked-sdpa off \
  --align-lib numpy

echo
echo "=== output ==="
echo "Combined PLY:  ${OUT_DIR}/pcd/combined_pcd.ply"
ls -la "${OUT_DIR}/pcd/" 2>&1 | head -10
