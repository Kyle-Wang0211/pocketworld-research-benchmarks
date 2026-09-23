#!/bin/bash
# build.sh — minimal host build of the SHIPPING official SfM route + A/B driver.
# Recipe = the existing host targets, verbatim flags:
#   core TUs  : build-host-fullbench/CMakeFiles/pwofficial_core.dir/flags.make
#               (= glomap_vendor/CMakeLists.txt:194-225 @7dc00642)
#   exe TUs   : build-host-fullbench/CMakeFiles/official_replay_bench_exe.dir/flags.make
#               (= glomap_vendor/CMakeLists.txt:1160-1188)
#   Metal .o  : glomap_vendor/CMakeLists.txt:1143-1149 (-D rename is load-bearing)
#   link line : build-host-fullbench/CMakeFiles/official_replay_bench_exe.dir/link.txt
# Only the official-route TUs are compiled; COLMAP/PoseLib/VLFeat objects are
# reused read-only from the prebuilt host libpwofficial_core.a (Sep 9, arm64),
# with the 14 official members removed (build/libcolmap_reuse_sep9host.a).
set -euo pipefail
B=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sfmB
S=$B/src/aether_cpp
PW=$B/src/pw_vendor_4e22ee7
TP=/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party   # read-only headers
O=$B/build/obj; mkdir -p $O

need_disk() {
  local avail_kb; avail_kb=$(df -k ~ | tail -1 | awk '{print $4}')
  if [ "$avail_kb" -lt $((5*1024*1024)) ]; then
    echo "STOP: free space $(df -h ~ | tail -1 | awk '{print $4}') < 5 GiB before '$1'" >&2; exit 90
  fi
  echo "[df ok $(df -h ~ | tail -1 | awk '{print $4}')] $1"
}

CORE_DEFS="-DAETHER_GPU_TIMESTAMPS_ENV_OFFICIAL=1 -DEIGEN_MPL2_ONLY -DGLOG_NO_ABBREVIATED_SEVERITIES -DGLOG_USE_GLOG_EXPORT -DGLOG_VERSION_MAJOR=0 -DGLOG_VERSION_MINOR=7 -DGLOMAP_CUDA_DISABLED -DVL_DISABLE_AVX -DVL_DISABLE_SSE2"
CORE_INC="-I$S/official_pipeline/include -I$S/include -I$S/third_party/glomap_vendor/colmap-src -I$S/third_party/glomap_vendor/poselib-src -I$S/third_party/glomap_vendor/stubs -I$TP/glog-install/include -I$TP/ceres/include -I$TP/ceres-build-ios/include -I$TP/ceres/config -I$TP/eigen-install/include/eigen3 -I/opt/homebrew/include"
CORE_FLAGS="-O3 -DNDEBUG -std=gnu++17 -arch arm64 -fPIC -fvisibility=hidden -fvisibility-inlines-hidden -w"

EXE_DEFS="-DAETHER_PRECLAMP_INSTR_ENV_OFFICIAL=1 -DAETHER_REPLAY_LINK_REAL_GPU_MATCH=1 -DCOLMAP_CUDA_ENABLED=0 -DEIGEN_MPL2_ONLY -DGLOG_NO_ABBREVIATED_SEVERITIES -DGLOG_USE_GLOG_EXPORT -DGLOG_VERSION_MAJOR=0 -DGLOG_VERSION_MINOR=7 -DGLOMAP_CUDA_DISABLED"
EXE_INC="-I$S/official_pipeline/include -I$S/third_party/glomap_vendor/colmap-src -I$S/third_party/glomap_vendor/poselib-src -I$S/third_party/glomap_vendor/stubs -I$S/include -I/opt/homebrew/include -I/opt/homebrew/include/eigen3 -I$TP/glog-install/include -I$TP/ceres/include -I$TP/ceres-build-ios/include -I$TP/ceres/config -I$TP/eigen-install/include/eigen3"
EXE_FLAGS="-O3 -DNDEBUG -std=gnu++17 -arch arm64 -fPIE -w"

CORE_TUS="official_aether_threaded_extract official_aether_sfm_c mandatory_arkit_gravity_v1 upright_relative_pose_v1 mandatory_gravity_tvg_v1 arkit_pose_store_v1 pair_selection_v2 pair_policy_v2_c visual_loop_index_v1 official_gpu_timestamp_writer_v1 official_gpu_timestamp_weak_stubs_v1 official_dsp_sift_c official_incremental_pipeline official_bundle_adjustment_ceres"

step=${1:-all}
if [ "$step" = all ] || [ "$step" = core ]; then
  need_disk "compile 14 official core TUs"
  for tu in $CORE_TUS; do
    extra=""; [ "$tu" = official_aether_sfm_c ] && extra="-DAETHER_COMPILE_DESCRIPTOR_RESIDENCY_V1=1"
    echo "/usr/bin/c++ $CORE_DEFS $extra $CORE_INC $CORE_FLAGS -c $S/official_pipeline/src/$tu.cc -o $O/$tu.o"
  done > $B/build/core_cmds.txt
  mkdir -p $B/build/cmds; rm -f $B/build/cmds/*.sh; i=0
  while IFS= read -r line; do i=$((i+1)); echo "$line" > $B/build/cmds/c$i.sh; done < $B/build/core_cmds.txt
  ls $B/build/cmds/*.sh | xargs -n 1 -P 6 sh
fi
if [ "$step" = all ] || [ "$step" = exe ]; then
  need_disk "compile exe-level TUs + shim + Metal matcher"
  /usr/bin/c++ $EXE_DEFS $EXE_INC $EXE_FLAGS -c $S/official_pipeline/src/official_preclamp_instr_v1.cc -o $O/official_preclamp_instr_v1.o &
  /usr/bin/c++ $EXE_DEFS $EXE_INC $EXE_FLAGS -c $S/src/crypto/sha256.cpp -o $O/sha256.o &
  /usr/bin/c++ $EXE_DEFS $EXE_INC $EXE_FLAGS -c $S/third_party/glomap_vendor/bench/host_gpu_extract_warmup_stub.cc -o $O/host_gpu_extract_warmup_stub.o &
  /usr/bin/cc -O3 -DNDEBUG -arch arm64 -fPIC -w -I$PW/include -c $PW/src/pwofficial_export_shim.c -o $O/pwofficial_export_shim.o &
  /usr/bin/c++ -std=c++17 -fobjc-arc -O3 -I$S/include -Daether_gpu_match_set_preview_fps30=aether_gpu_match_set_preview_fps30_hostimpl -c $PW/src/pwofficial_gpu_match.mm -o $O/pwofficial_gpu_match_host.o &
  /usr/bin/c++ $EXE_DEFS -I$PW/include $EXE_INC $EXE_FLAGS -c $B/driver/pwofficial_pose_ab_driver.cc -o $O/pwofficial_pose_ab_driver.o &
  wait
fi
if [ "$step" = all ] || [ "$step" = link ]; then
  need_disk "link"
  /usr/bin/c++ -O3 -DNDEBUG -arch arm64 -Wl,-search_paths_first -Wl,-headerpad_max_install_names \
    $O/pwofficial_pose_ab_driver.o $O/official_preclamp_instr_v1.o $O/sha256.o \
    $O/host_gpu_extract_warmup_stub.o $O/pwofficial_export_shim.o \
    $(for tu in $CORE_TUS; do printf '%s ' $O/$tu.o; done) \
    $O/pwofficial_gpu_match_host.o $B/build/libcolmap_reuse_sep9host.a \
    -framework Metal -framework Foundation /opt/homebrew/lib/libceres.dylib /opt/homebrew/lib/libglog.dylib -lsqlite3 \
    -o $B/build/pwofficial_pose_ab_driver
  ls -la $B/build/pwofficial_pose_ab_driver
fi
