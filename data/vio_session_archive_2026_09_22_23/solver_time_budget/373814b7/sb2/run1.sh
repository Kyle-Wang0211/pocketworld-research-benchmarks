#!/bin/bash
# run1.sh <build: basenr|branch> <scene> <arm> <rep> -> out/<scene>/<build>_<arm>_r<rep>.{tum,csv,log}
# (copied from the previous agent's sb/run1.sh; only OUT/cfg moved to this session's scratchpad)
set -uo pipefail
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/373814b7-9e8a-4c30-8bed-61f68566515c/scratchpad/sb2
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sb
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad
B=$1; SC=$2; ARM=$3; REP=$4
RUNNER=$S/build-$B/pw_euroc_runner
case $SC in
  6e2d4b99) DATA=$P/euroc_6e2d4b99; DEV=$SP/cfg/dev_6e2d4b99_td+8.yaml; K=$P/euroc/r6e2d_K.csv; KIND=phone;;
  V1_01) DATA=/Users/kaidongwang/Developer/euroc/V1_01_easy/mav0; DEV=$SP/cfg/euroc_sensor.yaml; K=; KIND=euroc;;
  V1_02) DATA=/Users/kaidongwang/Developer/euroc/V1_02_medium/mav0; DEV=$SP/cfg/euroc_sensor.yaml; K=; KIND=euroc;;
  V1_03) DATA=/Users/kaidongwang/Developer/euroc/V1_03_difficult/mav0; DEV=$SP/cfg/euroc_sensor.yaml; K=; KIND=euroc;;
esac
SLAM=$SP/cfg/${KIND}_slam_${ARM}.yaml
[ -f "$SLAM" ] || { echo "no $SLAM"; exit 1; }
OUT=$SP/out/$SC; mkdir -p $OUT
TAG=${B}_${ARM}_r${REP}
EXTRA=(--timing-csv "$OUT/$TAG.csv")
if [ "$KIND" = phone ]; then EXTRA+=(--intrinsics-csv "$K"); fi
L0=$(sysctl -n vm.loadavg | cut -d" " -f2)
"$RUNNER" "$SLAM" "$DEV" "euroc://$DATA" "$OUT/$TAG.tum" "${EXTRA[@]}" > "$OUT/$TAG.log" 2>&1
rc=$?
echo "$SC $TAG rc=$rc load0=$L0 load1=$(sysctl -n vm.loadavg | cut -d" " -f2) $(shasum -a 256 "$OUT/$TAG.tum" | cut -c1-16) $(grep -E '^\s+wall' "$OUT/$TAG.log" | tr -s ' ')"
