#!/bin/bash
# GPU 空闲下, 8192 采样 + 去噪(最高画质档), 扫分辨率。
# 🔴 同时检查一件之前没查的事: 4:3 会触发 adjust_camera_sensor 报错(发生在渲染【之后】的
#    存相机参数步)。如果它导致相机参数/深度真值写不出来, 那 4:3 根本产不出训练数据,
#    这比耗时更要命。所以每档都查产物。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/ig_venv2/bin/python
cd /root/infinigen
run(){ # tag W H
  rm -rf /root/igq/$1 /root/igq/frames /root/frames
  local T0=$(date +%s)
  timeout 5400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder /root/ig_probe/coarse --output_folder /root/igq/$1 \
    -g fast_solve.gin singleroom.gin \
    -p compose_indoors.terrain_enabled=False \
       configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True \
       render_image.render_resolution_override=[$2,$3] \
    > /root/igq_$1.log 2>&1
  local RC=$? T1=$(date +%s)
  local IM=$(find /root/igq /root/frames -name "Image*.png" 2>/dev/null | head -1)
  local DE=$(find /root/igq /root/frames -iname "*epth*" -type f 2>/dev/null | head -1)
  local CA=$(find /root/igq /root/frames -iname "*amera*" -o -iname "*.npz" -o -iname "*.npy" 2>/dev/null | head -1)
  LOG "  $1 ($2x$3) rc=$RC  脚本 $((T1-T0))s  Blender $(grep -oE '^Time: [0-9:.]+' /root/igq_$1.log | tail -1)"
  echo "      彩图: ${IM:-🔴无}"
  echo "      深度: ${DE:-🔴无}"
  echo "      相机参数: ${CA:-🔴无}"
  grep -icE "adjust_camera_sensor|Traceback" /root/igq_$1.log | xargs echo "      日志里报错行数:"
}
mkdir -p /root/igq
LOG "8192 + 去噪, GPU 空闲, 扫分辨率"
run r0768x576  768 576
run r1280x720  1280 720
run r1536x1152 1536 1152
run r2048x1536 2048 1536
touch /root/IGQ_DONE
