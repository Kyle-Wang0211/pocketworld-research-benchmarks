#!/usr/bin/env bash
# AliceVision fuseCut (Jancosek/Pajdla weakly-supported-surface graph cut = the RealityScan lineage), fed with the
# official CasDiffMVS fusion + our per-point visibility, via the official importMiddlebury SfMData.
#   run_fusecut.sh <ws_dir> <tag> [max_points]
set -uo pipefail
WS=${1:?ws}; TAG=${2:?tag}; MAXP=${3:-0}
export ALICEVISION_ROOT=/root/meshroom/aliceVision; export LD_LIBRARY_PATH=$ALICEVISION_ROOT/lib
PY=/venv/main/bin/python; A=$ALICEVISION_ROOT/bin
mkdir -p /root/av
echo "[$(date +%H:%M:%S)] structure export"
$PY /root/add_structure.py /root/av/sfm_poses.sfm $WS /root/av/sfm_$TAG.sfm $MAXP 2>&1 | tail -2
echo "[$(date +%H:%M:%S)] fuseCut meshing"
$A/aliceVision_meshing --input /root/av/sfm_$TAG.sfm --output /root/av/dense_$TAG.abc --outputMesh /root/av/mesh_$TAG.obj \
  --helperPointsGridSize 10 --maxInputPoints 50000000 --maxPoints 50000000 --maxPointsPerVoxel 50000000 \
  --addLandmarksToTheDensePointCloud 1 --colorizeOutput 1 > /root/av/mesh_$TAG.log 2>&1
rc=$?; echo "meshing rc=$rc"
grep -viE "\[trace\]" /root/av/mesh_$TAG.log | tail -6 | cut -c1-140
[ -s /root/av/mesh_$TAG.obj ] || { echo AV_MESH_FAILED; exit 1; }
echo "[$(date +%H:%M:%S)] filtering the full-resolution official cloud with the fuseCut mesh"
$PY /root/mesh_filter_full.py /root/av/mesh_$TAG.obj $WS/official_full.ply /root/bins_$TAG $TAG 0.01 2>&1 | grep -v "^  " | tail -5
$PY /root/export_deleted.py /root/av/mesh_$TAG.obj $WS/official_full.ply /root/bins_$TAG ${TAG}_deleted 0.01 2>&1 | tail -4
echo "[$(date +%H:%M:%S)] DONE_$TAG"
