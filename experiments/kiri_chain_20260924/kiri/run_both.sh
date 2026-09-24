#!/bin/bash
cd /root/tsdf_improve/kiri
mkdir -p out
for vx in 0.01 0.003; do
  echo "===== voxel $vx  $(date +%T)"
  /usr/bin/time -f "  peak RSS %M KB, wall %e s" ./venv/bin/python kiri_tsdf.py $vx out/kiri_v${vx}_t0.04_w5.ply 2>&1
done
echo "ALL DONE $(date +%T)"
