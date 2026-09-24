#!/bin/bash
set -u; OUT=/root/tsdf_full_ep0_legacy; B=/root/bins_tsdf_ep0; mkdir -p $OUT; rm -f $OUT/DONE $OUT/FAILED
EXPECT=$(head -c 400 /root/arm_full_ep0_tsdf/pc_t3.ply | grep -a "element vertex" | awk "{print \$3}")
nice -n 10 env OMP_NUM_THREADS=24 /root/venv_o3d/bin/python /root/tsdf_ep_legacy.py --device CPU:0 --voxel 0.003 --sdf_trunc 0.04 --tag full_ep0 --out_dir $OUT --expect_points $EXPECT > $OUT/run_3mm.log 2>&1 & pid=$!; peak=0
while kill -0 $pid 2>/dev/null; do rss=$(awk "/VmRSS/{print \$2}" /proc/$pid/status 2>/dev/null || echo 0); [ "${rss:-0}" -gt "$peak" ] && peak=$rss; [ "${rss:-0}" -gt 95000000 ] && { echo "RSS $rss kB > 95 GB, killed" | tee -a $OUT/run_3mm.log; kill -9 $pid; }; echo "$(date -u +%H:%M:%S) rss_kb=$rss" > $OUT/rss.txt; sleep 3; done
wait $pid; rc=$?; echo "[$(date -u +%H:%M:%S)] rc=$rc peak_rss_kb=$peak"; [ $rc -eq 0 ] || { echo 3mm_legacy > $OUT/FAILED; exit 1; }
PLY=$OUT/tsdf_legacy_full_ep0_v0.003_t0.04.ply; ls -la $PLY
/root/venv_o3d/bin/python /root/ply2bins_any.py $PLY $B full_ep0_tsdf3 2>&1 | tail -2
/venv/main/bin/python /root/gen_meta.py $B full_ep0_rerun full_ep0_tsdf3 2>&1 | tail -8
( cd $B && md5sum full_ep0_rerun.pos full_ep0_rerun.col full_ep0_tsdf3.pos full_ep0_tsdf3.col meta.json > md5.txt ); cat $B/md5.txt
echo "[$(date -u +%H:%M:%S)] done" > $OUT/DONE
