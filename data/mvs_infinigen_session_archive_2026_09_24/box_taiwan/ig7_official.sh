#!/bin/bash
# Infinigen 第七域 —— 官方原命令复刻: docs/source/ConfiguringCameras.md:97-99
#   "Generate a dataset of indoor rooms with 30 multiview cameras"
# 与官方逐字相同: --pipeline_configs local_256GB.gin monocular.gin blender_gt.gin indoor_background_configs.gin
#                 --configs singleroom.gin multiview_stereo.gin
#                 --pipeline_overrides get_cmd.driver_script=... iterate_scene_tasks.n_camera_rigs=30
#                 --overrides compose_indoors.restrict_single_supported_roomtype=True camera.spawn_camera_rigs.n_camera_rigs=30
# 仅有的偏离 (全部是用户决定):
#   ⓪h (09-24 08:40 UTC, 用户选「继续 fast_solve」+「coarse 并发调到 16 试 1 小时」) e 轮实测: 8 个 fast_solve coarse
#      同时跑 load 仅 110-170/384, GPU 活一阵一阵 (某时刻 0/16 忙, 全部已完成场景都已渲完) ⇒ 瓶颈 = coarse 并发。
#      MAX_STUCK=16 (同时做 coarse 的场景上限) + NUM_CONC=24 (在途场景总上限, local_256GB 默认 16, 含渲染中场景,
#      不调则 coarse 实际到不了 16; 官方命令 ConfiguringCameras.md:30 也改过 num_concurrent)。不传时默认值与之前一致 (8/16)。
#   ⓪g (09-24 03:35 UTC, 用户选「试 fast_solve 1 小时」) d 轮 2h 实测完整配方约 1.5 间/小时 (coarse 20/45/96 分钟、
#      成 3 败 4) ⇒ 试官方自带 fast_solve.gin (只减家具求解步数 300/200/50 -> 100/40/5, HelloRoom.md:18 原话
#      "sacrifices quality for speed"; 画质参数不变)。用 EXTRA_CFG=fast_solve.gin 传入, 顺序同 HelloRoom/v2 放最前;
#      不传时与之前完全相同 (c/d 续跑不传)。
#   ⓪f (09-24 01:40 UTC, 用户批准) c 轮实测每小时约 1 间, 查出:
#      ① 深度 GT 任务 local_256GB.gin:46 设 gpus=0, 单机模式下 = 不分配卡 (submitit_emulator 里 cuda_devices 为空就不设
#         CUDA_VISIBLE_DEVICES), 日志 CUDA_VISIBLE_DEVICES=None + 16 个 OPTIX 全可见 ⇒ 每个 GT 任务占满 16 卡 ⇒ 显存爆
#         (b 轮 58 次 / c 轮 15 次) ⇒ --pipeline_overrides ground_truth/queue_render.gpus=1 (官方开关, 与彩图渲染同样钉一张卡)
#      ⑤ --cleanup big_files 把渲染崩掉的场景也当结束删 *.blend ⇒ 12 间没法补渲 ⇒ 去掉, 回官方默认 none
#      ② Infinigen 墙面材质 bug 打社区补丁 PR #506 (decorate.py 内注明); ④ coarse 超 3 小时判失败由 /root/ig7_coarse_timeout.sh 执行
#         (官方单机模式不设时限, slurm.gin:19 为 48h; 3h 是用户拍板的数值)
#   ⓪e (09-23 15:50 UTC, 用户选「改回 8」) 实测并发 12 时 coarse 77/81/91/93 分钟 (并发 8 时 42/44), load ~450/384 超载
#      ⇒ max_stuck_at_task 12 -> 8。b 轮 --use_existing 续跑剩余渲染, 同时 c 轮新开 (尝试 540, 目标凑满 300 间好房间;
#      机位找不到 = 0/5 候选的确定性失败约占一半, 官方同样丢弃)。
#   ⓪d (09-23 13:10 UTC, 用户选「现在重启, 两个都加」) 首批实测: coarse 42/44 分钟、30 机位渲染+深度约 19 分钟、
#      67 分钟里 GPU 只忙约 19 分钟; 单场景原始产物 4.6 GB × 340 > 1 TB 盘 ⇒
#      ① --cleanup big_files (官方选项, 官方命令 ConfiguringCameras.md:30/:41 就这么用; monitor_tasks.py:79 场景结束时
#         调 util/cleanup.py 删 *.blend/*.obj/*.pkl/assets/ 等, 帧全保留 ⇒ 每场景 ~1.2 GB)
#      ② max_stuck_at_task 8 -> 12 (CPU load 200-300/384 有余量)
#      官方 --use_existing 只续跑已有文件夹、不新建场景 (manage_jobs.py:333), 所以改参数 = 新输出目录新开一轮:
#      /root/ig7_official (首轮, 2 间完成) + /root/ig7_official_b (本轮, 尝试 338)。
#   ⓪ compose_indoors.terrain_enabled=False —— 同一文档另外三条官方室内命令都这么写 (ConfiguringCameras.md:20,:39,:76),
#      只有 MVS 那条 (:99) 没写。try2 开地形实测: 每个 coarse 36-51 核, 27 分钟一个没跑完, 16 卡全闲 => 用户选关。
#   ⓪b --pipeline_overrides jobs_to_launch_next.max_stuck_at_task=8 (local_256GB.gin 默认 4)。官方代码 manage_jobs.py:592-594
#      自注: 这组参数用来限并行、降延迟, "may reduce throughput"; 官方命令本身也按机器调并发 (ConfiguringCameras.md:30
#      num_concurrent=15)。用户选「调高并发」。只动这一个开关。
#   ⓪c --num_scenes 340: 官方语义 = 尝试数, 崩溃不补; 按已见 ~10% 失败率尝试 340 以得 ~300。
#   ① 768x576 (训练代码 blend.py 不 resize + batch=4 => 七域同尺寸; 用户选 768):
#      execute_tasks.generate_resolution + get_sensor_coords.W/H (coarse 与 render 必须同值, 见 render_plan 记忆)
#   ② configure_render_cycles.denoise=True (用户「最高画质+去躁」; 官方默认 False, base_indoors.gin:43)
#   采样数用官方默认 8192 (configs_nature/base.gin:27), 不另传。
# 调度/失败处理全交给官方 manage_jobs (num_scenes = 尝试数, 崩溃场景记录不补; populate/render 失败自动 backup 重试)。
# v2 (自写 bash + fast_solve.gin + terrain_enabled=False) 已于 09-23 11:25 UTC 按用户指令「不要自研, 复刻官方」停用,
#   其成品另放 /root/ig7_blend_v2_fastsolve (不删)。
cd /root/infinigen
exec /root/ig_venv2/bin/python -m infinigen.datagen.manage_jobs \
  --output_folder ${OUTF:-/root/ig7_official} --num_scenes ${NUM_SCENES:-340} \
  --pipeline_configs local_256GB.gin monocular.gin blender_gt.gin indoor_background_configs.gin \
  --configs ${EXTRA_CFG:-} singleroom.gin multiview_stereo.gin \
  --pipeline_overrides get_cmd.driver_script=infinigen_examples.generate_indoors iterate_scene_tasks.n_camera_rigs=30 jobs_to_launch_next.max_stuck_at_task=${MAX_STUCK:-8} manage_datagen_jobs.num_concurrent=${NUM_CONC:-16} ground_truth/queue_render.gpus=1 \
  --overrides compose_indoors.terrain_enabled=False compose_indoors.restrict_single_supported_roomtype=True camera.spawn_camera_rigs.n_camera_rigs=30 \
    "execute_tasks.generate_resolution=(768,576)" get_sensor_coords.W=768 get_sensor_coords.H=576 \
    configure_render_cycles.denoise=True \
  "$@"
