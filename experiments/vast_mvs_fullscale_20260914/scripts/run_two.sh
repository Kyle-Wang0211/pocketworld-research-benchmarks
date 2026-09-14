#!/usr/bin/env bash
export ALICEVISION_ROOT=/root/meshroom/aliceVision; export LD_LIBRARY_PATH=$ALICEVISION_ROOT/lib
A=$ALICEVISION_ROOT/bin
( while true; do echo "$(date +%H:%M:%S) used_gb=$(free -g|awk '/Mem:/{print $3}')"; sleep 20; done ) > /root/av/mem_two.log 2>&1 &
MON=$!
# ---- 臂 A:同样的 768 深度图,Meshing 全套官方节点默认值(只这一处变) ----
echo "[$(date +%H:%M:%S)] A: 768 深度图 + 官方 Meshing 默认"
$A/aliceVision_meshing --input /root/av/sfm_poses_pp.sfm --depthMapsFolder /root/av/depthmaps \
  --output /root/av/dense_offA.abc --outputMesh /root/av/mesh_offA.obj \
  --maxInputPoints 50000000 --maxPoints 5000000 --maxPointsPerVoxel 1000000 \
  --minStep 2 --pixSizeMarginInitCoef 2 --pixSizeMarginFinalCoef 4 --minAngleThreshold 1.0 \
  --helperPointsGridSize 10 --colorizeOutput 0 > /root/av/mesh_offA.log 2>&1
echo "  A rc=$?  $(grep -viE '\[trace\]' /root/av/mesh_offA.log | grep -ioE 'points loaded[^,]*|[0-9]+ points' | tail -2 | tr '\n' ' ')"
# ---- 臂 B:原生 4032x3008 深度图(官方 downscale=2 的采样密度),其余沿用档案那套 ----
echo "[$(date +%H:%M:%S)] B: 原生深度图 step2"
$A/aliceVision_meshing --input /root/av/sfm_native_pp.sfm --depthMapsFolder /root/av/depthmaps_native \
  --output /root/av/dense_native.abc --outputMesh /root/av/mesh_native.obj \
  --maxInputPoints 400000000 --maxPoints 50000000 --maxPointsPerVoxel 50000000 \
  --minStep 1 --pixSizeMarginInitCoef 1 --pixSizeMarginFinalCoef 0.5 \
  --helperPointsGridSize 10 --colorizeOutput 0 > /root/av/mesh_native.log 2>&1
echo "  B rc=$?"
kill $MON 2>/dev/null
echo "[$(date +%H:%M:%S)] DONE_TWO"
