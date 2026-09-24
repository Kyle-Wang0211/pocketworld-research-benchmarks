#!/bin/bash
set -u; OUT=/root/tsdf_mesh_ep0; rm -f $OUT/DONE $OUT/FAILED
EXPECT=$(head -c 400 /root/arm_full_ep0_tsdf/pc_t3.ply | grep -a "element vertex" | awk "{print \$3}")
nice -n 10 env OMP_NUM_THREADS=24 /root/venv_o3d_fix/bin/python /root/tsdf_ep_mesh.py --int64_kernel --device CPU:0 --block_res 16 --voxel 0.003 --sdf_trunc 0.04 --block_count 300000 --tag full_ep0 --out_dir $OUT --expect_points $EXPECT > $OUT/run.log 2>&1 & pid=$!; peak=0
while kill -0 $pid 2>/dev/null; do rss=$(awk "/VmRSS/{print \$2}" /proc/$pid/status 2>/dev/null || echo 0); [ "${rss:-0}" -gt "$peak" ] && peak=$rss; [ "${rss:-0}" -gt 95000000 ] && { echo "RSS $rss > 95 GB, killed" | tee -a $OUT/run.log; kill -9 $pid; }; echo "$(date -u +%H:%M:%S) rss_kb=$rss" > $OUT/rss.txt; sleep 3; done
wait $pid; rc=$?; echo "[$(date -u +%H:%M:%S)] rc=$rc peak_rss_kb=$peak"; [ $rc -eq 0 ] && echo done > $OUT/DONE || echo mesh > $OUT/FAILED
