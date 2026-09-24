#!/bin/bash
# One weakly-supported-surface ablation arm.
# Command line copied verbatim from /root/av_ep0_off/arms.sh lines 13-32 (baseline arm A);
# the ONLY difference between arms is the AV_* environment override.
set -u
R=/root/av_ep0_off
W=/root/p4
AV=$PW_AV_BIN
[ -n "${PW_AV_ROOT:-}" ] && export ALICEVISION_ROOT=$PW_AV_ROOT
export LD_LIBRARY_PATH=$PW_AV_LIB
N=$1
mkdir -p $W/${N}_mesh $W/${N}_filt
echo "[$(date +%H:%M:%S)] $N meshing K_REL=${AV_K_REL:-def} K_ABS=${AV_K_ABS:-def} K_OUTL=${AV_K_OUTL:-def} NJ=${AV_NSIGMA_JUMP:-def} NF=${AV_NSIGMA_FRONT:-def} NB=${AV_NSIGMA_BACK:-def}"
$AV/aliceVision_meshing --input $R/scene_dense.sfm --depthMapsFolder $R/filt \
  --output $W/${N}_mesh/densePointCloud.abc --outputMesh $W/${N}_mesh/mesh.obj \
  --estimateSpaceFromSfM 1 --estimateSpaceMinObservations 3 --estimateSpaceMinObservationAngle 10.0 \
  --maxInputPoints 50000000 --maxPoints 5000000 --maxPointsPerVoxel 1000000 --minStep 2 \
  --partitioning singleBlock --repartition multiResolution --angleFactor 15.0 --simFactor 15.0 --minVis 2 \
  --pixSizeMarginInitCoef 2.0 --pixSizeMarginFinalCoef 4.0 --voteMarginFactor 4.0 --contributeMarginFactor 2.0 \
  --simGaussianSizeInit 10.0 --simGaussianSize 10.0 --minAngleThreshold 1.0 --refineFuse 1 \
  --helperPointsGridSize 10 --nPixelSizeBehind 4.0 --fullWeight 1.0 \
  --voteFilteringForWeaklySupportedSurfaces 1 --addLandmarksToTheDensePointCloud 0 \
  --invertTetrahedronBasedOnNeighborsNbIterations 10 --minSolidAngleRatio 0.2 --nbSolidAngleFilteringIterations 2 \
  --colorizeOutput 0 --maxNbConnectedHelperPoints 50 --saveRawDensePointCloud 0 --exportDebugTetrahedralization 0 \
  --seed 0 --verboseLevel info > $W/${N}_meshing.log 2>&1
rc=$?; echo "  meshing rc=$rc  $(grep -i "PW-ABLATION" $W/${N}_meshing.log | tr "\n" " " | cut -c1-140)"
[ $rc -ne 0 ] && { tail -5 $W/${N}_meshing.log; exit 1; }
$AV/aliceVision_meshFiltering --inputMesh $W/${N}_mesh/mesh.obj --outputMesh $W/${N}_filt/mesh.obj \
  --keepLargestMeshOnly 0 --smoothingSubset all --smoothingBoundariesNeighbours 0 --smoothingIterations 5 \
  --smoothingLambda 1.0 --filteringSubset all --filteringIterations 1 --filterLargeTrianglesFactor 60.0 \
  --filterTrianglesRatio 0.0 --verboseLevel info > $W/${N}_meshfilt.log 2>&1
echo "  meshFiltering rc=$?"
/venv/main/bin/python /root/layer2.py $W/${N}_filt/mesh.obj "$N" --objframe 2>/dev/null | tee -a $W/RESULTS.txt
md5sum $W/${N}_filt/mesh.obj >> $W/MD5.txt
rm -f $W/${N}_mesh/densePointCloud.abc
echo "ARM-DONE $N"
