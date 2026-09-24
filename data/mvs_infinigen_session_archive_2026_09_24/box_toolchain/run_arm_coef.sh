#!/bin/bash
# [PW-GRAZING] one meshing arm. Command line copied verbatim from /root/av_ep0_off/arms.sh
# lines 14-32 (arm A); the ONLY things that change between arms are the binary and the
# extra flags passed as $3+.
#   usage: run_arm.sh <arm-name> <meshing-binary> [extra flags...]
set -u
ARM=$1; BIN=$2; shift 2
R=/root/av_ep0_off
O=/root/graz/$ARM
BINDIR=$(dirname "$BIN")
export LD_LIBRARY_PATH="$BINDIR":/root/oiio_inst/lib:/root/av_deps/lib:/root/lz4_inst/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
mkdir -p "$O"

echo "[$(date +%H:%M:%S)] $ARM meshing: extra='$*'"
/usr/bin/time -v "$BIN" --input $R/scene_dense.sfm --depthMapsFolder $R/filt \
  --output $O/densePointCloud.abc --outputMesh $O/mesh.obj \
  --estimateSpaceFromSfM 1 --estimateSpaceMinObservations 3 --estimateSpaceMinObservationAngle 10.0 \
  --maxInputPoints 50000000 --maxPoints 5000000 --maxPointsPerVoxel 1000000 --minStep 2 \
  --partitioning singleBlock --repartition multiResolution --angleFactor 15.0 --simFactor 15.0 --minVis 2 \
  --pixSizeMarginInitCoef 2.0 --pixSizeMarginFinalCoef $PWCOEF --voteMarginFactor 4.0 --contributeMarginFactor 2.0 \
  --simGaussianSizeInit 10.0 --simGaussianSize 10.0 --minAngleThreshold 1.0 --refineFuse 1 \
  --helperPointsGridSize 10 --nPixelSizeBehind 4.0 --fullWeight 1.0 \
  --voteFilteringForWeaklySupportedSurfaces 1 --addLandmarksToTheDensePointCloud 0 \
  --invertTetrahedronBasedOnNeighborsNbIterations 10 --minSolidAngleRatio 0.2 --nbSolidAngleFilteringIterations 2 \
  --colorizeOutput 0 --maxNbConnectedHelperPoints 50 --saveRawDensePointCloud 0 --exportDebugTetrahedralization 0 \
  --seed 0 --verboseLevel info "$@" > $O/meshing.log 2>&1
RC=$?
echo "  meshing rc=$RC  $(grep -iE 'Final dense point cloud' $O/meshing.log | tail -1 | cut -c1-70)"
grep -E '\[PW-GRAZING\]' $O/meshing.log | sed 's/^/    /'
grep -E 'Maximum resident set size|Elapsed \(wall' $O/meshing.log | sed 's/^/    /'
[ -s $O/mesh.obj ] || { echo "  !! no mesh, abort"; tail -5 $O/meshing.log; exit 1; }

# same official MeshFiltering as arms.sh lines 28-32
"$BINDIR/aliceVision_meshFiltering" --inputMesh $O/mesh.obj --outputMesh $O/filt_mesh.obj \
  --keepLargestMeshOnly 0 --smoothingSubset all --smoothingBoundariesNeighbours 0 --smoothingIterations 5 \
  --smoothingLambda 1.0 --filteringSubset all --filteringIterations 1 --filterLargeTrianglesFactor 60.0 \
  --filterTrianglesRatio 0.0 --verboseLevel info > $O/meshfilt.log 2>&1
echo "  meshFiltering rc=$?"

echo "  md5 raw : $(md5sum $O/mesh.obj | cut -d' ' -f1)"
echo "  md5 filt: $(md5sum $O/filt_mesh.obj 2>/dev/null | cut -d' ' -f1)"
# THE ruler (/root/layer2.py), the only one
/venv/main/bin/python /root/layer2.py $O/mesh.obj      "${ARM}_raw"  --objframe
/venv/main/bin/python /root/layer2.py $O/filt_mesh.obj "${ARM}_filt" --objframe
echo "[$(date +%H:%M:%S)] $ARM done"
