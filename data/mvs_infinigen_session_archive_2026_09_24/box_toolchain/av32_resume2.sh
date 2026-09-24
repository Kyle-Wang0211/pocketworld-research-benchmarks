#!/bin/bash
set -u
until grep -qE "^MAKE2-RC" /root/av32_resume.out 2>/dev/null; do sleep 15; done
cd /root/av32_build && make -j32 > /root/av32_make3.log 2>&1
echo "MAKE3-RC=$?"
ls -la /root/av32_prefix/bin/aliceVision_meshing /root/av32_prefix/bin/aliceVision_meshFiltering 2>&1 | tail -3
