#!/bin/bash
# ============================================================================
# H. 「每一可用帧」的完整成本 = 彩图(8192+去噪, passes_to_save=[]) + 深度真值(flat/blender_gt)
#    两档分辨率各测一次, 两趟都计时, 并验产物 (camview K + Depth npy)。
# ============================================================================
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*" | tee -a /root/igq6.log; }
P=/root/ig_venv2/bin/python
VP=/venv/main/bin/python
cd /root/infinigen
COARSE=/root/igq2/coarse43     # 4:3, generate_resolution=(1536,1152) 生成
COMMON="-g fast_solve.gin singleroom.gin -p compose_indoors.terrain_enabled=False"
: > /root/igq6.log; mkdir -p /root/igq6

pair(){ # W H
  local W=$1 H=$2 R="execute_tasks.generate_resolution=($1,$2) get_sensor_coords.W=$1 get_sensor_coords.H=$2"
  local d=/root/igq6/p${W}x${H}; rm -rf $d; mkdir -p $d/a $d/b
  local T0=$(date +%s)
  $P -m infinigen_examples.generate_indoors --seed 0 --task render \
     --input_folder $COARSE --output_folder $d/a/out $COMMON $R \
     configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True \
     "full/render_image.passes_to_save=[]" > $d/a.log 2>&1
  local r1=$? T1=$(date +%s)
  $P -m infinigen_examples.generate_indoors --seed 0 --task render \
     --input_folder $COARSE --output_folder $d/b/out $COMMON $R \
     "render.render_image_func=@flat/render_image" > $d/b.log 2>&1
  local r2=$? T2=$(date +%s)
  local SZKEEP=$(find $d -name "Image_*.png" -o -name "camview_*.npz" -o -name "Depth_*.npy" | xargs -r stat -c%s | awk '{s+=$1} END{print s}')
  LOG "  ${W}x${H}: 彩图 $((T1-T0))s (rc=$r1) + 深度 $((T2-T1))s (rc=$r2) = 每帧 $((T2-T0))s | 全部产物 $(du -sb $d|cut -f1) B | 只留三件 ${SZKEEP} B"
  $VP - "$d" "$W" "$H" <<'PY' 2>&1 | tee -a /root/igq6.log
import sys,glob,numpy as np
d,W,H=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
c=glob.glob(d+"/**/camview*.npz",recursive=True); p=glob.glob(d+"/**/Depth_*.npy",recursive=True)
if c:
    z=np.load(c[0]);K=z["K"];print("     K fx=%.2f cx=%.1f cy=%.1f HW=%s 期望fx=%.2f %s"%(
        K[0,0],K[0,2],K[1,2],tuple(z["HW"]),15.0*W/(18.0*(W/H)),
        "OK" if abs(K[0,0]-15.0*W/(18.0*(W/H)))<1e-3 and tuple(z["HW"])==(H,W) else "!!!"))
else: print("     🔴 无 camview")
if p:
    a=np.load(p[0]);m=a<1e9
    print("     Depth %s %s  有效(<1e9)占比=%.3f  min=%.3f max=%.3f  哨兵1e10占比=%.3f"%(
        a.shape,a.dtype,m.mean(),float(a[m].min()),float(a[m].max()),float((a>=1e9).mean())))
else: print("     🔴 无 Depth")
PY
}
LOG "H. 每可用帧 = 彩图 + 深度, 两档"
pair 768 576
pair 1536 1152
touch /root/IGQ6_DONE
LOG "== PHASE H DONE =="
