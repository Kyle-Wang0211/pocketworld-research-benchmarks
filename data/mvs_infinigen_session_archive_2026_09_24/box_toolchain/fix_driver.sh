#!/bin/bash
# int64-patched Open3D: finish the wheel, install into /root/venv_o3d_fix, gate it against the unpatched build on a
# below-cap case (3 mm, block_res 4: must reproduce the same sorted point set), then run the real arms at block_res 16:
# 3 mm (09-08 recipe) and 2 mm (finest that fits this box's RAM). CPU only; RSS watchdog kills the arm, never the box.
set -u
OUT=/root/tsdf_full_ep0_fix; B=/root/bins_tsdf_ep0; mkdir -p $OUT; rm -f $OUT/DONE $OUT/FAILED
EXPECT=$(head -c 400 /root/arm_full_ep0_tsdf/pc_t3.ply | grep -a "element vertex" | awk '{print $3}')
step() { echo "[$(date -u +%H:%M:%S)] $*"; }
run_guarded() { local lim=$1 log=$2; shift 2; nice -n 10 env OMP_NUM_THREADS=24 "$@" > "$log" 2>&1 & local pid=$! peak=0
  while kill -0 $pid 2>/dev/null; do local rss=$(awk '/VmRSS/{print $2}' /proc/$pid/status 2>/dev/null || echo 0); [ "${rss:-0}" -gt "$peak" ] && peak=$rss
    [ "${rss:-0}" -gt "$lim" ] && { echo "🔴 RSS $rss kB > $lim kB, killing" | tee -a "$log"; kill -9 $pid; }; echo "$(date -u +%H:%M:%S) rss_kb=$rss" > $OUT/rss.txt; sleep 2; done
  wait $pid; local rc=$?; step "rc=$rc peak_rss_kb=$peak ($log)"; return $rc; }
# 1. wheel
/root/venv_o3d/bin/pip install -q pybind11_stubgen wheel setuptools 2>&1 | tail -1
( cd /root/Open3D/build && nice -n 10 ninja -j20 pip-package > /root/o3d_build3.log 2>&1 ) || { tail -5 /root/o3d_build3.log; echo wheel > $OUT/FAILED; exit 1; }
WHL=$(ls /root/Open3D/build/lib/python_package/pip_package/*.whl | head -1); step "wheel $WHL"
# 2. venv
[ -x /root/venv_o3d_fix/bin/python ] || python3 -m venv /root/venv_o3d_fix
/root/venv_o3d_fix/bin/pip install -q "$WHL" plyfile opencv-python-headless torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -1
PY=/root/venv_o3d_fix/bin/python; $PY -c "import open3d, torch, cv2, plyfile; print('fix venv: open3d', open3d.__version__, open3d.__file__)" || { echo venv > $OUT/FAILED; exit 1; }
# 3. gate: below-cap case must reproduce the unpatched build's point set
run_guarded 30000000 $OUT/gate_r4.log $PY /root/tsdf_ep_3mm.py --int64_kernel --device CPU:0 --block_res 4 --voxel 0.003 --sdf_trunc 0.04 --block_count 6000000 --tag gate --out_dir $OUT --expect_points $EXPECT || { echo gate_run > $OUT/FAILED; exit 1; }
$PY /root/ply_equal.py $OUT/tsdf_casdiffmvs_gate_v0.003_t0.04_r4.ply /root/tsdf_full_ep0/tsdf_casdiffmvs_full_ep0_v0.003_t0.04_r4.ply | tee $OUT/gate_equal.txt || { echo gate_equal > $OUT/FAILED; exit 1; }
# 4. real arms, block_res 16 (the 09-08 recipe)
run_guarded 60000000 $OUT/run_3mm.log $PY /root/tsdf_ep_3mm.py --int64_kernel --device CPU:0 --block_res 16 --voxel 0.003 --sdf_trunc 0.04 --block_count 300000 --tag full_ep0 --out_dir $OUT --expect_points $EXPECT || { echo 3mm > $OUT/FAILED; exit 1; }
/root/venv_o3d_fix/bin/python /root/ply2bins_any.py $OUT/tsdf_casdiffmvs_full_ep0_v0.003_t0.04_r16.ply $B full_ep0_tsdf3 2>&1 | tail -2
run_guarded 90000000 $OUT/run_2mm.log $PY /root/tsdf_ep_3mm.py --int64_kernel --device CPU:0 --block_res 16 --voxel 0.002 --sdf_trunc 0.04 --block_count 800000 --tag full_ep0 --out_dir $OUT --expect_points $EXPECT || { echo 2mm > $OUT/FAILED; exit 1; }
/root/venv_o3d_fix/bin/python /root/ply2bins_any.py $OUT/tsdf_casdiffmvs_full_ep0_v0.002_t0.04_r16.ply $B full_ep0_tsdf2 2>&1 | tail -2
/venv/main/bin/python /root/gen_meta.py $B full_ep0_rerun full_ep0_tsdf3 full_ep0_tsdf2 2>&1 | tail -12
( cd $B && md5sum full_ep0_rerun.pos full_ep0_rerun.col full_ep0_tsdf3.pos full_ep0_tsdf3.col full_ep0_tsdf2.pos full_ep0_tsdf2.col meta.json > md5.txt ); cat $B/md5.txt
step "all done" > $OUT/DONE; cat $OUT/DONE
