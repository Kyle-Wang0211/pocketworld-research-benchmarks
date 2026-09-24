#!/bin/bash
set -e
cp /root/ig7_official.sh /root/ig7_official.sh.v_b12
python3 - <<'PY'
p="/root/ig7_official.sh"; t=open(p).read()
head,sep,cmd=t.partition("\nexec ")
assert sep and cmd.count("jobs_to_launch_next.max_stuck_at_task=12")==1
cmd=cmd.replace("jobs_to_launch_next.max_stuck_at_task=12","jobs_to_launch_next.max_stuck_at_task=8")
a="# 仅有的偏离 (全部是用户决定):"
head=head.replace(a, a+"""
#   ⓪e (09-23 15:50 UTC, 用户选「改回 8」) 实测并发 12 时 coarse 77/81/91/93 分钟 (并发 8 时 42/44), load ~450/384 超载
#      ⇒ max_stuck_at_task 12 -> 8。b 轮 --use_existing 续跑剩余渲染, 同时 c 轮新开 (尝试 540, 目标凑满 300 间好房间;
#      机位找不到 = 0/5 候选的确定性失败约占一半, 官方同样丢弃)。""")
open(p,"w").write(head+sep+cmd); print("并发已改 8")
PY
bash -n /root/ig7_official.sh
grep -o "max_stuck_at_task=[0-9]*" /root/ig7_official.sh
# 只停顶层调度器 (ppid=1 的那个 manage_jobs); 子任务不杀
TOP=$(ps -eo pid,ppid,args | awk '$2==1 && /manage_[j]obs/ && /ig7_official_b/ {print $1}')
echo "顶层调度器 pid=$TOP"; [ -n "$TOP" ]
before=$(pgrep -fc "generate_[i]ndoors")
kill $TOP; sleep 10
echo "停调度器前在途 $before 个, 停后仍在跑 $(pgrep -fc "generate_[i]ndoors") 个; 顶层调度器还在: $(ps -p $TOP >/dev/null && echo 是 || echo 否)"
nohup bash /root/drain_resume.sh >/dev/null 2>&1 &
echo "排空脚本已起"
