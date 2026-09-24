#!/bin/bash
set -e
bash -n /root/ig7_coarse_timeout.sh; bash -n /root/ig7_c_finish.sh
TOP=$(ps -eo pid,ppid,args | awk '$2==1 && /manage_[j]obs/ && /ig7_official_c/ {print $1}')
echo "c 顶层调度器 pid=$TOP"; [ -n "$TOP" ]
kill $TOP; sleep 5
echo "c 调度器已停; c 孤儿任务仍在跑: $(ps -eo args | grep -c 'generate_[i]ndoors.*/root/ig7_official_c/')"
nohup bash /root/ig7_coarse_timeout.sh >/dev/null 2>&1 &
sleep 3; echo "--- 超时看门狗第一轮 ---"; cat /root/ig7_coarse_timeout.log 2>/dev/null || echo "(暂无)"
[ ! -e /root/ig7_official_d ]
cd /root; OUTF=/root/ig7_official_d NUM_SCENES=540 nohup /root/ig7_official.sh > /root/ig7_official_d.log 2>&1 &
echo "d 已起 pid $! 于 $(date +%T)"
nohup bash /root/ig7_c_finish.sh >/dev/null 2>&1 &
sleep 90
echo "--- d ---"; grep -A14 "^=====" /root/ig7_official_d.log | tail -12 | grep -e running -e crashed -e succeeded
echo "c 孤儿剩: $(ps -eo args | grep -c 'generate_[i]ndoors.*/root/ig7_official_c/')"; cat /root/ig7_c_finish.log
