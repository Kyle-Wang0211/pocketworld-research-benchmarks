#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
export DEBIAN_FRONTEND=noninteractive
LOG "装 OpenCV / Boost"
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq libopencv-dev libboost-all-dev >/dev/null 2>&1
LOG "  OpenCV $(pkg-config --modversion opencv4 2>/dev/null)  Boost $(grep -m1 BOOST_LIB_VERSION /usr/include/boost/version.hpp 2>/dev/null | awk "{print \$3}")"
cd /root/APDe-MVS
LOG "cmake 配置"
cmake -B build -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
LOG "编译"
cmake --build build --target APD -j 8 2>&1 | tail -15
LOG "产物: $(ls -la /root/APDe-MVS/build/APD 2>/dev/null || echo 🔴 未生成)"
touch /root/APDE_BUILD_DONE
