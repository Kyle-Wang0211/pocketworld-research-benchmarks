#!/bin/bash
# Arm C: Poisson on the ep0 dense cloud -> official meshFiltering -> official Texturing, same node, same params.
set -u
R=/root/av_ep0_off; AV=/root/meshroom2023/Meshroom-2023.3.0/aliceVision
export ALICEVISION_ROOT=$AV; export LD_LIBRARY_PATH=$AV/lib
log(){ echo "[$(date +%H:%M:%S)] $*"; }
mkdir -p $R/C_filt $R/texC
log "C/convert: poisson ply -> obj"
$AV/bin/aliceVision_convertMesh --input $R/C/poisson.ply --output $R/C/poisson.obj --verboseLevel info > $R/C_conv.log 2>&1
echo "  rc=$?"
log "C/meshFiltering: official defaults"
$AV/bin/aliceVision_meshFiltering --inputMesh $R/C/poisson.obj --outputMesh $R/C_filt/mesh.obj \
  --keepLargestMeshOnly 0 --smoothingSubset all --smoothingBoundariesNeighbours 0 --smoothingIterations 5 \
  --smoothingLambda 1.0 --filteringSubset all --filteringIterations 1 --filterLargeTrianglesFactor 60.0 \
  --filterTrianglesRatio 0.0 --verboseLevel info > $R/C_meshfilt.log 2>&1
echo "  rc=$? complex-edge=$(grep -c 'complex edge' $R/C_meshfilt.log) $(grep -i 'Output mesh' $R/C_meshfilt.log)"
log "C/texturing: same official node"
$AV/bin/aliceVision_texturing --input $R/scene_dense.sfm --imagesFolder $R/prep --inputMesh $R/C_filt/mesh.obj \
  --output $R/texC --textureSide 8192 --downscale 2 --outputMeshFileType obj --colorMappingFileType exr \
  --unwrapMethod Basic --useUDIM 1 --fillHoles 0 --padding 5 --multiBandDownscale 4 --multiBandNbContrib 1 5 10 0 \
  --useScore 1 --bestScoreThreshold 0.1 --angleHardThreshold 90.0 --workingColorSpace sRGB --outputColorSpace AUTO \
  --correctEV 1 --forceVisibleByAllVertices 0 --flipNormals 0 --visibilityRemappingMethod PullPush \
  --subdivisionTargetRatio 0.8 --verboseLevel info > $R/TC.log 2>&1
echo "  rc=$? charts=$(grep -oE 'Finalize packed charts \([0-9]+' $R/TC.log | grep -oE '[0-9]+') tiles=$(ls $R/texC/texture_*.exr 2>/dev/null | wc -l)"
log "C DONE"; touch $R/C.DONE
