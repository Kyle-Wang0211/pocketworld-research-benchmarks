#!/bin/bash
# Device gate run: liveness gate (twice >200 processes) → product-not-running gate (short-circuits) → install → launch
# → poll DONE (300 s hard cap, progress each 15 s) → pull bench_result.txt → compare digests with the host.
set -u
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/e8c0e65e-e731-470c-87b9-f01ba7ec3498/scratchpad
DEV=1B290474-D354-5B4C-AAB0-0805AC5DC832
APP=/private/tmp/casdiff_dense_stage/CasDiffDenseBench.app; BID=com.kyle.casdiffdensebench
OUT=$S/ios_dense/result; mkdir -p "$OUT"
for i in 1 2; do
  P=$(xcrun devicectl device info processes --device $DEV 2>/dev/null); n=$(echo "$P" | wc -l | tr -d ' ')
  echo "[$(date +%H:%M:%S)] 存活闸 $i: 进程 $n 行"
  [ "$n" -gt 200 ] || { echo "🔴 进程列表异常($n 行),拒绝启动"; exit 1; }
  sleep 3
done
echo "$P" | grep -qiE 'pocketworld|Runner' && { echo "🔴 产品 app 在跑(可能在拍摄),拒绝装机/启动"; exit 1; }
echo "[$(date +%H:%M:%S)] 产品 app 未运行,装 $APP"
xcrun devicectl device install app --device $DEV "$APP" 2>&1 | grep -E "installed|App installed|error|Error" | head -2
echo "[$(date +%H:%M:%S)] launch $BID"
xcrun devicectl device process launch --device $DEV --environment-variables "{\"PW_DENSE_FRAMES\":\"${1:-0-7}\"}" --activate $BID 2>&1 | grep -E "Launched|pid|error|Error" | head -2
T0=$(date +%s)
while true; do
  sleep 15; E=$(( $(date +%s) - T0 )); rm -f "$OUT/DONE"
  xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier $BID --source Documents/DONE --destination "$OUT/DONE" >/dev/null 2>&1
  if [ -f "$OUT/DONE" ]; then echo "[$(date +%H:%M:%S)] DONE after ${E}s: $(cat $OUT/DONE)"; break; fi
  xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier $BID --source Documents/bench_result.txt --destination "$OUT/bench_result.partial.txt" >/dev/null 2>&1
  echo "[$(date +%H:%M:%S)] +${E}s 进展: $(tail -1 "$OUT/bench_result.partial.txt" 2>/dev/null | cut -c1-100)"
  if [ $E -ge 300 ]; then echo "🔴 300 s 上限, 终止"; PID=$(xcrun devicectl device info processes --device $DEV 2>/dev/null | grep -i casdiffdensebench | awk '{print $1}' | head -1); [ -n "$PID" ] && xcrun devicectl device process terminate --device $DEV --pid $PID 2>/dev/null; break; fi
done
xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier $BID --source Documents/bench_result.txt --destination "$OUT/bench_result.txt" >/dev/null 2>&1
echo "===== bench_result.txt (device) ====="; cat "$OUT/bench_result.txt" 2>/dev/null | grep -vE "^H " | tail -8
echo "===== chain summary ====="
