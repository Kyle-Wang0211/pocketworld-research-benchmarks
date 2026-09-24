#!/bin/bash
set -u
# OpenImageIO drags in the system libopencv_core, whose cblas_* refs are not satisfied by
# the reference BLAS the superbuild installed.  The system libblas does define them, so add
# it to the executable link line.  Link-only change: no algorithmic effect.
cmake -S /root/av32_src/src -B /root/av32_build/external/aliceVision_build \
      -DALICEVISION_USE_ONNX=OFF -DALICEVISION_BUILD_SEGMENTATION=OFF \
      -DALICEVISION_REQUIRE_CERES_WITH_SUITESPARSE=OFF \
      -DCMAKE_EXE_LINKER_FLAGS="/usr/lib/x86_64-linux-gnu/libblas.so" > /root/av32_av_cfg2.log 2>&1
echo "AV-CFG2-RC=$?"
cd /root/av32_build/external/aliceVision_build
make -j32 aliceVision_meshing_exe aliceVision_meshFiltering_exe > /root/av32_make9.log 2>&1
echo "MAKE9-RC=$?"
ls -la /root/av32_build/Linux-x86_64/ 2>/dev/null | grep -E "meshing|meshFiltering"
