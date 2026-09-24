#!/bin/bash
set -e
cp /root/ig7_official.sh /root/ig7_official.sh.v_c8
python3 - <<'PY'
p="/root/ig7_official.sh"; t=open(p).read()
head,sep,cmd=t.partition("\nexec ")
assert sep
for old,new in [("--num_scenes ${NUM_SCENES:-340} --cleanup big_files \\\n","--num_scenes ${NUM_SCENES:-340} \\\n"),
                ("jobs_to_launch_next.max_stuck_at_task=8 \\\n","jobs_to_launch_next.max_stuck_at_task=8 ground_truth/queue_render.gpus=1 \\\n")]:
    assert cmd.count(old)==1, old
    cmd=cmd.replace(old,new)
a="# 仅有的偏离 (全部是用户决定):"
head=head.replace(a, a+"""
#   ⓪f (09-24 01:40 UTC, 用户批准) c 轮实测每小时约 1 间, 查出:
#      ① 深度 GT 任务 local_256GB.gin:46 设 gpus=0, 单机模式下 = 不分配卡 (submitit_emulator 里 cuda_devices 为空就不设
#         CUDA_VISIBLE_DEVICES), 日志 CUDA_VISIBLE_DEVICES=None + 16 个 OPTIX 全可见 ⇒ 每个 GT 任务占满 16 卡 ⇒ 显存爆
#         (b 轮 58 次 / c 轮 15 次) ⇒ --pipeline_overrides ground_truth/queue_render.gpus=1 (官方开关, 与彩图渲染同样钉一张卡)
#      ⑤ --cleanup big_files 把渲染崩掉的场景也当结束删 *.blend ⇒ 12 间没法补渲 ⇒ 去掉, 回官方默认 none
#      ② Infinigen 墙面材质 bug 打社区补丁 PR #506 (decorate.py 内注明); ④ coarse 超 3 小时判失败由 /root/ig7_coarse_timeout.sh 执行
#         (官方单机模式不设时限, slurm.gin:19 为 48h; 3h 是用户拍板的数值)""")
open(p,"w").write(head+sep+cmd); print("配置已改")
PY
bash -n /root/ig7_official.sh
sed -n '/^exec/,$p' /root/ig7_official.sh
