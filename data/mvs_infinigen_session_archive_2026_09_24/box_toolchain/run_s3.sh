#!/bin/bash
# Third dose of the same single variable: how far the sim map's range reaches into the "bad" half.
#   nc  sim in [-1, 0]   (what we ship:  sim = -conf)
#   s1  sim in [-1,+1]   (the range the PointCloud.cpp comment documents: sim = 1-2*conf)
#   s3  sim in [-1,+3]   (calibrated to the official estimator's own output: AliceVision writes
#                         sim = depthEnergy/20 in low-colour-variance areas, energy in [0,180] deg,
#                         so official white-wall sim is typically +1..+3)
set -u
while ! grep -q ALLDONE /root/av_simfix/driver.log; do sleep 30; done
B=/root/av_simfix
AV=/root/meshroom2023/Meshroom-2023.3.0/aliceVision
export ALICEVISION_ROOT=$AV; export LD_LIBRARY_PATH=$AV/lib
A=s3
/venv/main/bin/python /root/mk_simarm.py $B/$A/filt $A
mkdir -p $B/$A/mesh $B/$A/filtmesh
date +%H:%M:%S
$AV/bin/aliceVision_meshing --input /root/av_ep0_off/scene_dense.sfm --depthMapsFolder $B/$A/filt \
  --output $B/$A/mesh/densePointCloud.abc --outputMesh $B/$A/mesh/mesh.obj \
  --estimateSpaceFromSfM 1 --estimateSpaceMinObservations 3 --estimateSpaceMinObservationAngle 10.0 \
  --maxInputPoints 50000000 --maxPoints 5000000 --maxPointsPerVoxel 1000000 --minStep 2 \
  --partitioning singleBlock --repartition multiResolution --angleFactor 15.0 --simFactor 15.0 --minVis 2 \
  --pixSizeMarginInitCoef 2.0 --pixSizeMarginFinalCoef 4.0 --voteMarginFactor 4.0 --contributeMarginFactor 2.0 \
  --simGaussianSizeInit 10.0 --simGaussianSize 10.0 --minAngleThreshold 1.0 --refineFuse 1 \
  --helperPointsGridSize 10 --nPixelSizeBehind 4.0 --fullWeight 1.0 \
  --voteFilteringForWeaklySupportedSurfaces 1 --addLandmarksToTheDensePointCloud 0 \
  --invertTetrahedronBasedOnNeighborsNbIterations 10 --minSolidAngleRatio 0.2 --nbSolidAngleFilteringIterations 2 \
  --colorizeOutput 0 --maxNbConnectedHelperPoints 50 --saveRawDensePointCloud 0 --exportDebugTetrahedralization 0 \
  --seed 0 --verboseLevel info > $B/$A.meshing.log 2>&1
echo "[$A] meshing rc=$?"
$AV/bin/aliceVision_meshFiltering --inputMesh $B/$A/mesh/mesh.obj --outputMesh $B/$A/filtmesh/mesh.obj \
  --keepLargestMeshOnly 0 --smoothingSubset all --smoothingBoundariesNeighbours 0 --smoothingIterations 5 \
  --smoothingLambda 1.0 --filteringSubset all --filteringIterations 1 --filterLargeTrianglesFactor 60.0 \
  --filterTrianglesRatio 0.0 --verboseLevel info > $B/$A.meshfilt.log 2>&1
echo "[$A] meshFiltering rc=$?"; date +%H:%M:%S; echo S3DONE
