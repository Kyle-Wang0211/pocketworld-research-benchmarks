#!/bin/bash
# LOD 台架真机一次启动(一朵云 × 一种 mode)。🔴 只在用户批准装机、并且用户说「在了」之后由主会话执行。
# 只碰台架 bundle com.kyle.PWSplatAB;脚本里没有任何 uninstall / flutter 命令。
# 用法: ./run_lod.sh <out.json> <oct_prod|oct_216M> <perf|correct|lodverify> <tag> [cooldown_s] [extra lod args]
set -u
UDID=<device-coredevice-id>
BID=com.kyle.PWSplatAB
OUT=$1; OCT=$2; MODE=$3; TAG=$4; COOL=${5:-0}; EXTRA=${6:-}
if [ "$COOL" -gt 0 ]; then echo "== cooling ${COOL}s  $(date +%T)"; command sleep "$COOL"; fi
if [ "$MODE" = "lodverify" ]; then
  echo "== launch lodverify oct=$OCT  $(date +%T)"
  xcrun devicectl device process launch --device $UDID --terminate-existing $BID -- \
    -PWMode lodverify -PWOct $OCT -PWTag $TAG 2>&1 | tail -1
  SRC=Documents/SplatAB/lod_verify_${OCT}_$TAG.json   # tag in the name: never picks up a stale file
else
  echo "== launch lod oct=$OCT mode=$MODE tag=$TAG extra='$EXTRA'  $(date +%T)"
  xcrun devicectl device process launch --device $UDID --terminate-existing $BID -- \
    -PWMode lod -PWOct $OCT -PWLodArgs "mode=$MODE $EXTRA" -PWTag $TAG 2>&1 | tail -1
  SRC=Documents/SplatAB/lod_$TAG.json
fi
mkdir -p "$(dirname "$OUT")"; rm -f "$OUT"
# 结果文件写完才出现(一次性 fwrite);perf 约 5–8 分钟,轮询上限 30 分钟。
for i in $(seq 1 360); do
  if xcrun devicectl device copy from --device $UDID --domain-type appDataContainer \
       --domain-identifier $BID --source $SRC --destination "$OUT" >/dev/null 2>&1; then
    if [ "$MODE" = "lodverify" ] || python3 -c "import json,sys; sys.exit(0 if json.load(open('$OUT'))['tag']=='$TAG' else 1)" 2>/dev/null; then
      echo "== got $OUT after $i polls  $(date +%T)"; exit 0
    fi
  fi
  command sleep 5
done
echo "== TIMEOUT waiting for $SRC tag=$TAG"; exit 1
