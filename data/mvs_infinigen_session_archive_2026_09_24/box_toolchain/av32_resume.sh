#!/bin/bash
set -u
# gcc-13 needs <cstdint> that old vendored code (assimp/contrib/draco) does not include.
# Inject it as a compile flag instead of editing vendored sources.
export CXXFLAGS="-include cstdint"
export CFLAGS="${CFLAGS:-}"
cmake -S /root/av32_build/assimp -B /root/av32_build/assimp_build \
      -DCMAKE_CXX_FLAGS="-include cstdint" > /root/av32_assimp_cfg.log 2>&1
echo "ASSIMP-CFG-RC=$?"
cd /root/av32_build && make -j32 > /root/av32_make2.log 2>&1
echo "MAKE2-RC=$?"
ls -la /root/av32_prefix/bin/aliceVision_meshing /root/av32_prefix/bin/aliceVision_meshFiltering 2>&1 | tail -3
