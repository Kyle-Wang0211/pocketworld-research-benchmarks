#!/bin/bash
cd /root/infinigen_probe
export PATH=/root/.local/bin:$PATH
S=$(date +%s)
/root/ig_venv/bin/python -m infinigen_examples.generate_indoors --seed 0 --task render \
  --input_folder /root/ig_out/coarse --output_folder /root/ig_out/frames \
  > /root/ig_render.log 2>&1
RC=$?
E=$(( $(date +%s) - S ))
echo "RENDER_DONE rc=$RC elapsed=${E}s"
echo "--- 产物 ---"
find /root/ig_out/frames -type f | head -30
echo "--- 文件数按扩展名 ---"
find /root/ig_out/frames -type f | sed "s/.*\.//" | sort | uniq -c
