#!/bin/bash
# run_ac.sh <tag> <euroc_dir> <dev.yaml> <k.csv> <ref.tum> [--twice]
#   A_base : 纯净 8a1cc12 库 + runner,无 CSV
#   A_new  : 逐帧内参库 + runner,无 CSV      ⇒ 与 A_base 的 tum sha256 必须相同
#   C_new  : 逐帧内参库 + runner,--intrinsics-csv
set -uo pipefail
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad
TAG="$1"; E="$2"; DEV="$3"; KCSV="$4"; REF="$5"; TWICE="${6:-}"
SLAM="$S/runs/slam.yaml"; OUT="$S/runs"
BASE="$S/xrslam-base/build-pc/pw_euroc_runner"
NEW="$HOME/Developer/xrslam-4beb1a9-thr/build-pc-pfk/pw_euroc_runner"
PY=/opt/homebrew/bin/python3.11
ATE=$HOME/Developer/viobench-recordings/ate.py
run() { local bin="$1" out="$2"; shift 2; echo "── $(basename $out)"; "$bin" "$SLAM" "$DEV" "euroc://$E" "$out" "$@" 2> "$out.log"; local rc=$?; grep -E "images|poses|K matched|fx\(t\)|GetInfo|wall" "$out.log" | sed 's/^/   /'; echo "   rc=$rc"; }
run "$BASE" "$OUT/A_base_$TAG.tum"
[ "$TWICE" = "--twice" ] && run "$BASE" "$OUT/A_base2_$TAG.tum"
run "$NEW"  "$OUT/A_new_$TAG.tum"
run "$NEW"  "$OUT/C_new_$TAG.tum" --intrinsics-csv "$KCSV"
echo "── sha256"; shasum -a 256 "$OUT"/A_base_$TAG.tum "$OUT"/A_base2_$TAG.tum "$OUT"/A_new_$TAG.tum "$OUT"/C_new_$TAG.tum 2>/dev/null | sed 's/^/   /'
echo "── ATE vs ARKit(ate.py --ref-y-up)"
for arm in A_base A_new C_new; do echo "   [$arm]"; $PY "$ATE" "$OUT/${arm}_$TAG.tum" "$REF" --ref-y-up | sed 's/^/   /'; done
