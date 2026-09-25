#!/usr/bin/env bash
# verify_expmid.sh <Runner.app> [linkmap] — read-only checks of the rec30 arloopbench package.
set -uo pipefail
A="$1"; MAP="${2:-}"
PREV=/Users/kaidongwang/Developer/arloopbench_builds/unified_official_xrslam_rec30_20260924/Runner.app
t=$(mktemp -d)
unsign() { cp "$1" "$2"; codesign --remove-signature "$2" 2>/dev/null; }
text() { segedit "$1" -extract __TEXT __text /dev/stdout 2>/dev/null | shasum -a 256 | cut -c1-16; }
echo "== main binaries"
shasum -a 256 "$A/Runner" "$A/Frameworks/App.framework/App" | sed "s|$A/||"
echo "== Info.plist identity"
for k in CFBundleIdentifier CFBundleVersion PWXrslamBuildEngine PWXrslamEngineArm PWXrslamBuildLib PWXrslamSHA256 PWXrslamThreadingEnabled PWXrslamBuildRules PWXrslamGpuFrontendLinked PWXrslamEnginePedigree; do
  printf '  %-28s %s\n' "$k" "$(/usr/libexec/PlistBuddy -c "Print :$k" "$A/Info.plist" 2>&1)"; done
echo "== linked engine fingerprint in Runner (official_rules must be 1, others 0)"
strings -a "$A/Runner" > $t/run.txt
FP_O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xrofficial/build-ios/_deps/depends-opencv-build/opencv2.framework/Headers/core/mat.inl.hpp
FP_G=/private/tmp/opencv-official-c9ad577-b49/modules/core/include/opencv2/core/mat.inl.hpp
FP_N=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad/build-run1/_deps/depends-opencv-build/opencv2.framework/Headers/core/mat.inl.hpp
FP_P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad/pfk-host/build-pfk-04c0e83/_deps/depends-opencv-build/opencv2.framework/Headers/core/mat.inl.hpp
for pair in "official_rules:$FP_O" "generic:$FP_G" "gpufenothread:$FP_N" "pfk:$FP_P"; do
  n=${pair%%:*}; fp=${pair#*:}; printf '  %-16s %s\n' $n "$(grep -cF "$fp" $t/run.txt | awk '{print ($1>0)?1:0}')"; done
echo "== rec30 code in Runner"
for k in PWXrslamCameraHz poses_camera_by_recording_frame.csv barrier_nocache fsync_each PWBenchLidarSoakArms ruler_subset_xr30 xrslam_admission every_subset_frame_admitted "pw.bench.lidar-recorder-timing/2" PwXrslamOfficialFeed.admits; do
  printf '  %-40s %s\n' "$k" "$(grep -c -- "$k" $t/run.txt)"; done
echo "== expmid (2026-09-25): exposure-midpoint default"
for k in exposure_mid_source exposure_mid_default exposure_mid_rule mean_half_exposure_applied_s "t_feed = pts + exposure/2 + c" PWXrslamExposureMid launch_argument unparseable; do
  printf '  %-40s %s\n' "$k" "$(grep -c -- "$k" $t/run.txt)"; done
printf '  %-40s %s\n' "T _pw_xrslam_live_exposure_mid (Runner)" "$(nm "$A/Runner" 2>/dev/null | grep -cE ' [Tt] _pw_xrslam_live_exposure_mid$')"
echo "== Dart AOT: 13 menu pages (0 = tree-shaken) + rec30 page strings"
strings -a "$A/Frameworks/App.framework/App" > $t/app.txt
miss=0
for k in BenchHomePage BenchLidarRecordPage BenchReplayPage BenchFullChainPage BenchCoreSwitchesPage ArMinimalLoopPage ZeroArkitCaptureProbePage ZeroArkitPreviewProbePage ImuCalibCapturePage ZuptProbePage PoseChainProbePage LodDebugPage SplatAbPage; do
  n=$(grep -c -- "$k" $t/app.txt); [ "$n" -gt 0 ] || miss=$((miss+1)); printf '  %-28s %s\n' "$k" "$n"; done
echo "  pages missing: $miss"
printf '  %-28s %s\n' PocketWorldApp "$(grep -c PocketWorldApp $t/app.txt)"
printf '  %-28s %s\n' "viobench (BenchUnifiedNative)" "$(grep -c BenchUnifiedNative $t/app.txt)"
for k in "30:fsync_each,30:barrier,30:barrier,30:fsync_each" pw_bench_lidar_reexport_subset "record_hz" "write_sync"; do printf '  %-50s %s\n' "$k" "$(grep -c -- "$k" $t/app.txt)"; done
for k in pw_xrslam_live_exposure_mid PWXrslamExposureMid exposure_mid bench_default exposureMidEnabled; do printf '  AOT %-46s %s\n' "$k" "$(grep -c -- "$k" $t/app.txt)"; done
echo "== Dawn: _wgpuCreateInstance definitions in Runner: $(nm "$A/Runner" 2>/dev/null | grep -cE ' [Tt] _wgpuCreateInstance$')"
echo "== Runner defined symbol families"
nm -gU "$A/Runner" > $t/nm.txt 2>/dev/null
for pat in _PWXrslamTransport _pw_bench_lidar_ _pw_bench_replay_ _pw_camera_slot_ _pw_xrslam_live_ '_pwlod_run$' '_pwsplat_ab_run$'; do printf '  %4s %s\n' "$(grep -cE " [TtSsDd] $pat" $t/nm.txt)" "$pat"; done
nm -gU "$A/Runner" | grep " _pw_bench_lidar_" | sed 's/^/    /'
echo "== engine entry points in Runner (t = linked via -force_load)"
nm "$A/Runner" | grep -E ' [Tt] _XRSLAM(Create|Destroy|GetResult|PushSensorData|RunOneFrame)$' | sed 's/^/  /'
echo "== embedded frameworks __text vs unified_official_xrslam_rec30_20260924 (the installed bench)"
for n in PWOfficialSfm PWDense PWOnnxRuntime PWVIOBenchKit PWXRSLAMEngine PWBasaltEngine thermion_dart Flutter; do
  unsign "$A/Frameworks/$n.framework/$n" $t/a; unsign "$PREV/Frameworks/$n.framework/$n" $t/p
  a=$(shasum -a 256 < $t/a | cut -c1-16); printf '  %-16s unsigned sha %s %s\n' $n $a "$(cmp -s $t/a $t/p && echo SAME || echo DIFF)"; done
echo "  Frameworks: $(ls "$A/Frameworks" | tr '\n' ' ')"
echo "== signature"
codesign --verify --deep --strict --verbose=2 "$A" 2>&1 | tail -2
codesign -dv "$A" 2>&1 | grep -E '^Identifier|TeamIdentifier' | head -2
if [ -n "$MAP" ] && [ -f "$MAP" ]; then
  echo "== Link map: Dawn"
  awk '/^# Object files:/{f=1;next} /^# Sections:/{f=0} f' "$MAP" > $t/obj.txt
  idx=$(grep -E '\] _wgpuCreateInstance$' "$MAP" | sed -E 's/.*\[ *([0-9]+)\] _wgpuCreateInstance$/\1/' | sort -u)
  echo "  _wgpuCreateInstance defined by $(printf '%s\n' $idx | grep -c .) object(s):"
  for i in $idx; do grep -E "^\[ *$i\] " $t/obj.txt | sed 's/^/    /'; done
fi
rm -rf $t
