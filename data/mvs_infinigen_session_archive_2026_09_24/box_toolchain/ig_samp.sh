#!/bin/bash
set -u
P=/root/ig_venv2/bin/python
cd /root/infinigen
for S in 256 64; do
  rm -rf /root/ig_probe/f$S
  T0=$(date +%s)
  timeout 2400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder /root/ig_probe/coarse --output_folder /root/ig_probe/f$S \
    -g fast_solve.gin singleroom.gin \
    -p compose_indoors.terrain_enabled=False configure_render_cycles.num_samples=$S \
    > /root/ig_samp_$S.log 2>&1
  T1=$(date +%s)
  R=$(grep -oE "^Time: [0-9:.]+" /root/ig_samp_$S.log | tail -1)
  echo "  采样 $S : 脚本总 $((T1-T0)) 秒 | Blender 报告 $R"
done
touch /root/IGSAMP_DONE
