#!/bin/bash
# Pass 5: 64-bit ArrayIndexer offsets (marching cubes mesh_structure), rebuild, reinstall, re-run the equivalence gates, then the mesh chain.
set -u; OUT=/root/tsdf_full_ep0_fix; M=/root/tsdf_mesh_ep0; rm -f $M/DONE $M/FAILED
EXPECT=$(head -c 400 /root/arm_full_ep0_tsdf/pc_t3.ply | grep -a "element vertex" | awk "{print \$3}")
step() { echo "[$(date -u +%H:%M:%S)] $*"; }
run_guarded() { local lim=$1 log=$2; shift 2; nice -n 10 env OMP_NUM_THREADS=24 "$@" > "$log" 2>&1 & local pid=$! peak=0
  while kill -0 $pid 2>/dev/null; do local rss=$(awk "/VmRSS/{print \$2}" /proc/$pid/status 2>/dev/null || echo 0); [ "${rss:-0}" -gt "$peak" ] && peak=$rss
    [ "${rss:-0}" -gt "$lim" ] && { echo "RSS $rss kB > $lim kB, killing" | tee -a "$log"; kill -9 $pid; }; echo "$(date -u +%H:%M:%S) rss_kb=$rss" > $M/rss.txt; sleep 2; done
  wait $pid; local rc=$?; step "rc=$rc peak_rss_kb=$peak ($log)"; return $rc; }
pkill -f "[n]inja -j12 python-package"; sleep 1
( cd /root/Open3D/build && nice -n 10 ninja -j20 pip-package > /root/o3d_build5.log 2>&1 ) || { tail -5 /root/o3d_build5.log; echo wheel5 > $M/FAILED; exit 1; }
WHL=$(ls -t /root/Open3D/build/lib/python_package/pip_package/*.whl | head -1); step "wheel $WHL"
PY=/root/venv_o3d_fix/bin/python; /root/venv_o3d_fix/bin/pip install -q --force-reinstall --no-deps "$WHL" 2>&1 | tail -1
run_guarded 30000000 $OUT/gate5_r4.log $PY /root/tsdf_ep_3mm.py --int64_kernel --device CPU:0 --block_res 4 --voxel 0.003 --sdf_trunc 0.04 --block_count 8000000 --tag gate5 --out_dir $OUT --expect_points $EXPECT || { echo gate5_run > $M/FAILED; exit 1; }
$PY /root/ply_equal.py $OUT/tsdf_casdiffmvs_gate5_v0.003_t0.04_r4.ply /root/tsdf_full_ep0/tsdf_casdiffmvs_full_ep0_v0.003_t0.04_r4.ply | tee $OUT/gate5_equal.txt || { echo gate5_equal > $M/FAILED; exit 1; }
run_guarded 60000000 $OUT/run_3mm_c.log $PY /root/tsdf_ep_3mm.py --int64_kernel --device CPU:0 --block_res 16 --voxel 0.003 --sdf_trunc 0.04 --block_count 300000 --tag full_ep0c --out_dir $OUT --expect_points $EXPECT || { echo 3mm_c > $M/FAILED; exit 1; }
$PY /root/ply_equal.py $OUT/tsdf_casdiffmvs_full_ep0c_v0.003_t0.04_r16.ply $OUT/tsdf_casdiffmvs_full_ep0_v0.003_t0.04_r16.ply | tee $OUT/gate5_3mm_equal.txt || { echo 3mm_c_equal > $M/FAILED; exit 1; }
run_guarded 95000000 $M/run.log $PY /root/tsdf_ep_mesh.py --int64_kernel --device CPU:0 --block_res 16 --voxel 0.003 --sdf_trunc 0.04 --block_count 300000 --tag full_ep0 --out_dir $M --expect_points $EXPECT || { echo mesh > $M/FAILED; exit 1; }
echo done > $M/DONE
