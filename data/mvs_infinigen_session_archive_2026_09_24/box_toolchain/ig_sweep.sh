#!/bin/bash
# 画质/成本曲线: 全部开去噪, 扫采样数。参照物 = 8192+去噪(已有 /root/ig4_s8192_dn.png)。
set -u
P=/root/ig_venv2/bin/python
cd /root/infinigen
for S in 128 256 512 1024 2048; do
  [ -f /root/sw_$S.png ] && continue
  rm -rf /root/sw /root/ig3/frames /root/frames /root/ig4/frames
  T0=$(date +%s)
  timeout 2400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder /root/ig_probe/coarse --output_folder /root/sw \
    -g fast_solve.gin singleroom.gin \
    -p compose_indoors.terrain_enabled=False \
       configure_render_cycles.num_samples=$S configure_render_cycles.denoise=True \
    > /root/sw_$S.log 2>&1
  T1=$(date +%s)
  for c in /root/sw/frames/Image/camera_0/Image_*.png /root/frames/Image/camera_0/Image_*.png /root/sw/Image_*.png; do
    [ -f "$c" ] && { cp "$c" /root/sw_$S.png; break; }
  done
  echo "  采样 $S : $((T1-T0)) 秒  $( [ -f /root/sw_$S.png ] && echo ok || echo 无图)"
done
touch /root/IGSW_DONE
