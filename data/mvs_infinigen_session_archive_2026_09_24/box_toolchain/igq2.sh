#!/bin/bash
# ============================================================================
# Infinigen Indoors 开渲方案实测 (第二轮, 修掉第一轮的三个缺陷)
#  ① 4:3 阻塞的【正解验证】: 官方旋钮是 execute_tasks.generate_resolution
#     (src/infinigen_examples/configs_nature/base.gin:62, 由 execute_tasks.py:235-236 落到
#      scene.render.resolution_x/y), 不是 render_image.render_resolution_override
#     (render.py:553-555 只改分辨率, 不重算 sensor)。
#     相机 sensor 在 coarse 阶段由 spawn_camera->adjust_camera_sensor 烤死
#     (placement/camera.py:103-110, 117)。所以 coarse 和 render 必须传【同一个】宽高比。
#     官方自证: configs_indoor/topview.gin:1 = (720,720) 1:1, 非 16:9 且能跑。
#  ② 判据能报警: 直接把 camview*.npz 读出来验 K 是否 = f*W/sensor_w, cx=W/2, cy=H/2。
#  ③ 并行/产物大小/GT(深度)实测。
# ============================================================================
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*" | tee -a /root/igq2.log; }
P=/root/ig_venv2/bin/python
VP=/venv/main/bin/python
cd /root/infinigen
mkdir -p /root/igq2
: > /root/igq2.log

COMMON="-g fast_solve.gin singleroom.gin -p compose_indoors.terrain_enabled=False"
QUAL="configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True"

# ---- 读 npz 验 K ---------------------------------------------------------
verify(){  # $1=目录 $2=W $3=H
python_check=$(cat <<'PY'
import sys, glob, numpy as np
d,W,H=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
cam=glob.glob(d+"/**/camview*.npz",recursive=True)
dep=glob.glob(d+"/**/Depth*.npy",recursive=True)
img=glob.glob(d+"/**/Image*.png",recursive=True)
print("  camview npz:", cam[0] if cam else "NONE")
print("  Depth  npy :", dep[0] if dep else "NONE")
print("  Image  png :", img[0] if img else "NONE")
if cam:
    z=np.load(cam[0]); K=z["K"]; T=z["T"]; HW=z["HW"]
    fx,fy,cx,cy=K[0,0],K[1,1],K[0,2],K[1,2]
    exp_f=15.0*W/(18.0*(W/H))   # f_mm * W / sensor_w, sensor_w=18*(W/H), f=15mm (base_indoors.gin:19)
    ok = abs(fx-fy)<1e-6 and abs(cx-W/2)<1e-6 and abs(cy-H/2)<1e-6 and tuple(HW)==(H,W)
    print("  K: fx=%.3f fy=%.3f cx=%.1f cy=%.1f  HW=%s  期望fx=%.3f  T有限=%s  => %s"
          %(fx,fy,cx,cy,tuple(HW),exp_f,bool(np.isfinite(T).all()),"OK" if ok and abs(fx-exp_f)<1e-3 else "!!! 不合法"))
if dep:
    a=np.load(dep[0]); f=np.isfinite(a)
    print("  Depth: shape=%s dtype=%s 有限值占比=%.3f min=%.4f max=%.4f"
          %(a.shape,a.dtype,f.mean(),float(a[f].min()) if f.any() else -1,float(a[f].max()) if f.any() else -1))
if img:
    import struct,zlib
    with open(img[0],'rb') as fh: b=fh.read(33)
    w,h=struct.unpack(">II",b[16:24]); print("  Image 实际像素: %dx%d"%(w,h))
PY
)
  $VP -c "$python_check" "$1" "$2" "$3" 2>&1 | tee -a /root/igq2.log
}

# ---- A. 4:3 coarse (正解) -------------------------------------------------
COARSE43=/root/igq2/coarse43
if [ ! -f $COARSE43/scene.blend ]; then
  LOG "A. coarse @ 4:3 (execute_tasks.generate_resolution=(1536,1152)), n_camera_rigs=1"
  rm -rf $COARSE43
  T0=$(date +%s)
  $P -m infinigen_examples.generate_indoors --seed 0 --task coarse \
     --output_folder $COARSE43 $COMMON "execute_tasks.generate_resolution=(1536,1152)" \
     "get_sensor_coords.W=1536" "get_sensor_coords.H=1152" \
     > /root/igq2_coarse43.log 2>&1
  RC=$?; T1=$(date +%s)
  LOG "   coarse43 rc=$RC  $((T1-T0))s  blend=$(du -sh $COARSE43/scene.blend 2>/dev/null | cut -f1)"
  [ $RC -ne 0 ] && tail -20 /root/igq2_coarse43.log | sed 's/^/     /' | tee -a /root/igq2.log
fi

# ---- B. 在 4:3 coarse 上扫分辨率 (全部 4:3, 同宽高比) ----------------------
runB(){ # tag W H
  local d=/root/igq2/$1; rm -rf $d; mkdir -p $d
  local T0=$(date +%s)
  timeout 5400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder $COARSE43 --output_folder $d/out \
    $COMMON $QUAL "execute_tasks.generate_resolution=($2,$3)" "get_sensor_coords.W=$2" "get_sensor_coords.H=$3" \
    > /root/igq2_$1.log 2>&1
  local RC=$? T1=$(date +%s)
  local AR=$(grep -oE "\[Actual rendering\] finished in [0-9:.]+" /root/igq2_$1.log | tail -1)
  LOG "   $1 ($2x$3) rc=$RC 脚本 $((T1-T0))s | $AR | 产物 $(du -sb $d 2>/dev/null | cut -f1) B"
  verify $d $2 $3
  grep -m1 -oE "ValueError.*" /root/igq2_$1.log | sed 's/^/     ERR /' | tee -a /root/igq2.log
}
LOG "B. 4:3 分辨率扫描 (8192 + 去噪)"
runB b0768x576  768  576
runB b1024x768  1024 768
runB b1536x1152 1536 1152
runB b2048x1536 2048 1536

# ---- C. GT (flat) 深度真值 -----------------------------------------------
LOG "C. GT flat 渲染 (render.render_image_func=@flat/render_image, 官方 job_funcs.py:443)"
for R in "1536 1152"; do
  set -- $R
  d=/root/igq2/gt_$1x$2; rm -rf $d; mkdir -p $d
  T0=$(date +%s)
  timeout 5400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder $COARSE43 --output_folder $d/out \
    $COMMON "execute_tasks.generate_resolution=($1,$2)" "get_sensor_coords.W=$1" "get_sensor_coords.H=$2" \
    "render.render_image_func=@flat/render_image" \
    > /root/igq2_gt_$1x$2.log 2>&1
  RC=$?; T1=$(date +%s)
  LOG "   GT $1x$2 rc=$RC 脚本 $((T1-T0))s | 产物 $(du -sb $d | cut -f1) B"
  verify $d $1 $2
  grep -m1 -oE "ValueError.*|Error.*" /root/igq2_gt_$1x$2.log | sed 's/^/     ERR /' | tee -a /root/igq2.log
done
touch /root/IGQ2_PHASE1
LOG "== PHASE1 DONE =="
