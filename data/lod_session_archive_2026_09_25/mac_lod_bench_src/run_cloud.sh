#!/bin/bash
# 真实聚簇点云台架。一档相机一次冷启动(热预算是硬约束)。
# 用法: ./run_cloud.sh <out.json> <cam> <K> <R> <warm> <base_tenths> <arms> <tag> [cooldown_s]
set -u
UDID=<device-coredevice-id>
BID=com.kyle.PWSplatAB
OUT=$1; CAM=$2; K=$3; R=$4; W=$5; BASE=$6; ARMS=$7; TAG=$8; COOL=${9:-0}
if [ "$COOL" -gt 0 ]; then echo "== cooling ${COOL}s  $(date +%T)"; command sleep "$COOL"; fi
echo "== launch cam=$CAM K=$K R=$R warm=$W base=$BASE arms=$ARMS tag=$TAG  $(date +%T)"
xcrun devicectl device process launch --device $UDID --terminate-existing $BID -- \
  -PWMode cloud -PWCam $CAM -PWK $K -PWR $R -PWWarm $W -PWRad $BASE \
  -PWArms $ARMS -PWTag $TAG 2>&1 | tail -1
rm -f "$OUT"
for i in $(seq 1 400); do
  if xcrun devicectl device copy from --device $UDID --domain-type appDataContainer \
       --domain-identifier $BID --source Documents/SplatAB/cloud.json \
       --destination "$OUT" >/dev/null 2>&1; then
    if python3 -c "import json,sys; sys.exit(0 if json.load(open('$OUT'))['tag']=='$TAG' else 1)" 2>/dev/null; then
      echo "== got $OUT after $i polls  $(date +%T)"; exit 0
    fi
  fi
done
echo "== TIMEOUT waiting for tag=$TAG"; exit 1
