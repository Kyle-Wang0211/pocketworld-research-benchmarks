#!/bin/zsh
# 通用 RSS 看门狗。这台机器只有 18GB,今天已经被顶到 swap 13/14.3GB、物理空闲 66MB
# 一次 —— 任何长跑的 python 都必须挂着它跑,超阈值立刻 kill 并把"死在多少 GB"记下来。
#
# 被杀不是失败,是数据:峰值 RSS 本身就是"这个配置能不能在 18GB 上跑"的答案。
#
# 用法: run_watched.sh <capGB> <logfile> <命令...>
set -u
CAP_GB="$1"; LOG="$2"; shift 2
CAP_KB=$(( CAP_GB * 1024 * 1024 ))

"$@" >> "$LOG" 2>&1 &
PID=$!
PEAK=0; KILLED=0
while kill -0 $PID 2>/dev/null; do
  # 整棵进程树:融合用 fork worker,只看父进程会严重低估
  RSS=$(ps -eo pid,ppid,rss | awk -v p=$PID '$1==p||$2==p {s+=$3} END {print s+0}')
  [ "$RSS" -gt "$PEAK" ] && PEAK=$RSS
  if [ "$RSS" -gt "$CAP_KB" ]; then
    pkill -9 -P $PID 2>/dev/null; kill -9 $PID 2>/dev/null
    KILLED=1; break
  fi
  sleep 2
done
wait $PID 2>/dev/null; RC=$?
PEAK_GB=$(echo "scale=2; $PEAK/1048576" | bc)
if [ "$KILLED" = "1" ]; then
  echo "[watchdog] KILLED peakRSS=${PEAK_GB}GB cap=${CAP_GB}GB" | tee -a "$LOG"
else
  echo "[watchdog] done rc=$RC peakRSS=${PEAK_GB}GB" | tee -a "$LOG"
fi
