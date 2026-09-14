#!/usr/bin/env bash
# FULL AliceVision replication (the RealityScan lineage end to end): THEIR depth maps (PatchMatch/SGM, classical
# photometric — no learned cost-volume regularisation) -> THEIR filtering -> THEIR fuseCut meshing, on OUR 132
# images and OUR COLMAP poses. Deliverable is AliceVision's own dense point cloud, so nothing of ours is mixed in.
#   run_av_full.sh <tag> [downscale]
set -uo pipefail
TAG=${1:?tag}; DS=${2:-1}
export ALICEVISION_ROOT=/root/meshroom/aliceVision; export LD_LIBRARY_PATH=$ALICEVISION_ROOT/lib
A=$ALICEVISION_ROOT/bin; O=/root/avfull_$TAG; mkdir -p $O/depth $O/filt
echo "[$(date +%H:%M:%S)] depthMapEstimation (downscale $DS)"
$A/aliceVision_depthMapEstimation --input /root/av/sfm_poses_pp.sfm --imagesFolder /root/av/images_by_viewid \
  --output $O/depth --downscale $DS --maxTCams 10 > $O/depth.log 2>&1
echo "  rc=$? maps=$(ls $O/depth/*_depthMap.exr 2>/dev/null | wc -l)"
grep -viE "\[trace\]" $O/depth.log | tail -3 | cut -c1-140
[ "$(ls $O/depth/*_depthMap.exr 2>/dev/null | wc -l)" -gt 0 ] || { echo AV_DEPTH_FAILED; exit 1; }
echo "[$(date +%H:%M:%S)] depthMapFiltering"
$A/aliceVision_depthMapFiltering --input /root/av/sfm_poses_pp.sfm --depthMapsFolder $O/depth --output $O/filt > $O/filt.log 2>&1
echo "  rc=$? maps=$(ls $O/filt/*_depthMap.exr 2>/dev/null | wc -l)"
echo "[$(date +%H:%M:%S)] fuseCut meshing"
$A/aliceVision_meshing --input /root/av/sfm_poses_pp.sfm --depthMapsFolder $O/filt \
  --output $O/dense.abc --outputMesh $O/mesh.obj \
  --maxInputPoints 50000000 --maxPoints 50000000 --maxPointsPerVoxel 50000000 \
  --minStep 1 --pixSizeMarginInitCoef 1 --pixSizeMarginFinalCoef 0.5 \
  --helperPointsGridSize 10 --colorizeOutput 1 --saveRawDensePointCloud 0 > $O/mesh.log 2>&1
echo "  rc=$?"
grep -viE "\[trace\]" $O/mesh.log | grep -iE "points loaded|Task done|OUTPUT" | tail -3 | cut -c1-130
[ -s $O/mesh.obj ] || { echo AV_MESH_FAILED; exit 1; }
echo "[$(date +%H:%M:%S)] AliceVision's own dense cloud -> viewer bins (their result, unmodified)"
/venv/main/bin/python /root/av_dense_to_bins.py $O/mesh.obj $O/filt /root/av/sfm_poses_pp.sfm /root/bins_$TAG $TAG
echo "[$(date +%H:%M:%S)] DONE_$TAG"
