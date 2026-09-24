#!/bin/bash
# ============================================================================
# G. 30 机位 (官方 MVS 档) 的真实成本与可行性
#    官方命令: docs/source/ConfiguringCameras.md:99
#      --configs singleroom.gin multiview_stereo.gin
#      --overrides camera.spawn_camera_rigs.n_camera_rigs=30
#      --pipeline_overrides iterate_scene_tasks.n_camera_rigs=30
#    multiview_stereo.gin -> configure_cameras.mvs_setting=True (configs_nature/multiview_stereo.gin:4)
#    每个机位一次 render, 用 execute_tasks.camera_id=[k,0] (base.gin:12) 选
# ============================================================================
set -u
W=${1:-1536}; H=${2:-1152}
LOG(){ echo "[$(date +%H:%M:%S)] $*" | tee -a /root/igq5.log; }
P=/root/ig_venv2/bin/python
VP=/venv/main/bin/python
cd /root/infinigen
RES="execute_tasks.generate_resolution=($W,$H) get_sensor_coords.W=$W get_sensor_coords.H=$H"
: > /root/igq5.log; mkdir -p /root/igq5
C30=/root/igq5/coarse30

LOG "G1. coarse, 30 机位 @ ${W}x${H}"
rm -rf $C30
T0=$(date +%s)
$P -m infinigen_examples.generate_indoors --seed 0 --task coarse \
   --output_folder $C30 \
   -g fast_solve.gin singleroom.gin multiview_stereo.gin \
   -p compose_indoors.terrain_enabled=False $RES \
      camera.spawn_camera_rigs.n_camera_rigs=30 \
   > /root/igq5_coarse30.log 2>&1
RC=$?; T1=$(date +%s)
LOG "   coarse30 rc=$RC $((T1-T0))s  blend=$(du -sh $C30/scene.blend 2>/dev/null|cut -f1)"
if [ $RC -ne 0 ]; then tail -25 /root/igq5_coarse30.log | sed 's/^/     /' | tee -a /root/igq5.log; touch /root/IGQ5_DONE; exit 1; fi

LOG "G2. 数一下真的有几个机位 + 它们的位姿是否互异"
$P - <<'PY' 2>&1 | tee -a /root/igq5.log
import bpy, numpy as np
bpy.ops.wm.open_mainfile(filepath="/root/igq5/coarse30/scene.blend")
rigs=[o for o in bpy.data.objects if o.name.startswith("CameraRigs")]
cams=[o for o in bpy.data.objects if o.type=="CAMERA"]
print("   CameraRigs 个数:", len(rigs), " CAMERA 对象个数:", len(cams))
locs=np.array([list(c.matrix_world.translation) for c in cams])
print("   相机名样例:", sorted(c.name for c in cams)[:4], "...")
if len(locs)>1:
    d=np.linalg.norm(locs[:,None]-locs[None],axis=-1)
    iu=np.triu_indices(len(locs),1)
    print("   两两距离 min=%.3fm  中位=%.3fm  max=%.3fm"%(d[iu].min(),np.median(d[iu]),d[iu].max()))
    print("   互异(最小间距>1mm):", bool(d[iu].min()>1e-3))
c0=cams[0].data
print("   sensor=%.1fx%.1f  lens=%.1fmm  => W/H=%.4f sensor比=%.4f"%(
    c0.sensor_width,c0.sensor_height,c0.lens, W/H if False else 0, c0.sensor_width/c0.sensor_height))
PY

LOG "G3. 渲 3 个不同机位 (camera_id=[0,0] [10,0] [29,0]), 验 camview 位姿互异"
for k in 0 10 29; do
  d=/root/igq5/cam$k; rm -rf $d; mkdir -p $d
  T0=$(date +%s)
  $P -m infinigen_examples.generate_indoors --seed 0 --task render \
     --input_folder $C30 --output_folder $d/out \
     -g fast_solve.gin singleroom.gin multiview_stereo.gin \
     -p compose_indoors.terrain_enabled=False $RES \
        camera.spawn_camera_rigs.n_camera_rigs=30 \
        "execute_tasks.camera_id=[$k,0]" \
        configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True \
        "full/render_image.passes_to_save=[]" \
     > $d/log 2>&1
  RC=$?; T1=$(date +%s)
  LOG "   cam$k rc=$RC $((T1-T0))s | $(grep -oE '\[Actual rendering\] finished in [0-9:.]+' $d/log|tail -1) | $(du -sb $d|cut -f1) B"
  [ $RC -ne 0 ] && grep -m1 -oE "ValueError.*|Error.*" $d/log | sed 's/^/     ERR /' | tee -a /root/igq5.log
done
$VP - <<'PY' 2>&1 | tee -a /root/igq5.log
import glob,numpy as np
for k in (0,10,29):
    f=glob.glob("/root/igq5/cam%d/**/camview*.npz"%k,recursive=True)
    if not f: print("   cam%d: 无 camview"%k); continue
    z=np.load(f[0]); K=z["K"]; T=z["T"]
    print("   cam%d: fx=%.2f cx=%.1f cy=%.1f HW=%s  位置=%s"%(k,K[0,0],K[0,2],K[1,2],tuple(z["HW"]),np.round(T[:3,3],3)))
PY
touch /root/IGQ5_DONE
LOG "== PHASE G DONE =="
