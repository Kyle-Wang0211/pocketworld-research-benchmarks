#!/bin/bash
set -e
pkill -f "manage_[j]obs" || true; sleep 3; pkill -f "generate_[i]ndoors" || true; sleep 3
echo "残留 ig=$(pgrep -fc "generate_[i]ndoors" || true) mj=$(pgrep -fc "manage_[j]obs" || true)"
cp /root/ig7_official.sh /root/ig7_official.sh.v_a
python3 - <<'PY'
p="/root/ig7_official.sh"; t=open(p).read()
head,sep,cmd=t.partition("\nexec ")
assert sep
a="# 仅有的偏离 (全部是用户决定):"
assert head.count(a)==1
head=head.replace(a, a+"""
#   ⓪d (09-23 13:10 UTC, 用户选「现在重启, 两个都加」) 首批实测: coarse 42/44 分钟、30 机位渲染+深度约 19 分钟、
#      67 分钟里 GPU 只忙约 19 分钟; 单场景原始产物 4.6 GB × 340 > 1 TB 盘 ⇒
#      ① --cleanup big_files (官方选项, 官方命令 ConfiguringCameras.md:30/:41 就这么用; monitor_tasks.py:79 场景结束时
#         调 util/cleanup.py 删 *.blend/*.obj/*.pkl/assets/ 等, 帧全保留 ⇒ 每场景 ~1.2 GB)
#      ② max_stuck_at_task 8 -> 12 (CPU load 200-300/384 有余量)
#      官方 --use_existing 只续跑已有文件夹、不新建场景 (manage_jobs.py:333), 所以改参数 = 新输出目录新开一轮:
#      /root/ig7_official (首轮, 2 间完成) + /root/ig7_official_b (本轮, 尝试 338)。""")
for old,new in [("--output_folder /root/ig7_official ","--output_folder ${OUTF:-/root/ig7_official} "),
                ("jobs_to_launch_next.max_stuck_at_task=8","jobs_to_launch_next.max_stuck_at_task=12"),
                ("--num_scenes ${NUM_SCENES:-340} \\\n","--num_scenes ${NUM_SCENES:-340} --cleanup big_files \\\n")]:
    assert cmd.count(old)==1, old
    cmd=cmd.replace(old,new)
open(p,"w").write(head+sep+cmd); print("改好")
PY
bash -n /root/ig7_official.sh
sed -n '/^exec/,$p' /root/ig7_official.sh
[ ! -e /root/ig7_official_b ]
OUTF=/root/ig7_official_b NUM_SCENES=338 nohup /root/ig7_official.sh > /root/ig7_official_b.log 2>&1 &
echo "launched $!"
