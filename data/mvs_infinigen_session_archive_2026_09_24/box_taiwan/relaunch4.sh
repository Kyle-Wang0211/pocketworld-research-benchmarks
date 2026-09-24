#!/bin/bash
set -e
pkill -f "manage_[j]obs" || true; sleep 2; pkill -f "generate_[i]ndoors" || true; sleep 3
echo "残留 ig=$(pgrep -fc "generate_[i]ndoors" || true) mj=$(pgrep -fc "manage_[j]obs" || true)"
mv /root/ig7_official /root/ig7_official_try3_mistake_terrain_on; mv /root/ig7_official.log /root/ig7_official_try3_mistake_terrain_on/manage_jobs.log
python3 - <<'PY'
p="/root/ig7_official.sh"; t=open(p).read()
head,sep,cmd=t.partition("\nexec ")
assert sep, "no exec line"
a="# 仅有的偏离 (全部是用户决定):"
assert head.count(a)==1
head=head.replace(a, a+"""
#   ⓪ compose_indoors.terrain_enabled=False —— 同一文档另外三条官方室内命令都这么写 (ConfiguringCameras.md:20,:39,:76),
#      只有 MVS 那条 (:99) 没写。try2 开地形实测: 每个 coarse 36-51 核, 27 分钟一个没跑完, 16 卡全闲 => 用户选关。
#   ⓪b --pipeline_overrides jobs_to_launch_next.max_stuck_at_task=8 (local_256GB.gin 默认 4)。官方代码 manage_jobs.py:592-594
#      自注: 这组参数用来限并行、降延迟, "may reduce throughput"; 官方命令本身也按机器调并发 (ConfiguringCameras.md:30
#      num_concurrent=15)。用户选「调高并发」。只动这一个开关。
#   ⓪c --num_scenes 340: 官方语义 = 尝试数, 崩溃不补; 按已见 ~10% 失败率尝试 340 以得 ~300。""")
for old,new in [("--num_scenes ${NUM_SCENES:-300}","--num_scenes ${NUM_SCENES:-340}"),
                ("iterate_scene_tasks.n_camera_rigs=30 \\\n","iterate_scene_tasks.n_camera_rigs=30 jobs_to_launch_next.max_stuck_at_task=8 \\\n"),
                ("--overrides compose_indoors.restrict_single_supported_roomtype=True","--overrides compose_indoors.terrain_enabled=False compose_indoors.restrict_single_supported_roomtype=True")]:
    assert cmd.count(old)==1, old
    cmd=cmd.replace(old,new)
open(p,"w").write(head+sep+cmd); print("改好")
PY
bash -n /root/ig7_official.sh
sed -n '/^exec/,$p' /root/ig7_official.sh
nohup /root/ig7_official.sh > /root/ig7_official.log 2>&1 &
sleep 150; grep -A14 "^=====" /root/ig7_official.log | tail -12 | grep -v "^---"; ps -eo pcpu,args | grep "generate_[i]ndoors" | grep -c terrain_enabled=False
