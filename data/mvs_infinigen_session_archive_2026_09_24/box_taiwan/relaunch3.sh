#!/bin/bash
pkill -f "generate_[i]ndoors"; sleep 3; echo "残留 ig=$(pgrep -fc "generate_[i]ndoors") mj=$(pgrep -fc "manage_[j]obs")"
mv /root/ig7_official /root/ig7_official_try2_terrain_on && mv /root/ig7_official.log /root/ig7_official_try2_terrain_on/manage_jobs.log
python3 - <<'PY'
p="/root/ig7_official.sh"; t=open(p).read(); n0=len(t)
a="""# 仅有的偏离 (全部是用户决定):"""
assert a in t
t=t.replace(a, a+"""
#   ⓪ compose_indoors.terrain_enabled=False —— 同一文档另外三条官方室内命令都这么写 (ConfiguringCameras.md:20,:39,:76),
#      只有 MVS 那条 (:99) 没写。try2 开地形实测: 每个 coarse 36-51 核, 27 分钟一个没跑完, 16 卡全闲 => 用户选关。
#   ⓪b --pipeline_overrides jobs_to_launch_next.max_stuck_at_task=8 (local_256GB.gin 默认 4)。官方代码 manage_jobs.py:592-594
#      自注: 这组参数用来限并行、降延迟, "may reduce throughput"; 官方命令本身也按机器调并发 (ConfiguringCameras.md:30
#      num_concurrent=15)。用户选「调高并发」。只动这一个开关。
#   ⓪c --num_scenes 340: 官方语义 = 尝试数, 崩溃不补; 按已见 ~10% 失败率尝试 340 以得 ~300。""")
for old,new in [("--num_scenes ${NUM_SCENES:-300}","--num_scenes ${NUM_SCENES:-340}"),
                ("iterate_scene_tasks.n_camera_rigs=30 \\\n","iterate_scene_tasks.n_camera_rigs=30 jobs_to_launch_next.max_stuck_at_task=8 \\\n"),
                ("--overrides compose_indoors.restrict_single_supported_roomtype=True","--overrides compose_indoors.terrain_enabled=False compose_indoors.restrict_single_supported_roomtype=True")]:
    assert t.count(old)==1, old
    t=t.replace(old,new)
open(p,"w").write(t); print("改好", n0, "->", len(t))
PY
bash -n /root/ig7_official.sh && echo SYNTAX_OK
sed -n '/^exec/,$p' /root/ig7_official.sh
nohup /root/ig7_official.sh > /root/ig7_official.log 2>&1 &
sleep 120; grep -A14 "^=====" /root/ig7_official.log | tail -12 | grep -v "^---"
