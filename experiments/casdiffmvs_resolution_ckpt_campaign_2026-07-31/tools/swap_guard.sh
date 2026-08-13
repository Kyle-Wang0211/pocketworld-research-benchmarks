#!/bin/zsh
# 第二道保险:RSS 看门狗只看进程自身,但这台 18GB 的机器 swap 已经吃到 11/12GB,
# 有可能在 RSS 触到 12GB 之前就先"应用程序内存不足"。所以再加一条:剩余 swap
# 低于 THRESH_MB 就立刻杀导出进程 —— 保机器优先,导出失败本身就是可记录的结论。
set -u
THRESH_MB=${1:-700}
LOG=/Users/kaidongwang/Documents/progecttwo/_host_fixtures/bench_models/export_watchdog.log
while true; do
  PID=$(pgrep -f export_bench_resolutions.py | head -1)
  [ -z "$PID" ] && exit 0
  FREE=$(sysctl -n vm.swapusage | sed -E 's/.*free = ([0-9.]+)M.*/\1/')
  FREE_INT=${FREE%%.*}
  if [ "${FREE_INT:-9999}" -lt "$THRESH_MB" ]; then
    RSS=$(ps -o rss= -p $PID | tr -d ' ')
    kill -9 $PID
    echo "SWAP-GUARD-KILLED\tfreeSwap=${FREE}MB\tRSS=$(echo "scale=2;$RSS/1048576"|bc)GB" >> "$LOG"
    exit 0
  fi
  sleep 5
done
