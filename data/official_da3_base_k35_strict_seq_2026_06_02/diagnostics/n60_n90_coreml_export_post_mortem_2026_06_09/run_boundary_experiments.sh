#!/bin/bash
# Boundary experiments E1 + E2 to determine the exact trigger for K=60 trace failure.
# Run AFTER a fresh reboot (swap should be ~0 MB).
#
# E1 — Discrete threshold test: run K=55 and K=58 to find where it breaks
#   K=55 PASS + K=58 FAIL → narrow discrete threshold (~K=56)
#   K=55/K=58 BOTH PASS → only K=60+ fails, broad range
#   K=55 FAIL → trigger is below K=55
#
# E2 — Force backend test: run K=60 with --force-sdpa-backend efficient
#   K=60 PASS → confirmed: dispatcher silently switched math→efficient between K=50/K=60
#   K=60 FAIL with explicit traceback → memory-efficient backend isn't the issue
#
# E2b (bonus) — Force math at K=50: should it fail too?
#   K=50 math PASS → math backend always works, dispatcher wasn't the issue
#   K=50 math FAIL → math backend is the real killer, dispatcher saved K=50

set -u

SCRIPT=/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/export_da3_image_only_coreml.py
PY=/Users/kaidongwang/Developer/Aether3D-cross/.venv-da3/bin/python
DA3_REPO=/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3
MODEL_DIR=/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE
OUT_DIR=/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/n60_n90_coreml_export_post_mortem_2026_06_09/boundary_experiments
mkdir -p "$OUT_DIR"

TS=$(date +%Y%m%d_%H%M%S)

dump_vm() {
    echo "  --- vm at $(date +%H:%M:%S) ---"
    PAGE_SIZE=16384
    FREE_PAGES=$(vm_stat | grep 'Pages free' | grep -oE '[0-9]+')
    INACTIVE_PAGES=$(vm_stat | grep 'Pages inactive' | grep -oE '[0-9]+')
    echo "  free MB: $((FREE_PAGES * PAGE_SIZE / 1024 / 1024)) | inactive MB: $((INACTIVE_PAGES * PAGE_SIZE / 1024 / 1024))"
    sysctl vm.swapusage 2>&1 | head -1
}

run_test() {
    local NAME=$1
    local K=$2
    shift 2
    local EXTRA=("$@")
    local LOG="$OUT_DIR/${NAME}_${TS}.log"
    local REPORT="$OUT_DIR/${NAME}_${TS}_report.json"
    local OUT_MODEL="$OUT_DIR/${NAME}_${TS}.mlpackage"

    echo
    echo "==============================================================="
    echo "=== TEST: $NAME (K=$K, extra=${EXTRA[*]:-none}) ==="
    echo "==============================================================="
    dump_vm
    echo "  log: $LOG"
    local T0=$(date +%s)
    KMP_DUPLICATE_LIB_OK=TRUE PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONUNBUFFERED=1 \
        "$PY" -u "$SCRIPT" \
        --official-da3-repo "$DA3_REPO" \
        --model-dir "$MODEL_DIR" \
        --out-model "$OUT_MODEL" \
        --out-report "$REPORT" \
        --window-size "$K" \
        --height 280 --width 504 \
        --convert --compute-precision float16 --minimum-deployment-target iOS18 \
        --static-shape-export-patches \
        --allow-duplicate-openmp \
        ${EXTRA[@]+"${EXTRA[@]}"} \
        > "$LOG" 2>&1
    local EXIT=$?
    local T1=$(date +%s)
    local ELAPSED=$((T1 - T0))
    echo "  exit: $EXIT  elapsed: ${ELAPSED}s"
    echo "  --- log tail ---"
    tail -15 "$LOG" 2>&1 | sed 's/^/    /'
    echo "  --- mlpackage ---"
    if [ -d "$OUT_MODEL" ]; then
        du -sh "$OUT_MODEL" 2>&1 | sed 's/^/    /'
    else
        echo "    (not produced)"
    fi
    dump_vm
}

echo "===== E1 + E2 boundary experiments started at $(date) ====="
dump_vm
echo "Mac boot time: $(sysctl -n kern.boottime | grep -oE 'sec = [0-9]+' | grep -oE '[0-9]+' | head -1 | xargs -I{} date -r {})"

# E1: discrete-threshold test
run_test "e1_n55_default" 55
run_test "e1_n58_default" 58

# E2: force backend at K=60 to verify dispatcher hypothesis
run_test "e2_n60_efficient" 60 --force-sdpa-backend efficient

# E2b: force math at K=50 — does it die?
run_test "e2b_n50_math" 50 --force-sdpa-backend math

echo
echo "===== experiments complete at $(date) ====="
echo "all logs + reports under: $OUT_DIR"
