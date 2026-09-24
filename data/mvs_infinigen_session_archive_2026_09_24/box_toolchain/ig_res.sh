#!/bin/bash
# 已定配置 = 8192 采样 + 去噪。测它在三档分辨率上的耗时。
# 目的: 若耗时近乎不随像素数变 => 应按高分辨率渲(高分辨率永远可降采样, 反之补不回)。
# 🔴 4:3 的档会在渲染【之后】的存相机参数步报 adjust_camera_sensor 错, 不影响渲染计时。
# 🔴 纯 CPU, 不碰 GPU(训练中)。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/ig_venv2/bin/python
cd /root/infinigen

run () {   # $1=tag  $2=override(空=用场景原生 1280x720)
  rm -rf /root/igr/$1 /root/igr/frames /root/frames
  local T0=$(date +%s)
  timeout 2400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder /root/ig_probe/coarse --output_folder /root/igr/$1 \
    -g fast_solve.gin singleroom.gin \
    -p compose_indoors.terrain_enabled=False \
       configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True $2 \
    > /root/igr_$1.log 2>&1
  local T1=$(date +%s)
  local BT=$(grep -oE '^Time: [0-9:.]+' /root/igr_$1.log | tail -1)
  local SM=$(grep -oE 'Sample [0-9]+/[0-9]+' /root/igr_$1.log | tail -1)
  local RES=$(grep -oE 'Fra:1 .*' /root/igr_$1.log | head -1 | grep -oE '[0-9]+x[0-9]+' | head -1)
  LOG "  $1 : 脚本 $((T1-T0))s | Blender $BT | $SM"
  # 立刻拷图(整理步骤会移走并互相覆盖)
  for c in /root/igr/frames/Image/camera_0/Image_*.png /root/frames/Image/camera_0/Image_*.png /root/igr/$1/Image_*.png; do
    [ -f "$c" ] && { cp "$c" /root/igr_$1.png; break; }
  done
  [ -f /root/igr_$1.png ] && /venv/main/bin/python -c "
import cv2; im=cv2.imread('/root/igr_$1.png'); print('      实际尺寸', im.shape[1], 'x', im.shape[0])" 2>/dev/null
}

mkdir -p /root/igr
LOG "8192 + 去噪, 三档分辨率"
run r1280x720  ""
run r0768x576  "render_image.render_resolution_override=[768,576]"
run r1536x1152 "render_image.render_resolution_override=[1536,1152]"
run r2048x1536 "render_image.render_resolution_override=[2048,1536]"
touch /root/IGR_DONE
