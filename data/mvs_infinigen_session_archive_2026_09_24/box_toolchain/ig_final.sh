#!/bin/bash
# 按已定配置测准成本: 8192 采样 + 去噪, 分别在 1280x720 与我们真正要的 768x576 上。
# 768x576 会触发 adjust_camera_sensor 报错(发生在渲染【之后】的存相机参数步), 不影响计时。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/ig_venv2/bin/python
cd /root/infinigen
run () {  # $1=tag  $2=extra
  rm -rf /root/igf/$1 /root/igf/frames /root/frames
  local T0=$(date +%s)
  timeout 2400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder /root/ig_probe/coarse --output_folder /root/igf/$1 \
    -g fast_solve.gin singleroom.gin \
    -p compose_indoors.terrain_enabled=False \
       configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True $2 \
    > /root/igf_$1.log 2>&1
  local T1=$(date +%s)
  LOG "  $1 : 脚本 $((T1-T0))s | Blender $(grep -oE "^Time: [0-9:.]+" /root/igf_$1.log | tail -1) | 采样 $(grep -oE "Sample [0-9]+/[0-9]+" /root/igf_$1.log | tail -1)"
}
mkdir -p /root/igf
LOG "8192 + 去噪, 两种分辨率"
run r720 ""
run r576 "render_image.render_resolution_override=[768,576]"
touch /root/IGF_DONE
