#!/bin/bash
set -u
cd /root/av32_build/external/aliceVision_build
make -j32 aliceVision_meshing_exe aliceVision_meshFiltering_exe > /root/av32_make8.log 2>&1
echo "MAKE8-RC=$?"
ls -la /root/av32_build/Linux-x86_64/aliceVision_meshing* /root/av32_build/Linux-x86_64/aliceVision_meshFiltering* 2>&1 | tail -4
