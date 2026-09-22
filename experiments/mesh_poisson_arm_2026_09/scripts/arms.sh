#!/bin/bash
# The meshing ablation: ONE dense input ($R/filt, the officially filtered CasDiffMVS depth), two ways to turn it
# into a surface, then the SAME official Texturing node on both so the only difference is the meshing method.
set -u
R=/root/av_ep0_off; AV=/root/meshroom2023/Meshroom-2023.3.0/aliceVision
export ALICEVISION_ROOT=$AV; export LD_LIBRARY_PATH=$AV/lib
PY=/venv/main/bin/python; PYO=/root/venv_o3d_fix/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
mkdir -p $R/A_mesh $R/A_filt $R/B $R/texA $R/texB

# ---- Arm A: official Meshing + MeshFiltering (Delaunay + visibility vote + graph cut) ----
if [ ! -f $R/A.DONE ]; then
log "A/meshing: official Delaunay + graph cut"
$AV/bin/aliceVision_meshing --input $R/scene_dense.sfm --depthMapsFolder $R/filt \
  --output $R/A_mesh/densePointCloud.abc --outputMesh $R/A_mesh/mesh.obj \
  --estimateSpaceFromSfM 1 --estimateSpaceMinObservations 3 --estimateSpaceMinObservationAngle 10.0 \
  --maxInputPoints 50000000 --maxPoints 5000000 --maxPointsPerVoxel 1000000 --minStep 2 \
  --partitioning singleBlock --repartition multiResolution --angleFactor 15.0 --simFactor 15.0 --minVis 2 \
  --pixSizeMarginInitCoef 2.0 --pixSizeMarginFinalCoef 4.0 --voteMarginFactor 4.0 --contributeMarginFactor 2.0 \
  --simGaussianSizeInit 10.0 --simGaussianSize 10.0 --minAngleThreshold 1.0 --refineFuse 1 \
  --helperPointsGridSize 10 --nPixelSizeBehind 4.0 --fullWeight 1.0 \
  --voteFilteringForWeaklySupportedSurfaces 1 --addLandmarksToTheDensePointCloud 0 \
  --invertTetrahedronBasedOnNeighborsNbIterations 10 --minSolidAngleRatio 0.2 --nbSolidAngleFilteringIterations 2 \
  --colorizeOutput 0 --maxNbConnectedHelperPoints 50 --saveRawDensePointCloud 0 --exportDebugTetrahedralization 0 \
  --seed 0 --verboseLevel info > $R/A_meshing.log 2>&1
echo "  rc=$? $(grep -viE '\[trace\]' $R/A_meshing.log | grep -iE 'Final dense' | cut -c1-90)"
$AV/bin/aliceVision_meshFiltering --inputMesh $R/A_mesh/mesh.obj --outputMesh $R/A_filt/mesh.obj \
  --keepLargestMeshOnly 0 --smoothingSubset all --smoothingBoundariesNeighbours 0 --smoothingIterations 5 \
  --smoothingLambda 1.0 --filteringSubset all --filteringIterations 1 --filterLargeTrianglesFactor 60.0 \
  --filterTrianglesRatio 0.0 --verboseLevel info > $R/A_meshfilt.log 2>&1
echo "  rc=$? $(grep -i 'Output mesh' $R/A_meshfilt.log)"
touch $R/A.DONE; fi

# ---- Arm B: our TSDF on THE SAME filtered depth ----
if [ ! -f $R/B.DONE ]; then
log "B/tsdf: 3 mm TSDF + marching cubes + Open3D tutorial cleanup, from the same filtered maps"
$PYO $R/tsdf_from_filtered.py $R/scene_dense.sfm $R/filt $R/mvs_undist/images $R/B/mesh.ply 0.003 0.04 1.0 \
  > $R/B_tsdf.log 2>&1
echo "  rc=$? $(grep -E '^\[(mc|cc|fill)' $R/B_tsdf.log | tr '\n' ' ' | cut -c1-160)"
[ -s $R/B/mesh.ply ] || { echo "B FAILED"; tail -n 5 $R/B_tsdf.log; exit 1; }
$AV/bin/aliceVision_convertMesh --input $R/B/mesh.ply --output $R/B/mesh.obj --verboseLevel info > $R/B_conv.log 2>&1
echo "  convert rc=$? $(ls -la $R/B/mesh.obj 2>/dev/null | awk '{printf \"%.0f MB\", $5/1048576}')"
touch $R/B.DONE; fi

# ---- the SAME official Texturing on both ----
for A in A B; do
  [ -f $R/T$A.DONE ] && continue
  M=$([ $A = A ] && echo $R/A_filt/mesh.obj || echo $R/B/mesh.obj)
  log "$A/texturing: official Texturing node defaults"
  $AV/bin/aliceVision_texturing --input $R/scene_dense.sfm --imagesFolder $R/prep --inputMesh $M \
    --output $R/tex$A --textureSide 8192 --downscale 2 --outputMeshFileType obj --colorMappingFileType exr \
    --unwrapMethod Basic --useUDIM 1 --fillHoles 0 --padding 5 --multiBandDownscale 4 --multiBandNbContrib 1 5 10 0 \
    --useScore 1 --bestScoreThreshold 0.1 --angleHardThreshold 90.0 --workingColorSpace sRGB --outputColorSpace AUTO \
    --correctEV 1 --forceVisibleByAllVertices 0 --flipNormals 0 --visibilityRemappingMethod PullPush \
    --subdivisionTargetRatio 0.8 --verboseLevel info > $R/T${A}.log 2>&1
  echo "  rc=$? tiles=$(ls $R/tex$A/texture_*.exr 2>/dev/null | wc -l) obj=$(ls -la $R/tex$A/texturedMesh.obj 2>/dev/null | awk '{printf \"%.0f MB\", $5/1048576}')"
  touch $R/T$A.DONE
done
log "ARMS DONE"; touch $R/ARMS.DONE
