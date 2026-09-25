#!/bin/bash
# 裸点云台架:一格一次冷启动(热预算是硬约束),跑完把 points.json 取回来。
# 用法: ./run_points.sh <out.json> <cell> <K> <R> <warm> <rad_tenths> <tag>
set -u
UDID=<device-coredevice-id>
BID=com.kyle.PWSplatAB
OUT=$1; CELL=$2; K=$3; R=$4; W=$5; RAD=$6; TAG=$7; COOL=${8:-0}
# 冷却:热漂移是这台机器上最大的混杂,一格一次冷启动 + 跑前静置。
if [ "$COOL" -gt 0 ]; then echo "== cooling ${COOL}s  $(date +%T)"; command sleep "$COOL"; fi
echo "== launch cell=$CELL K=$K R=$R warm=$W rad=$RAD tag=$TAG  $(date +%T)"
xcrun devicectl device process launch --device $UDID --terminate-existing $BID -- \
  -PWMode points -PWCell $CELL -PWK $K -PWR $R -PWWarm $W -PWRad $RAD -PWTag $TAG \
  2>&1 | tail -1
rm -f "$OUT"
# 设备上先把旧结果删掉是做不到的(copy from 只读),所以靠 tag 校验取到的是这一跑。
for i in $(seq 1 240); do
  if xcrun devicectl device copy from --device $UDID --domain-type appDataContainer \
       --domain-identifier $BID --source Documents/SplatAB/points.json \
       --destination "$OUT" >/dev/null 2>&1; then
    if python3 -c "import json,sys; sys.exit(0 if json.load(open('$OUT'))['tag']=='$TAG' else 1)" 2>/dev/null; then
      echo "== got $OUT after $i polls  $(date +%T)"; exit 0
    fi
  fi
done
echo "== TIMEOUT waiting for tag=$TAG"; exit 1
