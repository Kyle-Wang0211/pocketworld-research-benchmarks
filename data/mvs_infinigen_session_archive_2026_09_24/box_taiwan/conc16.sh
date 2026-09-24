#!/bin/bash
set -e
bash -n /root/ig7_e_finish.sh
pgrep -f "ig7_coarse_[t]imeout" >/dev/null && echo "3h 超时看门狗在岗" || { nohup bash /root/ig7_coarse_timeout.sh >/dev/null 2>&1 & echo "看门狗重新拉起"; }
cp /root/ig7_official.sh /root/ig7_official.sh.v_e8
python3 - <<'PY'
p="/root/ig7_official.sh"; t=open(p).read()
head,sep,cmd=t.partition("\nexec ")
old="jobs_to_launch_next.max_stuck_at_task=8 "
assert sep and cmd.count(old)==1
cmd=cmd.replace(old,"jobs_to_launch_next.max_stuck_at_task=${MAX_STUCK:-8} manage_datagen_jobs.num_concurrent=${NUM_CONC:-16} ")
a="# 仅有的偏离 (全部是用户决定):"
head=head.replace(a, a+"""
#   ⓪h (09-24 08:40 UTC, 用户选「继续 fast_solve」+「coarse 并发调到 16 试 1 小时」) e 轮实测: 8 个 fast_solve coarse
#      同时跑 load 仅 110-170/384, GPU 活一阵一阵 (某时刻 0/16 忙, 全部已完成场景都已渲完) ⇒ 瓶颈 = coarse 并发。
#      MAX_STUCK=16 (同时做 coarse 的场景上限) + NUM_CONC=24 (在途场景总上限, local_256GB 默认 16, 含渲染中场景,
#      不调则 coarse 实际到不了 16; 官方命令 ConfiguringCameras.md:30 也改过 num_concurrent)。不传时默认值与之前一致 (8/16)。""")
open(p,"w").write(head+sep+cmd); print("并发参数化")
PY
bash -n /root/ig7_official.sh
TOP=$(ps -eo pid,ppid,args | awk '$2==1 && /manage_[j]obs/ && /ig7_official_e/ && !/use_existing/ {print $1}')
echo "e 顶层调度器 pid=$TOP"; [ -n "$TOP" ]
kill $TOP; sleep 5
echo "e 调度器已停; e 孤儿仍在跑: $(ps -eo args | grep -c 'generate_[i]ndoors.*/root/ig7_official_e/')"
nohup bash /root/ig7_e_finish.sh >/dev/null 2>&1 &
[ ! -e /root/ig7_official_f ]
cd /root; MAX_STUCK=16 NUM_CONC=24 EXTRA_CFG=fast_solve.gin OUTF=/root/ig7_official_f NUM_SCENES=400 nohup /root/ig7_official.sh > /root/ig7_official_f.log 2>&1 &
echo "f 已起 pid $! 于 $(date +%T)"
sleep 150
echo "f coarse 进程: $(ps -eo args | grep 'generate_[i]ndoors.*/root/ig7_official_f/' | grep -c 'task coarse')  带 fast_solve: $(ps -eo args | grep 'generate_[i]ndoors.*/root/ig7_official_f/' | grep -c fast_solve)"
ps -eo args | grep "manage_[j]obs.*ig7_official_f" | head -1 | grep -o -e "max_stuck_at_task=[0-9]*" -e "num_concurrent=[0-9]*"
grep -A14 "^=====" /root/ig7_official_f.log | tail -12 | grep -e max -e running
uptime | sed "s/.*load/load/"
