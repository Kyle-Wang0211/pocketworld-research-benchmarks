#!/bin/bash
# 补充实验(不是三档主实验): 在 200k 云上单独扫 max_intersections 与 ray_trim_offset,
# 目的是刻画"射线密度/阈值"这两个共享常量,判断机制在默认参数下是不是被闸死。
WS=/root/afsr/ws_200k
CB=/root/colmap-4.1.0-fa8e3b3/build/src/colmap/exe/colmap
mkdir -p /root/afsr/sweep
for MI in 1 3 10; do
  for TR in 0.1 0.02 0.005; do
    N=mi${MI}_tr${TR}
    $CB advancing_front_mesher --input_path $WS \
      --output_path /root/afsr/sweep/$N.ply --AdvancingFrontMeshing.num_threads 8 \
      --AdvancingFrontMeshing.visibility_filtering 1 \
      --AdvancingFrontMeshing.visibility_post_filtering 1 \
      --AdvancingFrontMeshing.visibility_filtering_max_intersections $MI \
      --AdvancingFrontMeshing.visibility_ray_trim_offset $TR \
      > /root/afsr/sweep/$N.log 2>&1
    R=$(grep -oE "Removed [0-9]+ of [0-9]+" /root/afsr/sweep/$N.log | tail -1)
    L=$(/venv/main/bin/python /root/layer2.py /root/afsr/sweep/$N.ply "$N" 2>&1 | tail -1)
    echo "$L   [$R]"
  done
done
echo SWEEP_DONE
