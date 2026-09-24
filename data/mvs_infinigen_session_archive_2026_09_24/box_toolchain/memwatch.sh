#!/bin/bash
# 内存看门狗:只记录+告警,不杀任何进程(杀了会毁掉 agent 跑到一半的实验)。
# 训练 train.py 是主线,单独记它还在不在。
while true; do
  FREE=$(free -g | awk '/Mem:/{print $7}')
  USED=$(free -g | awk '/Mem:/{print $3}')
  TRAIN=$(pgrep -c -f 'train.py')
  TOP=$(ps -eo rss,comm --sort=-rss | sed -n 2p)
  LVL=OK; [ "$FREE" -lt 20 ] && LVL=WARN; [ "$FREE" -lt 10 ] && LVL=CRIT
  echo "$(date +%H:%M:%S) $LVL avail=${FREE}G used=${USED}G train_procs=$TRAIN top=$TOP" >> /root/memwatch.log
  [ "$LVL" = CRIT ] && echo "$(date +%H:%M:%S) CRIT" >> /root/MEM_CRIT
  sleep 20
done
