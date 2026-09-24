#!/bin/bash
# 盘 + 内存看门狗:只记录和警告,永不杀进程(杀了会毁掉正在跑的实验)
LOG=/root/diskwatch.log
while true; do
  AVAIL_G=$(df -BG --output=avail /root | tail -1 | tr -dc 0-9)
  USED_PCT=$(df --output=pcent /root | tail -1 | tr -dc 0-9)
  MEM_AVAIL=$(free -g | awk '/^Mem:/{print $7}')
  TS=$(date '+%m-%d %H:%M:%S')
  printf '%s  disk_avail=%sG (%s%% used)  mem_avail=%sG\n' "$TS" "$AVAIL_G" "$USED_PCT" "$MEM_AVAIL" >> $LOG
  if [ "${AVAIL_G:-9999}" -lt 400 ]; then
    printf '%s  [DISK LOW] %sG left\n' "$TS" "$AVAIL_G" >> $LOG
    touch /root/DISK_CRIT
  fi
  if [ "${AVAIL_G:-9999}" -lt 150 ]; then
    printf '%s  [DISK CRITICAL] %sG left -- biggest dirs:\n' "$TS" "$AVAIL_G" >> $LOG
    du -sh /root/*/ 2>/dev/null | sort -rh | head -15 >> $LOG
    touch /root/DISK_EMERG
  fi
  if [ "${MEM_AVAIL:-9999}" -lt 12 ]; then
    printf '%s  [MEM LOW] %sG available\n' "$TS" "$MEM_AVAIL" >> $LOG
    touch /root/MEM_CRIT
  fi
  sleep 120
done
