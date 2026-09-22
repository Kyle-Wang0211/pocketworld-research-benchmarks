#!/bin/bash
# 重贴 arm C: 网格已用 Sim3 搬进官方 SfM 帧 (旧的 texC/texC2 是帧错配下贴的, 7.03M 三角产生 7.03M chart = 全废)
set -u
R=/root/av_ep0_off; AV=/root/meshroom2023/Meshroom-2023.3.0/aliceVision
export ALICEVISION_ROOT=$AV; export LD_LIBRARY_PATH=$AV/lib
mkdir -p $R/texC3
$AV/bin/aliceVision_texturing --input $R/scene_dense.sfm --imagesFolder $R/prep \
  --inputMesh $R/C_filt/mesh_aligned.obj --output $R/texC3 \
  --textureSide 8192 --downscale 2 --outputMeshFileType obj --colorMappingFileType exr \
  --unwrapMethod Basic --useUDIM 1 --fillHoles 0 --padding 5 --multiBandDownscale 4 --multiBandNbContrib 1 5 10 0 \
  --useScore 1 --bestScoreThreshold 0.1 --angleHardThreshold 90.0 --workingColorSpace sRGB --outputColorSpace AUTO \
  --correctEV 1 --forceVisibleByAllVertices 0 --flipNormals 0 --visibilityRemappingMethod PullPush \
  --subdivisionTargetRatio 0.8 --verboseLevel info > $R/TC3.log 2>&1
echo "rc=$?  $(grep -oE "Packing texture charts \([0-9]+" $R/TC3.log|head -1) -> $(grep -oE "Finalize packed charts \([0-9]+" $R/TC3.log|head -1)  atlases=$(grep -oE "nbAtlas: [0-9]+" $R/TC3.log|head -1)"
touch $R/C3.DONE
