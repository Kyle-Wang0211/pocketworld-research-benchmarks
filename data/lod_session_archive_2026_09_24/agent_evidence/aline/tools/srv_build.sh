#!/bin/bash
# server-side strict build with g++-14: srv_build.sh
set -u
W=/root/aline_lodbuild; rm -rf $W/src && mkdir -p $W/src $W/bin && cd $W/src && tar xzf $W/src.tgz
FL="-std=c++20 -O2 -ffp-contract=off -fno-fast-math -Wall -Wextra -Werror -fno-exceptions -fno-rtti -Iinclude -Ithird_party -pthread"
rc=0
for f in src/pointcloud_lod_build/*.cpp; do g++-14 $FL -c $f -o $W/bin/$(basename $f .cpp).o || rc=1; done
g++-14 $FL -c tests/pointcloud_lod_build/pwlod_build_cli.cpp -o $W/bin/cli.o || rc=1
[ $rc = 0 ] && g++-14 -pthread $W/bin/*.o -o $W/bin/pwlod_build_cli && echo BUILD_OK
