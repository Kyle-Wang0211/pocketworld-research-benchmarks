#!/bin/bash
set -e
bash -n /root/ig7_d_finish.sh
cp /root/ig7_official.sh /root/ig7_official.sh.v_d
python3 - <<'PY'
p="/root/ig7_official.sh"; t=open(p).read()
head,sep,cmd=t.partition("\nexec ")
old="--configs singleroom.gin multiview_stereo.gin \\\n"
assert sep and cmd.count(old)==1
cmd=cmd.replace(old,"--configs ${EXTRA_CFG:-} singleroom.gin multiview_stereo.gin \\\n")
a="# 仅有的偏离 (全部是用户决定):"
head=head.replace(a, a+"""
#   ⓪g (09-24 03:35 UTC, 用户选「试 fast_solve 1 小时」) d 轮 2h 实测完整配方约 1.5 间/小时 (coarse 20/45/96 分钟、
#      成 3 败 4) ⇒ 试官方自带 fast_solve.gin (只减家具求解步数 300/200/50 -> 100/40/5, HelloRoom.md:18 原话
#      "sacrifices quality for speed"; 画质参数不变)。用 EXTRA_CFG=fast_solve.gin 传入, 顺序同 HelloRoom/v2 放最前;
#      不传时与之前完全相同 (c/d 续跑不传)。""")
open(p,"w").write(head+sep+cmd); print("脚本已参数化")
PY
bash -n /root/ig7_official.sh
TOP=$(ps -eo pid,ppid,args | awk '$2==1 && /manage_[j]obs/ && /ig7_official_d/ && !/use_existing/ {print $1}')
echo "d 顶层调度器 pid=$TOP"; [ -n "$TOP" ]
kill $TOP; sleep 5
echo "d 调度器已停; d 孤儿仍在跑: $(ps -eo args | grep -c 'generate_[i]ndoors.*/root/ig7_official_d/')"
nohup bash /root/ig7_d_finish.sh >/dev/null 2>&1 &
[ ! -e /root/ig7_official_e ]
cd /root; EXTRA_CFG=fast_solve.gin OUTF=/root/ig7_official_e NUM_SCENES=540 nohup /root/ig7_official.sh > /root/ig7_official_e.log 2>&1 &
echo "e 已起 pid $! 于 $(date +%T)"
sleep 60
echo "e coarse 进程数: $(ps -eo args | grep 'generate_[i]ndoors.*/root/ig7_official_e/' | grep -c 'task coarse'), 其中带 fast_solve: $(ps -eo args | grep 'generate_[i]ndoors.*/root/ig7_official_e/' | grep -c fast_solve)"
ps -eo args | grep 'generate_[i]ndoors.*/root/ig7_official_e/' | head -1 | grep -o -- '-g [^-]*'
cat /root/ig7_d_finish.log
