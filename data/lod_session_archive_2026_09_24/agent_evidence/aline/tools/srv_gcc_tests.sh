#!/bin/bash
# GCC 14, repo strict flags, library + reader + tests; then run them on the fixture.
set -u
W=/root/aline_lodbuild; S=$W/src_full; rm -rf $S $W/gcc && mkdir -p $S $W/gcc && cd $S && tar xzf $W/src_full.tgz 2>/dev/null
FL="-std=c++20 -O2 -ffp-contract=off -fno-fast-math -Wall -Wextra -Werror -fno-exceptions -fno-rtti -Iinclude -Ithird_party -pthread"
rc=0; n=0
for f in src/pointcloud_lod/*.cpp src/pointcloud_lod_build/*.cpp; do g++-14 $FL -c $f -o $W/gcc/lib_$(basename $f .cpp).o 2>> $W/gcc/warnings.txt || rc=1; n=$((n+1)); done
for t in tests/pointcloud_lod_build/test_build.cpp tests/pointcloud_lod_build/pwlod_build_cli.cpp tests/pointcloud_lod/test_octree.cpp tests/pointcloud_lod/test_select.cpp tests/pointcloud_lod/test_stream.cpp; do
  g++-14 $FL $t $W/gcc/lib_*.o -o $W/gcc/$(basename $t .cpp) 2>> $W/gcc/warnings.txt || rc=1; n=$((n+1)); done
echo "g++-14 translation units: $n, rc=$rc, diagnostics lines: $(wc -l < $W/gcc/warnings.txt)"
g++-14 --version | head -1
[ $rc = 0 ] || exit 1
$W/gcc/test_build tests/pointcloud_lod/fixture $W/gcc/tb_out | grep -E "PASS|FAIL|SKIP|===="
for t in octree select stream; do echo "-- reader test_$t on the port's output:"; $W/gcc/test_$t $W/gcc/tb_out/ply | grep -E "FAIL|====" ; done
