#!/bin/bash
# ============================================================================
# F. 「14 个 AOV 分解通道」是不是白花钱?
#    full/render_image.passes_to_save (configs_nature/base.gin:39-54) 默认存 14 个通道,
#    MVS 训练只要 Image + camview + Depth。官方自证可以清空: configs_nature/asset_demo.gin:9
#    `full/render_image.passes_to_save = []`。测单变量: 耗时 + 产物大小。
# ============================================================================
set -u
W=${1:-1536}; H=${2:-1152}
LOG(){ echo "[$(date +%H:%M:%S)] $*" | tee -a /root/igq4.log; }
P=/root/ig_venv2/bin/python
cd /root/infinigen
COARSE=/root/igq2/coarse43
COMMON="-g fast_solve.gin singleroom.gin -p compose_indoors.terrain_enabled=False"
QUAL="configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True"
RES="execute_tasks.generate_resolution=($W,$H) get_sensor_coords.W=$W get_sensor_coords.H=$H"
: > /root/igq4.log; mkdir -p /root/igq4

arm(){ # tag extra...
  local tag=$1; shift
  local d=/root/igq4/$tag; rm -rf $d; mkdir -p $d
  local T0=$(date +%s)
  $P -m infinigen_examples.generate_indoors --seed 0 --task render \
     --input_folder $COARSE --output_folder $d/out $COMMON $QUAL $RES "$@" \
     > $d/log 2>&1
  local RC=$? T1=$(date +%s)
  local AR=$(grep -oE "\[Actual rendering\] finished in [0-9:.]+" $d/log | tail -1)
  LOG "  $tag rc=$RC 脚本 $((T1-T0))s | $AR | 产物 $(du -sb $d/frames $d/out 2>/dev/null | awk '{s+=$1} END{print s}') B"
  find $d -name "*.png" -o -name "*.exr" -o -name "*.npz" | sed 's|.*/||' | sort | tr '\n' ' ' | sed 's/^/     文件: /' | tee -a /root/igq4.log; echo | tee -a /root/igq4.log
}
LOG "F. passes_to_save 单变量 @ ${W}x${H}, 8192+去噪"
arm f_allpasses
arm f_nopasses "full/render_image.passes_to_save=[]"
touch /root/IGQ4_DONE
LOG "== PHASE F DONE =="
