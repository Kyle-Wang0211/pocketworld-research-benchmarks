#!/bin/bash
# Arm D: arm A 逐字复制, 唯一变量 --voteFilteringForWeaklySupportedSurfaces 1 -> 0
# 问的问题: 点云空着的地方, 成网能不能就空着? WSS 就是把空洞铺成大三角的那个机制。
set -u
R=/root/av_ep0_off; AV=/root/meshroom2023/Meshroom-2023.3.0/aliceVision
export ALICEVISION_ROOT=$AV; export LD_LIBRARY_PATH=$AV/lib
log(){ echo "[$(date +%H:%M:%S)] $*"; }
mkdir -p $R/D_mesh $R/D_filt $R/texD
log "D/meshing: 同 A, 只关 WSS"
$AV/bin/aliceVision_meshing --input $R/scene_dense.sfm --depthMapsFolder $R/filt \
  --output $R/D_mesh/densePointCloud.abc --outputMesh $R/D_mesh/mesh.obj \
  --estimateSpaceFromSfM 1 --estimateSpaceMinObservations 3 --estimateSpaceMinObservationAngle 10.0 \
  --maxInputPoints 50000000 --maxPoints 5000000 --maxPointsPerVoxel 1000000 --minStep 2 \
  --partitioning singleBlock --repartition multiResolution --angleFactor 15.0 --simFactor 15.0 --minVis 2 \
  --pixSizeMarginInitCoef 2.0 --pixSizeMarginFinalCoef 4.0 --voteMarginFactor 4.0 --contributeMarginFactor 2.0 \
  --simGaussianSizeInit 10.0 --simGaussianSize 10.0 --minAngleThreshold 1.0 --refineFuse 1 \
  --helperPointsGridSize 10 --nPixelSizeBehind 4.0 --fullWeight 1.0 \
  --voteFilteringForWeaklySupportedSurfaces 0 --addLandmarksToTheDensePointCloud 0 \
  --invertTetrahedronBasedOnNeighborsNbIterations 10 --minSolidAngleRatio 0.2 --nbSolidAngleFilteringIterations 2 \
  --colorizeOutput 0 --maxNbConnectedHelperPoints 50 --saveRawDensePointCloud 0 --exportDebugTetrahedralization 0 \
  --seed 0 --verboseLevel info > $R/D_meshing.log 2>&1
echo "  rc=$? $(grep -viE "\[trace\]" $R/D_meshing.log | grep -iE "Final dense" | cut -c1-90)"
log "D/meshFiltering: 官方默认"
$AV/bin/aliceVision_meshFiltering --inputMesh $R/D_mesh/mesh.obj --outputMesh $R/D_filt/mesh.obj \
  --keepLargestMeshOnly 0 --smoothingSubset all --smoothingBoundariesNeighbours 0 --smoothingIterations 5 \
  --smoothingLambda 1.0 --filteringSubset all --filteringIterations 1 --filterLargeTrianglesFactor 60.0 \
  --filterTrianglesRatio 0.0 --verboseLevel info > $R/D_meshfilt.log 2>&1
echo "  rc=$? $(grep -i "Output mesh" $R/D_meshfilt.log)"
log "D/texturing: 官方默认"
$AV/bin/aliceVision_texturing --input $R/scene_dense.sfm --imagesFolder $R/prep --inputMesh $R/D_filt/mesh.obj \
  --output $R/texD --textureSide 8192 --downscale 2 --outputMeshFileType obj --colorMappingFileType exr \
  --unwrapMethod Basic --useUDIM 1 --fillHoles 0 --padding 5 --multiBandDownscale 4 --multiBandNbContrib 1 5 10 0 \
  --useScore 1 --bestScoreThreshold 0.1 --angleHardThreshold 90.0 --workingColorSpace sRGB --outputColorSpace AUTO \
  --correctEV 1 --forceVisibleByAllVertices 0 --flipNormals 0 --visibilityRemappingMethod PullPush \
  --subdivisionTargetRatio 0.8 --verboseLevel info > $R/TD.log 2>&1
echo "  rc=$?  charts=$(grep -oE "Packing texture charts \([0-9]+" $R/TD.log | head -1)  ->  $(grep -oE "Finalize packed charts \([0-9]+" $R/TD.log | head -1)"
log "D DONE"; touch $R/D.DONE
