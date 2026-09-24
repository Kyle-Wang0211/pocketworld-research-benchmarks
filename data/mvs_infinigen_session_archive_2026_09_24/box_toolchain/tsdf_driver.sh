#!/bin/bash
# ep0 + TSDF filtered arms (09-08 recipe: official gate replay, Open3D VoxelBlockGrid, sdf_trunc 40 mm), CPU:0 so the training
# GPU (19.9/32.6 GB) is never touched. block_resolution 4 (recipe: 16) because Open3D's kernel indexes voxels with int32
# (VoxelBlockGridImpl.h:40/269) and this scene's 3 mm grid has 234,284 blocks x 4096 x 3 > 2^31 -> CPU segfault at 174,762 blocks.
# Arms: 3 mm (the 09-08 page voxel) and 2 mm (finest that stays under the int32 cap at res 4). RSS watchdog kills the arm only.
set -u
PY=/root/venv_o3d/bin/python; ARM=/root/arm_full_ep0_tsdf; OUT=/root/tsdf_full_ep0; B=/root/bins_tsdf_ep0
EXPECT=$(head -c 400 $ARM/pc_t3.ply | grep -a "element vertex" | awk '{print $3}')
mkdir -p $OUT $B; rm -f $OUT/DONE $OUT/FAILED
echo "[$(date -u +%H:%M:%S)] expect_points=$EXPECT"
run_guarded() {  # <rss_limit_kb> <log> <cmd...>
  local lim=$1 log=$2; shift 2
  nice -n 10 env OMP_NUM_THREADS=24 "$@" > "$log" 2>&1 & local pid=$!
  local peak=0
  while kill -0 $pid 2>/dev/null; do
    local rss=$(awk '/VmRSS/{print $2}' /proc/$pid/status 2>/dev/null || echo 0)
    [ "${rss:-0}" -gt "$peak" ] && peak=$rss
    if [ "${rss:-0}" -gt "$lim" ]; then echo "🔴 RSS ${rss} kB > limit ${lim} kB, killing arm pid $pid" | tee -a "$log"; kill -9 $pid; fi
    sleep 2
  done
  wait $pid; local rc=$?; echo "[$(date -u +%H:%M:%S)] rc=$rc peak_rss_kb=$peak ($log)"; return $rc
}
[ -f $B/full_ep0_rerun.pos ] || /venv/main/bin/python /root/ply2bins.py $ARM/pc_t3.ply $B full_ep0_rerun 2>&1 | tail -2
# ② 3 mm, res 4 (measured 3,799,645 blocks -> 6 M capacity, ~4.6 GB)
run_guarded 40000000 $OUT/run_3mm.log $PY /root/tsdf_ep_3mm.py --device CPU:0 --block_res 4 --voxel 0.003 --sdf_trunc 0.04 --block_count 6000000 \
   --tag full_ep0 --out_dir $OUT --expect_points $EXPECT || { echo 3mm > $OUT/FAILED; exit 1; }
PLY3=$OUT/tsdf_casdiffmvs_full_ep0_v0.003_t0.04_r4.ply; ls -la $PLY3
/venv/main/bin/python /root/ply2bins.py $PLY3 $B full_ep0_tsdf3 2>&1 | tail -2
# ③ 2 mm, res 4 (expected ~8.6 M blocks = 2.27x of 3 mm; cap 11,184,810; capacity 12 M = 9.2 GB up front, no rehash)
run_guarded 60000000 $OUT/run_2mm.log $PY /root/tsdf_ep_3mm.py --device CPU:0 --block_res 4 --voxel 0.002 --sdf_trunc 0.04 --block_count 12000000 \
   --tag full_ep0 --out_dir $OUT --expect_points $EXPECT || { echo 2mm > $OUT/FAILED; exit 1; }
PLY2=$OUT/tsdf_casdiffmvs_full_ep0_v0.002_t0.04_r4.ply; ls -la $PLY2
/venv/main/bin/python /root/ply2bins.py $PLY2 $B full_ep0_tsdf2 2>&1 | tail -2
/venv/main/bin/python /root/gen_meta.py $B full_ep0_rerun full_ep0_tsdf3 full_ep0_tsdf2 2>&1 | tail -12
( cd $B && md5sum *.pos *.col meta.json > md5.txt ); cat $B/md5.txt
echo "[$(date -u +%H:%M:%S)] all done" > $OUT/DONE; cat $OUT/DONE
