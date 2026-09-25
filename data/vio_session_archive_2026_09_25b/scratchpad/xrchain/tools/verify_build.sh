#!/bin/bash
# verify_build.sh <新 Runner.app> <基线 Runner.app>(基线 = any43default 台架包)
F=$1; B=$2
t=$(mktemp -d)
unsign() { cp "$1" "$2"; codesign --remove-signature "$2" 2>/dev/null; }
echo "== Info.plist 身份"
for k in CFBundleIdentifier CFBundleVersion PWXrslamBuildEngine PWXrslamEngineArm PWXrslamBenchArm PWXrslamBuildLib PWXrslamSHA256 PWXrslamThreadingEnabled PWXrslamBuildRules PWXrslamGpuFrontendLinked PWXrslamEnginePedigree; do
  printf '  %-28s base=%s new=%s\n' $k "$(/usr/libexec/PlistBuddy -c "Print :$k" $B/Info.plist 2>/dev/null)" "$(/usr/libexec/PlistBuddy -c "Print :$k" $F/Info.plist 2>/dev/null)"; done
echo "== Runner 里的引擎指纹(本臂 xrchain 必须 ≥1,其它臂 0)"
for n in "xrchain:scratchpad/xrchain/build-ios" "okvis2preint:scratchpad/preint/build-ios" "official_rules 89042cd5:scratchpad/xrofficial/build-ios" "bkpose 4853976d:scratchpad/bkpose/build-ios" "generic:opencv-official-c9ad577-b49" "gpufe/pfk:4437f552-36d8-4d91-9d8d-ae4aaadf54b6"; do
  printf '  %-26s %s\n' "${n%%:*}" "$(strings -a $F/Runner | grep -c -- "${n#*:}")"; done
echo "== Runner 符号(nm -m:引擎外推接口须是强定义,不是本包的弱兜底)"
nm -m $F/Runner | grep -E "_XRSLAMPropagateBackendState|_XRSLAMDrainBackendStates|_XRSLAMGetBackendWindowStates" | sed 's/^/  /'
for s in _pw_xrchain_begin _pw_xrchain_end _pw_xrchain_submit_photo_host _pw_xrchain_take_result_host _pw_xrchain_drain_state _pw_xrchain_close_host _pw_xrchain_stats_host _pw_xrchain_reset _pw_xrchain_poll _pw_xrchain_close _pw_camera_slot_capture_photo _pw_camera_slot_photo_result _pw_camera_slot_photo_size_candidates _pw_bench_lidar_start; do
  printf '  %-40s base=%s new=%s\n' $s "$(nm -gU $B/Runner | grep -c " $s\$")" "$(nm -gU $F/Runner | grep -c " $s\$")"; done
for k in imu_events.csv split_events_v1 imu_gyro_sample_count "timestamp_ns,sensor,x,y,z"; do
  printf '  string %-28s base=%s new=%s\n' "$k" "$(strings -a $B/Runner | grep -c -- "$k")" "$(strings -a $F/Runner | grep -c -- "$k")"; done
echo "== Dart AOT(App.framework/App)"
for k in XrReconChainPage xrchain_run_ limited_xrchain_ pw_xrchain_begin pw_xrchain_submit_photo_host PWXrslamTdExtraMs PWXrchainFinalTimeoutMs pw.bench.xr_recon_chain/1 BenchHomePage ZeroArkitCaptureProbePage BenchLidarRecordPage; do
  printf '  %-32s base=%s new=%s\n' $k "$(strings -a $B/Frameworks/App.framework/App | grep -c -- $k)" "$(strings -a $F/Frameworks/App.framework/App | grep -c -- $k)"; done
echo "== 其它嵌入二进制(对基线包去签名逐字节)"
for n in PWOfficialSfm PWDense PWOnnxRuntime PWVIOBenchKit PWXRSLAMEngine PWBasaltEngine thermion_dart Flutter; do
  unsign $B/Frameworks/$n.framework/$n $t/x; unsign $F/Frameworks/$n.framework/$n $t/y
  printf '  %-14s %s\n' $n "$(cmp -s $t/x $t/y && echo SAME || echo DIFF)"; done
echo "== Frameworks 目录"; diff <(ls $B/Frameworks) <(ls $F/Frameworks) && echo "  同一集合"
echo "== 签名"; codesign --verify --deep --strict $F 2>&1 && echo "  valid"; codesign -dv $F 2>&1 | grep -E "Identifier=|TeamIdentifier="
echo "== 主二进制 sha256"; shasum -a 256 $F/Runner $F/Frameworks/App.framework/App | sed 's#  .*/#  #'
rm -rf $t
