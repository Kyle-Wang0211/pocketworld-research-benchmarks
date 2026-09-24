#!/bin/bash
# Two meshing arms that differ from the /root/av_ep0_off baseline in ONE thing: the simMap values
# that aliceVision_meshing reads.  Same depthMapFiltered, same nmodMap, same meshing flags as
# /root/av_ep0_off/arms.sh lines 10-32.  Run sequentially (meshing peaks ~22 GB).
set -u
B=/root/av_simfix
AV=/root/meshroom2023/Meshroom-2023.3.0/aliceVision
export ALICEVISION_ROOT=$AV; export LD_LIBRARY_PATH=$AV/lib
PY=/venv/main/bin/python
mesh_one () {
  A=$1
  mkdir -p $B/$A/mesh $B/$A/filtmesh
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
  echo "[$A] meshing rc=$? $(grep -iE 'Final dense|points loaded and filtered' $B/$A.meshing.log | tail -2 | tr '\n' ' ')"
  $AV/bin/aliceVision_meshFiltering --inputMesh $B/$A/mesh/mesh.obj --outputMesh $B/$A/filtmesh/mesh.obj \
    --keepLargestMeshOnly 0 --smoothingSubset all --smoothingBoundariesNeighbours 0 --smoothingIterations 5 \
    --smoothingLambda 1.0 --filteringSubset all --filteringIterations 1 --filterLargeTrianglesFactor 60.0 \
    --filterTrianglesRatio 0.0 --verboseLevel info > $B/$A.meshfilt.log 2>&1
  echo "[$A] meshFiltering rc=$?"
}
for A in nc s1; do
  echo "=== build $A ==="; $PY /root/mk_simarm.py $B/$A/filt $A
  echo "=== mesh $A ==="; date +%H:%M:%S; mesh_one $A; date +%H:%M:%S
done
echo "=== PRISTINE re-run (second noise sample of the untouched baseline) ==="
mkdir -p $B/pristine; ln -sfn /root/av_ep0_off/filt $B/pristine/filt 2>/dev/null
date +%H:%M:%S; mesh_one pristine; date +%H:%M:%S
echo ALLDONE
