#!/bin/bash
# run1.sh <build: base|branch> <scene> <arm> <rep>  -> out/<scene>/<build>_<arm>_r<rep>.{tum,csv,log}
set -uo pipefail
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sb
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad
B=$1; SC=$2; ARM=$3; REP=$4
RUNNER=$S/build-$B/pw_euroc_runner
case $SC in
  6e2d4b99) DATA=$P/euroc_6e2d4b99; DEV=$S/cfg/dev_6e2d4b99_td+8.yaml; K=$P/euroc/r6e2d_K.csv; KIND=phone;;
  5966aec0) DATA=$S/data/r5966; DEV=$S/cfg/dev_5966aec0_td+8.yaml; K=$P/euroc/r5966_K.csv; KIND=phone;;
  4ad6e500) DATA=$S/data/r4ad6; DEV=$S/cfg/dev_4ad6e500_td+3.yaml; K=$P/euroc/r4ad6_K.csv; KIND=phone;;
  V1_01) DATA=/Users/kaidongwang/Developer/euroc/V1_01_easy/mav0; DEV=$S/cfg/euroc_sensor.yaml; K=; KIND=euroc;;
  V1_02) DATA=/Users/kaidongwang/Developer/euroc/V1_02_medium/mav0; DEV=$S/cfg/euroc_sensor.yaml; K=; KIND=euroc;;
  V1_03) DATA=/Users/kaidongwang/Developer/euroc/V1_03_difficult/mav0; DEV=$S/cfg/euroc_sensor.yaml; K=; KIND=euroc;;
esac
# arm: <solverprofile>[_A]   e.g. prod, prod_b0.035, upstream, prod_A (no per-frame K)
SP=${ARM%_A}
SLAM=$S/cfg/${KIND}_slam_${SP}.yaml
[ -f "$SLAM" ] || { echo "no $SLAM"; exit 1; }
OUT=$S/out/$SC; mkdir -p $OUT
TAG=${B}_${ARM}_r${REP}
EXTRA=()
if [ "$KIND" = phone ] && [ "$ARM" = "$SP" ]; then EXTRA+=(--intrinsics-csv "$K"); fi
if [ "$B" != base ]; then EXTRA+=(--timing-csv "$OUT/$TAG.csv"); fi
L0=$(sysctl -n vm.loadavg | cut -d" " -f2)
"$RUNNER" "$SLAM" "$DEV" "euroc://$DATA" "$OUT/$TAG.tum" ${EXTRA[@]+"${EXTRA[@]}"} > "$OUT/$TAG.log" 2>&1
rc=$?
echo "$SC $TAG rc=$rc load0=$L0 load1=$(sysctl -n vm.loadavg | cut -d" " -f2) $(shasum -a 256 "$OUT/$TAG.tum" | cut -c1-16) $(grep -E '^\s+wall' "$OUT/$TAG.log" | tr -s ' ')"
