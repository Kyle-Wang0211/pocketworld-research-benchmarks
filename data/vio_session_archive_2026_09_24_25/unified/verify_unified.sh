#!/usr/bin/env bash
# verify_unified.sh <Runner.app> [linkmap] — read-only checks of the unified arloopbench package.
set -uo pipefail
A="$1"; MAP="${2:-}"
R168=/Users/kaidongwang/Developer/pw_builds_20260904/Runner-168-feature-reuse.app
FIX=/Users/kaidongwang/Developer/arloopbench_builds/fullchain_168_fixes/Runner.app
KIT=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-unified-20260924/bench/viobench_kit/dist
t=$(mktemp -d)
unsign() { cp "$1" "$2"; codesign --remove-signature "$2" 2>/dev/null; }
text() { segedit "$1" -extract __TEXT __text /dev/stdout 2>/dev/null | shasum -a 256 | cut -c1-16; }
echo "== Info.plist"
for k in CFBundleIdentifier CFBundleShortVersionString CFBundleVersion PWFullChainBench; do
  printf '  %-28s %s\n' "$k" "$(/usr/libexec/PlistBuddy -c "Print :$k" "$A/Info.plist" 2>&1)"; done
echo "== Dart AOT (App.framework/App): every menu page + production app (count of name strings; 0 = tree-shaken)"
strings -a "$A/Frameworks/App.framework/App" > $t/app.txt
miss=0
for k in ArLoopBenchApp BenchHomePage BenchLidarRecordPage BenchReplayPage BenchFullChainPage BenchCoreSwitchesPage \
         ArMinimalLoopPage ZeroArkitCaptureProbePage ZeroArkitPreviewProbePage ImuCalibCapturePage ZuptProbePage \
         PoseChainProbePage LodDebugPage SplatAbPage BenchUnifiedNative \
         PocketWorldApp AetherAppShell _AuthGate OfficialARCapturePage NativeDenseStageLauncher SfmLiveRecon PwDenseFfi MePage \
         pwofficial_add_jpeg_frame_v2 devicePoseTrustHonored official_device_sessions.jsonl moved_to_core_device_align_v1 official_env.json; do
  n=$(grep -c -- "$k" $t/app.txt); [ "$n" -gt 0 ] || miss=$((miss+1)); printf '  %-34s %s\n' "$k" "$n"; done
echo "  missing: $miss"
for k in OFFICIAL_AETHER_SCALE_ANCHOR feature_disabled; do printf '  (must be 0, removed by C-dart) %-28s %s\n' "$k" "$(grep -c -- "$k" $t/app.txt)"; done
echo "== Runner defined symbols"
nm -gU "$A/Runner" > $t/nm.txt 2>/dev/null
for pat in '_wgpuCreateInstance$' '_pwsplat_ab_run$' '_pwpoints_run$' '_pwcloud_run$' '_pwlod_run$' '_pwlod_' '_pw_bench_replay_' '_pw_bench_lidar_' '_PWXrslamTransport' '_pw_camera_slot_' '_pw_jxl_' '_pw_zpaq_' '_pw_lepton_' '_pw_sqlite_' '_OrtGetApiBase$' '_pw_vt_'; do
  printf '  %-24s %s\n' "$pat" "$(grep -cE " [TtSsDd] $pat" $t/nm.txt)"; done
echo "  _wgpuCreateInstance definitions incl. local: $(nm "$A/Runner" 2>/dev/null | grep -cE ' [Tt] _wgpuCreateInstance$')"
echo "== Runner strings"
strings -a "$A/Runner" > $t/run.txt
for k in pw_bench_unified PWVIOBenchHost PWVIOBenchKit.framework "full-chain 168 plugins registered" pocketworld_official_arkit OfficialAetherARKitPlugin PwVioSlamFeeder pw_lod_texture PWSPLATAB; do
  printf '  %-40s %s\n' "$k" "$(grep -c -- "$k" $t/run.txt)"; done
echo "== 168 fingerprint strings present in this Runner"
strings -a "$R168/Runner" | grep -E 'OfficialAetherARKit|PwVio|pocketworld_|\[AppDelegate\]|OfficialRecon|OfficialArchive' | sort -u > $t/168.txt
sort -u $t/run.txt > $t/run_sorted.txt
echo "  168: $(wc -l < $t/168.txt | tr -d ' ') strings, missing here: $(comm -23 $t/168.txt $t/run_sorted.txt | wc -l | tr -d ' ')"
comm -23 $t/168.txt $t/run_sorted.txt | sed 's/^/    missing: /'
echo "== Embedded frameworks (unsigned __text sha)"
for n in PWOfficialSfm PWDense PWOnnxRuntime thermion_dart Flutter; do
  unsign "$A/Frameworks/$n.framework/$n" $t/a; unsign "$FIX/Frameworks/$n.framework/$n" $t/f
  a=$(text $t/a); f=$(text $t/f); printf '  %-14s unified=%s fixes-pkg=%s %s\n' $n $a $f "$([ $a = $f ] && echo SAME || echo DIFF)"; done
for f in casdiffmvs.onnx casdiffmvs_feat.onnx casdiffmvs_rest.onnx; do cmp -s "$A/Frameworks/PWDense.framework/$f" "$R168/Frameworks/PWDense.framework/$f" && echo "  $f SAME as 168" || echo "  $f DIFF"; done
for n in PWVIOBenchKit PWXRSLAMEngine PWBasaltEngine; do
  a=$(text "$A/Frameworks/$n.framework/$n"); d=$(text "$KIT/$n.framework/$n")
  printf '  %-14s __text embedded=%s dist=%s %s\n' $n $a $d "$([ $a = $d ] && echo SAME || echo DIFF)"; done
echo "  PWOfficialSfm exports v2: add_jpeg_frame_v2=$(nm -gU "$A/Frameworks/PWOfficialSfm.framework/PWOfficialSfm" | grep -c ' _pwofficial_add_jpeg_frame_v2$') reg_evidence_stats=$(nm -gU "$A/Frameworks/PWOfficialSfm.framework/PWOfficialSfm" | grep -c ' _pwofficial_registration_evidence_stats_v1$')"
for k in OFFICIAL_AETHER_DEVICE_ALIGN_V1 OFFICIAL_AETHER_REG_EVIDENCE OFFICIAL_AETHER_FINALIZE_VIA_RESUME OFFICIAL_AETHER_GSS_FUSED; do
  printf '  core string %-38s %s\n' $k "$(strings -a "$A/Frameworks/PWOfficialSfm.framework/PWOfficialSfm" | grep -c -- $k)"; done
echo "  Frameworks: $(ls "$A/Frameworks" | tr '\n' ' ')"
echo "  Objective-C classes in PWXRSLAMEngine / PWBasaltEngine: $(nm "$A/Frameworks/PWXRSLAMEngine.framework/PWXRSLAMEngine" | grep -c 'OBJC_CLASS_\$') / $(nm "$A/Frameworks/PWBasaltEngine.framework/PWBasaltEngine" | grep -c 'OBJC_CLASS_\$')"
echo "== Signature"
codesign --verify --deep --strict --verbose=2 "$A" 2>&1 | tail -3
codesign -dv "$A" 2>&1 | grep -E 'Identifier|TeamIdentifier|Authority=Apple Development' | head -3
for n in PWVIOBenchKit PWXRSLAMEngine PWBasaltEngine PWOfficialSfm; do printf '  %-14s %s\n' $n "$(codesign --verify --strict "$A/Frameworks/$n.framework" 2>&1 && echo valid)"; done
if [ -n "$MAP" ] && [ -f "$MAP" ]; then
  echo "== Link map: Dawn"
  awk '/^# Object files:/{f=1;next} /^# Sections:/{f=0} f' "$MAP" > $t/obj.txt
  echo "  objects: $(wc -l < $t/obj.txt | tr -d ' ')  from libaether3d_ffi.a: $(grep -c 'libaether3d_ffi.a(' $t/obj.txt)  from any libwebgpu_dawn.a: $(grep -c 'libwebgpu_dawn.a(' $t/obj.txt)"
  idx=$(grep -E '\] _wgpuCreateInstance$' "$MAP" | sed -E 's/.*\[ *([0-9]+)\] _wgpuCreateInstance$/\1/' | sort -u)
  echo "  _wgpuCreateInstance defined by $(printf '%s\n' $idx | grep -c .) object(s):"
  for i in $idx; do grep -E "^\[ *$i\] " $t/obj.txt | sed 's/^/    /'; done
  echo "  splat objects: $(grep -cE '/(bench|bench_points|bench_cloud)\.o$' $t/obj.txt)"
fi
rm -rf $t
