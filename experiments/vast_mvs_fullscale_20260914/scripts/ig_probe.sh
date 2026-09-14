#!/bin/bash
cd /root/infinigen_probe
export PATH=/root/.local/bin:$PATH
S=$(date +%s)
/root/ig_venv/bin/python -m infinigen_examples.generate_indoors --seed 0 --task coarse \
  --output_folder /root/ig_out/coarse -g fast_solve.gin singleroom.gin \
  -p compose_indoors.terrain_enabled=False \
     restrict_solving.restrict_parent_rooms=\[\"DiningRoom\"\] \
  > /root/ig_coarse.log 2>&1
RC=$?
E=$(( $(date +%s) - S ))
echo "COARSE_DONE rc=$RC elapsed=${E}s"
ls -la /root/ig_out/coarse/ 2>/dev/null | head
