#!/bin/bash
# quick strict build of the library + cli: qbuild.sh <compiler> <outdir>
set -u
CXX=${1:-clang++}; B=${2:-/tmp/qb}; mkdir -p $B
cd "$(dirname "$0")/../a3d/aether_cpp"
FL="-std=c++20 -O2 -ffp-contract=off -fno-fast-math -Wall -Wextra -Werror -fno-exceptions -fno-rtti -Iinclude -Ithird_party -pthread"
rc=0
for f in src/pointcloud_lod_build/*.cpp; do $CXX $FL -c $f -o $B/$(basename $f .cpp).o || rc=1; done
$CXX $FL -c tests/pointcloud_lod_build/pwlod_build_cli.cpp -o $B/cli.o || rc=1
[ $rc = 0 ] && $CXX -pthread $B/*.o -o $B/pwlod_build_cli && echo BUILD_OK
