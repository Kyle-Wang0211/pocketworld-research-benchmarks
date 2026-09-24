#!/bin/bash
# mac run: mrun.sh <tag> [cli options]   -> $SP/run/<tag>, prints time + peak RSS
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/cb65ad40-6d75-486f-b32e-36830fe130aa/scratchpad/aline
PLY=${PLY:-/Users/kaidongwang/Developer/pw_clouds_20260923/pc_t3_ep0_36M.ply}
TAG=$1; shift
rm -rf $SP/run/$TAG $SP/run/${TAG}_chunks
/usr/bin/time -l $SP/cmk/pointcloud_lod_build_cli $PLY $SP/run/$TAG --chunkdir $SP/run/${TAG}_chunks "$@" 2> $SP/run/$TAG.time
echo "$TAG: $(grep -E 'real' $SP/run/$TAG.time | awk '{print $1"s wall"}') peakRSS=$(grep 'maximum resident' $SP/run/$TAG.time | awk '{printf "%.0f MB", $1/1048576}') footprint=$(grep 'peak memory footprint' $SP/run/$TAG.time | awk '{printf "%.0f MB", $1/1048576}')"
