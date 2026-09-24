#!/bin/bash
# The official Meshroom photogrammetry pipeline, run by Meshroom itself. No parameters are written by us:
# meshroom_batch loads lib/meshroom/pipelines/photogrammetry.mg and executes every node with its own defaults.
# Input = the 132 original 4032x3024 photos. Everything (SfM at full resolution, DepthMap, DepthMapFilter,
# Meshing, MeshFiltering, Texturing) is Meshroom's own.
set -u
M=/root/meshroom2023/Meshroom-2023.3.0
export ALICEVISION_ROOT=$M/aliceVision
export LD_LIBRARY_PATH=$ALICEVISION_ROOT/lib
export ALICEVISION_SENSOR_DB=$ALICEVISION_ROOT/share/aliceVision/cameraSensors.db
export ALICEVISION_VOCTREE=$ALICEVISION_ROOT/share/aliceVision/vlfeat_K80L3.SIFT.tree
cd /root
$M/meshroom_batch --input /root/mvs_P16k/images --pipeline photogrammetry \
  --output /root/mr_official/out --cache /root/mr_official/cache --save /root/mr_official/project.mg -v info
echo "meshroom_batch rc=$?"
