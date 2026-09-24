#!/bin/bash
set -u
# ceres pins a Dec-2022 commit whose SuiteSparseQR call does not match the
# SuiteSparse built here (int64 index change).  Ceres is only used by AliceVision
# bundle adjustment, not by meshing / meshFiltering, so build it without SuiteSparse.
cmake -S /root/av32_build/ceres-solver -B /root/av32_build/external/ceres_build \
      -DSUITESPARSE:BOOL=OFF -DCXSPARSE:BOOL=OFF > /root/av32_ceres_cfg.log 2>&1
echo "CERES-CFG-RC=$?"
cd /root/av32_build && make -j32 > /root/av32_make4.log 2>&1
echo "MAKE4-RC=$?"
ls -la /root/av32_prefix/bin/aliceVision_meshing /root/av32_prefix/bin/aliceVision_meshFiltering 2>&1 | tail -3
