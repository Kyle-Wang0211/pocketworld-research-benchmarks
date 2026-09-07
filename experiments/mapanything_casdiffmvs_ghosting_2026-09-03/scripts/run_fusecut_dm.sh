#!/usr/bin/env bash
# AliceVision fuseCut (Jancosek/Pajdla, weakly-supported-surface graph cut = the RealityScan lineage) on the NATIVE
# depth-map input — the same path Meshroom/RealityScan use — then the mesh arbitrates the full-resolution
# official CasDiffMVS cloud (kept points are unchanged, no resampling).
#   run_fusecut_dm.sh <tag> <maxPoints>
set -uo pipefail
TAG=${1:?tag}; MAXP=${2:-10000000}
export ALICEVISION_ROOT=/root/meshroom/aliceVision; export LD_LIBRARY_PATH=$ALICEVISION_ROOT/lib
PY=/venv/main/bin/python; A=$ALICEVISION_ROOT/bin
echo "[$(date +%H:%M:%S)] fuseCut meshing from depth maps (maxPoints $MAXP)"
$A/aliceVision_meshing --input /root/av/sfm_poses.sfm --depthMapsFolder /root/av/depthmaps \
  --output /root/av/dense_$TAG.abc --outputMesh /root/av/mesh_$TAG.obj \
  --maxInputPoints 50000000 --maxPoints $MAXP --maxPointsPerVoxel 50000000 \
  --helperPointsGridSize 10 --colorizeOutput 1 > /root/av/mesh_$TAG.log 2>&1
echo "meshing rc=$?"
grep -viE "\[trace\]" /root/av/mesh_$TAG.log | tail -5 | cut -c1-140
[ -s /root/av/mesh_$TAG.obj ] || { echo AV_MESH_FAILED; exit 1; }
ls -la /root/av/mesh_$TAG.obj | awk '{printf "mesh %.1f MB\n", $5/1048576}'
echo "[$(date +%H:%M:%S)] arbitrating the full-resolution official cloud"
$PY /root/mesh_filter_full.py /root/av/mesh_$TAG.obj /root/ws_gc8/official_full.ply /root/bins_$TAG $TAG 0.01 2>&1 | grep -v "^  " | tail -5
$PY /root/export_deleted.py /root/av/mesh_$TAG.obj /root/ws_gc8/official_full.ply /root/bins_$TAG ${TAG}_deleted 0.01 2>&1 | tail -4
echo "[$(date +%H:%M:%S)] DONE_$TAG"
