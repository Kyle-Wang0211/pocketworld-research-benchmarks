#!/bin/bash
# Infinigen Indoors 多视角立体(MVS)小样本 —— 官方配方
#   出处: /root/infinigen/docs/source/ConfiguringCameras.md:99  (mvs_indoors)
#     --configs singleroom.gin multiview_stereo.gin
#     --overrides camera.spawn_camera_rigs.n_camera_rigs=30 compose_indoors.restrict_single_supported_roomtype=True
#     --pipeline_configs ... blender_gt.gin      (深度真值走 blender_gt)
#   偏离: n_camera_rigs 30 -> 12 (箱上算力紧张), 其余逐项照抄。
#   🔴 教训: 我一开始把 configure_cameras.mvs_radius 改成 (2.5,5.0) -> camera_pose_proposal
#      的 while True 死循环(camera.py:262-286, 半径太大时相机永远在墙外, 到中心的射线必被挡)。
#      官方室内默认就在 base_indoors.gin:72 = ('uniform',1,2), 照抄即可, 不要自己填。
#   🔴 原生 4:3: execute_tasks.generate_resolution (execute_tasks.py:235, 在 spawn_camera 之前生效)
#      —— 不是 render_image.render_resolution_override (那个在 coarse 之后改, 相机 sensor 还是 32x18)
#   🔴 纯 CPU: CUDA_VISIBLE_DEVICES="" (configure_cycles_devices 不是 gin configurable)
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
export CUDA_VISIBLE_DEVICES=""
P=/root/ig_venv2/bin/python
cd /root/infinigen
OUT=/root/igmv
W=768; H=576; N=${N:-12}

COMMON="-g fast_solve.gin singleroom.gin multiview_stereo.gin
 -p compose_indoors.terrain_enabled=False
    compose_indoors.restrict_single_supported_roomtype=True
    camera.spawn_camera_rigs.n_camera_rigs=$N
    execute_tasks.generate_resolution=($W,$H)
    get_sensor_coords.W=$W get_sensor_coords.H=$H"

rm -rf $OUT; mkdir -p $OUT
LOG "STEP1 coarse (4:3 原生 ${W}x${H}, n_camera_rigs=$N, mvs_setting=True)"
T0=$(date +%s)
nice -n 15 $P -m infinigen_examples.generate_indoors --seed 0 --task coarse \
  --output_folder $OUT/coarse $COMMON > /root/igmv_coarse.log 2>&1
RC=$?; T1=$(date +%s); LOG "coarse rc=$RC $((T1-T0))s"
[ $RC -ne 0 ] && { tail -25 /root/igmv_coarse.log; exit 1; }

for i in $(seq 0 $((N-1))); do
  LOG "STEP2 render full  cam_rig=$i"
  nice -n 15 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder $OUT/coarse --output_folder $OUT/frames $COMMON \
    execute_tasks.camera_id=\($i,0\) \
    configure_render_cycles.num_samples=128 configure_render_cycles.denoise=True \
    > /root/igmv_full_$i.log 2>&1
  LOG "   rc=$?"
done

for i in $(seq 0 $((N-1))); do
  LOG "STEP3 render flat/blendergt  cam_rig=$i"
  nice -n 15 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder $OUT/coarse --output_folder $OUT/gt $COMMON \
    execute_tasks.camera_id=\($i,0\) \
    render.render_image_func=@flat/render_image \
    > /root/igmv_gt_$i.log 2>&1
  LOG "   rc=$?"
done

LOG "产物:"; find $OUT/frames -maxdepth 2 -type d | sed 's/^/  /'
ls $OUT/frames/camview/camera_0 2>/dev/null | head; ls $OUT/frames/Depth/camera_0 2>/dev/null | head
touch /root/IGMV_DONE; LOG "ALL DONE"
