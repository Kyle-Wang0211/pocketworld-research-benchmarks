#!/bin/bash
# Second pass: patch the two remaining int32 sites (Impl.h:1649 `resolution3 * block_idx`, :140-145 neighbour indices narrowed
# back to int), rebuild the wheel, reinstall, re-run the equivalence gate, then the 2 mm arm + bins + meta.
set -u
OUT=/root/tsdf_full_ep0_fix; B=/root/bins_tsdf_ep0; rm -f $OUT/DONE $OUT/FAILED
EXPECT=$(head -c 400 /root/arm_full_ep0_tsdf/pc_t3.ply | grep -a "element vertex" | awk '{print $3}')
step() { echo "[$(date -u +%H:%M:%S)] $*"; }
run_guarded() { local lim=$1 log=$2; shift 2; nice -n 10 env OMP_NUM_THREADS=24 "$@" > "$log" 2>&1 & local pid=$! peak=0
  while kill -0 $pid 2>/dev/null; do local rss=$(awk '/VmRSS/{print $2}' /proc/$pid/status 2>/dev/null || echo 0); [ "${rss:-0}" -gt "$peak" ] && peak=$rss
    [ "${rss:-0}" -gt "$lim" ] && { echo "🔴 RSS $rss kB > $lim kB, killing" | tee -a "$log"; kill -9 $pid; }; echo "$(date -u +%H:%M:%S) rss_kb=$rss" > $OUT/rss.txt; sleep 2; done
  wait $pid; local rc=$?; step "rc=$rc peak_rss_kb=$peak ($log)"; return $rc; }
cd /root/Open3D; F=cpp/open3d/t/geometry/kernel/VoxelBlockGridImpl.h
sed -i "s/index_t linear_idx = resolution3 \* block_idx + voxel_idx;/int64_t linear_idx = static_cast<int64_t>(block_idx) * resolution3 + voxel_idx;/" $F
sed -i -E "s/^(\s+)index_t (v[xyz][pn]) = GetLinearIdx\(/\1int64_t \2 = GetLinearIdx(/" $F
git diff --stat; grep -nE "resolution3" $F | grep -vE "static_cast<int64_t>|index_t resolution3 =|int64_t n =|/ resolution3|% resolution3"; grep -nE "int64_t v[xyz][pn] = GetLinearIdx" $F | wc -l
( cd build && nice -n 10 ninja -j20 pip-package > /root/o3d_build4.log 2>&1 ) || { tail -5 /root/o3d_build4.log; echo wheel2 > $OUT/FAILED; exit 1; }
WHL=$(ls -t /root/Open3D/build/lib/python_package/pip_package/*.whl | head -1); step "wheel $WHL"
PY=/root/venv_o3d_fix/bin/python; /root/venv_o3d_fix/bin/pip install -q --force-reinstall --no-deps "$WHL" 2>&1 | tail -1
$PY -c "import open3d; print('fix venv: open3d', open3d.__version__)" || { echo venv2 > $OUT/FAILED; exit 1; }
run_guarded 30000000 $OUT/gate2_r4.log $PY /root/tsdf_ep_3mm.py --int64_kernel --device CPU:0 --block_res 4 --voxel 0.003 --sdf_trunc 0.04 --block_count 6000000 --tag gate2 --out_dir $OUT --expect_points $EXPECT || { echo gate2_run > $OUT/FAILED; exit 1; }
$PY /root/ply_equal.py $OUT/tsdf_casdiffmvs_gate2_v0.003_t0.04_r4.ply /root/tsdf_full_ep0/tsdf_casdiffmvs_full_ep0_v0.003_t0.04_r4.ply | tee $OUT/gate2_equal.txt || { echo gate2_equal > $OUT/FAILED; exit 1; }
# 3 mm must also be unchanged by the second patch (sorted-row identity with the first patched build's output)
run_guarded 60000000 $OUT/run_3mm_b.log $PY /root/tsdf_ep_3mm.py --int64_kernel --device CPU:0 --block_res 16 --voxel 0.003 --sdf_trunc 0.04 --block_count 300000 --tag full_ep0b --out_dir $OUT --expect_points $EXPECT || { echo 3mm_b > $OUT/FAILED; exit 1; }
$PY /root/ply_equal.py $OUT/tsdf_casdiffmvs_full_ep0b_v0.003_t0.04_r16.ply $OUT/tsdf_casdiffmvs_full_ep0_v0.003_t0.04_r16.ply | tee $OUT/gate3mm_equal.txt || { echo 3mm_equal > $OUT/FAILED; exit 1; }
run_guarded 90000000 $OUT/run_2mm.log $PY /root/tsdf_ep_3mm.py --int64_kernel --device CPU:0 --block_res 16 --voxel 0.002 --sdf_trunc 0.04 --block_count 800000 --tag full_ep0 --out_dir $OUT --expect_points $EXPECT || { echo 2mm > $OUT/FAILED; exit 1; }
$PY /root/ply2bins_any.py $OUT/tsdf_casdiffmvs_full_ep0_v0.002_t0.04_r16.ply $B full_ep0_tsdf2 2>&1 | tail -2
/venv/main/bin/python /root/gen_meta.py $B full_ep0_rerun full_ep0_tsdf3 full_ep0_tsdf2 2>&1 | tail -12
( cd $B && md5sum full_ep0_rerun.pos full_ep0_rerun.col full_ep0_tsdf3.pos full_ep0_tsdf3.col full_ep0_tsdf2.pos full_ep0_tsdf2.col meta.json > md5.txt ); cat $B/md5.txt
step "all done" > $OUT/DONE; cat $OUT/DONE
