#!/bin/zsh
# 带内存看门狗的单档导出。上一轮就是 2688x2016 这档把 18GB 的 Mac 撑爆的,
# 所以这次:一次只导一档、单独进程、RSS 超过 LIMIT_GB 立刻 kill -9。
#
# 关键:被杀不是失败,是数据 —— 峰值 RSS 会写进 <outdir>/export_watchdog.log。
# Mac 上导不出来 ≠ 手机上跑不动(转换期内存 ≠ 运行期内存),所以能导出来的都要
# 送上真机实测,导不出来的那档记下它死在多少 GB。
#
# 用法: export_big_watchdog.sh <outdir> <WxH> [LIMIT_GB]
set -u
OUT="$1"; RES="$2"; LIMIT_GB="${3:-12}"
PY=/opt/homebrew/bin/python3.11
SCRIPT="$(cd "$(dirname "$0")" && pwd)/export_bench_resolutions.py"
LOG="$OUT/export_watchdog.log"
mkdir -p "$OUT"

LIMIT_KB=$(( LIMIT_GB * 1024 * 1024 ))
"$PY" "$SCRIPT" "$OUT" "$RES" >> "$OUT/export_${RES}_stdout.log" 2>&1 &
PID=$!

PEAK_KB=0
KILLED=0
while kill -0 $PID 2>/dev/null; do
  RSS=$(ps -o rss= -p $PID 2>/dev/null | tr -d ' ')
  [ -z "$RSS" ] && break
  [ "$RSS" -gt "$PEAK_KB" ] && PEAK_KB=$RSS
  if [ "$RSS" -gt "$LIMIT_KB" ]; then
    kill -9 $PID 2>/dev/null
    KILLED=1
    break
  fi
  sleep 3
done
wait $PID 2>/dev/null
RC=$?
PEAK_GB=$(echo "scale=2; $PEAK_KB/1048576" | bc)
if [ "$KILLED" = "1" ]; then
  echo "$RES\tWATCHDOG-KILLED\tpeakRSS=${PEAK_GB}GB\tlimit=${LIMIT_GB}GB" >> "$LOG"
else
  echo "$RES\trc=$RC\tpeakRSS=${PEAK_GB}GB" >> "$LOG"
fi
tail -1 "$LOG"
