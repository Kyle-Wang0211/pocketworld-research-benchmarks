#!/bin/bash
# pw_run_arm.sh <label> <mode> [extra -PW flags…]  一场跑到底:闸→启动→心跳轮询→拉取(确认落地)→摘要
set -uo pipefail
LABEL=$1; MODE=$2; shift 2
D=${PW_BENCH_DEVICE:-1B290474-D354-5B4C-AAB0-0805AC5DC832}
S=$(cd "$(dirname "$0")" && pwd); DEST=~/Developer/viobench-recordings; LOGD=$DEST/eval-xrslam-threading-backpressure-20260903; mkdir -p "$LOGD"
REC=run-6e2d4b99-896b-4372-ae47-ac0b4679cf18
LOG="$LOGD/${LABEL}_$(date +%m%d_%H%M%S).log"; exec > >(tee -a "$LOG") 2>&1
echo "══════ $LABEL mode=$MODE flags=$* $(date '+%H:%M:%S') ══════"
P=$(xcrun devicectl device info processes --device "$D" 2>/dev/null)
[ "$(echo "$P" | wc -l)" -gt 50 ] || { echo "进程列表异常,拒绝启动"; exit 1; }
LST() { xcrun devicectl device info files --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --username mobile 2>/dev/null; }
# 有进行中的 run(60 s 内 started 心跳)则拒绝
TMPG=$(mktemp -d); INPROG=0
LALL=$(LST)
for r in $(echo "$LALL" | grep heartbeat.json | grep -E "$(date '+%-m/%-d/%y')" | grep -oE "run-[a-f0-9-]{36}" | sort -u); do
  echo "$LALL" | grep -q "VIOBenchRuns/$r/diagnostics.json" && continue   # 已收尾的 run 不算进行中(其 heartbeat 仍写 started)
  rm -f "$TMPG/hb.json"; xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/VIOBenchRuns/$r/heartbeat.json" --destination "$TMPG/hb.json" >/dev/null 2>&1
  [ -f "$TMPG/hb.json" ] && python3 - "$TMPG/hb.json" <<'PYG' && INPROG=1
import json,sys,datetime
d=json.load(open(sys.argv[1])); t=datetime.datetime.fromisoformat(d.get("written_at_utc","1970-01-01T00:00:00Z").replace("Z","+00:00"))
sys.exit(0 if (d.get("receipt_state")=="started" and (datetime.datetime.now(datetime.timezone.utc)-t).total_seconds()<60) else 1)
PYG
done
[ "$INPROG" = 1 ] && { echo "有 run 正在进行,拒绝启动"; exit 1; }
# 未拉取的 run 先拉(下一次启动会 purge 自测 run)
for r in $(LST | grep -oE "run-[a-f0-9-]{36}" | sort -u | grep -v "$REC"); do
  [ -f "$DEST/$r/receipt.json" ] && continue
  mkdir -p "$DEST/$r"; xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/VIOBenchRuns/$r" --destination "$DEST/$r" >/dev/null 2>&1
  inner="$DEST/$r/$r"; [ -d "$inner" ] && { mv "$inner"/* "$DEST/$r"/ 2>/dev/null; rmdir "$inner"; }; echo "预拉取 $r: $([ -f "$DEST/$r/receipt.json" ] && echo ok || echo 失败)"
done
BEFORE=$(LST | grep -oE "run-[a-f0-9-]{36}" | sort -u)
BK=$(printf "%s" "$*" | grep -q -- "-PWAutoRunBackend" || echo "-PWAutoRunBackend xrslam")
xcrun devicectl device process launch --device "$D" --terminate-existing com.kyle.viobench -- -PWAutoRun "$MODE" $BK "$@" 2>&1 | grep -E "Launched|rror" | head -2
T0=$(date +%s); RUN=""; TMP=$(mktemp -d)
# [09-04] 用户要求: 不要每 5 s 拉心跳。先睡到预期时长(回放 ~70 s; 直播 = -PWAutoRunSeconds + 20 s), 然后每 30 s 只查一次 run 是否收尾。
EXPECT=70; for ((k=1; k<=$#; k++)); do [ "${!k}" = "-PWAutoRunSeconds" ] && { n=$((k+1)); EXPECT=$(( ${!n} + 20 )); }; done
[ "$MODE" = live-soak ] && [ $EXPECT -lt 90 ] && EXPECT=$(( ${PWAUTOSECS:-600} + 20 ))
echo "预期 ${EXPECT}s 后才检查 (中间不拉心跳)"; sleep $EXPECT
for i in $(seq 1 120); do
  LNOW=$(LST); NOW=$(echo "$LNOW" | grep -oE "run-[a-f0-9-]{36}" | sort -u); [ -z "$RUN" ] && { RUN=$(comm -13 <(echo "$BEFORE") <(echo "$NOW") | grep -v "$REC" | head -1); [ -n "$RUN" ] && echo "run=$RUN"; }
  if [ -n "$RUN" ]; then
    echo "$LNOW" | grep -q "VIOBenchRuns/$RUN/diagnostics.json" && { echo "diagnostics.json 已落盘 @ +$(( $(date +%s) - T0 ))s ⇒ 完成"; break; }
    rm -f "$TMP/dg.json"; xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/VIOBenchRuns/$RUN/diagnostics.json" --destination "$TMP/dg.json" >/dev/null 2>&1
    [ -s "$TMP/dg.json" ] && { echo "diagnostics.json 可拷 @ +$(( $(date +%s) - T0 ))s ⇒ 完成(列表失效兜底)"; break; }
  fi
  [ "$(xcrun devicectl device info processes --device "$D" 2>/dev/null | grep -ci VIOReplacementBench)" = 0 ] && { echo "进程已退出 @ +$(( $(date +%s) - T0 ))s(多半是被杀)"; break; }
  sleep 30
done
[ -z "$RUN" ] && { echo "没有新 run"; exit 2; }
sleep 3; mkdir -p "$DEST/$RUN"
for try in 1 2 3; do
  xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/VIOBenchRuns/$RUN" --destination "$DEST/$RUN" >/dev/null 2>&1
  inner="$DEST/$RUN/$RUN"; [ -d "$inner" ] && { mv "$inner"/* "$DEST/$RUN"/ 2>/dev/null; rmdir "$inner"; }
  [ -f "$DEST/$RUN/receipt.json" ] && break; echo "拉取未落地,重试 $try"; sleep 3
done
[ -f "$DEST/$RUN/receipt.json" ] || { echo "✗ 拉取失败:$RUN"; exit 3; }
touch "$DEST/$RUN/.backup_complete"; echo "已拉取: $(ls "$DEST/$RUN" | tr '\n' ' ')"
[ -f "$DEST/$RUN/diagnostics.json" ] && "$S/pw_summ_live.sh" "$DEST/$RUN" || echo "无 diagnostics(未收尾)"
echo "日志: $LOG"
