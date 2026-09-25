#!/usr/bin/env bash
# 只读:核验台架包里真的带着完整链(或不带),以及 Dawn 只有一份。
# 用法: verify_binary.sh <Runner.app> <expect_fullchain:1|0> [linkmap]
set -uo pipefail
A="$1"; FC="$2"; MAP="${3:-}"
R168=/Users/kaidongwang/Developer/pw_builds_20260904/Runner-168-feature-reuse.app
APP="$A/Frameworks/App.framework/App"; RUN="$A/Runner"
echo "== Info.plist"; /usr/libexec/PlistBuddy -c "Print :PWFullChainBench" "$A/Info.plist" 2>&1; /usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$A/Info.plist"
echo "== Dart AOT 类名(App.framework/App)"
strings -a "$APP" > /tmp/.vb_app_strings.$$ 
for k in OfficialARCapturePage AetherAppShell PocketWorldApp _AuthGate NativeDenseStageLauncher PwDenseFfi PhotoArchiveCoordinator OfficialArchiveBackgroundRuntime SfmLiveRecon VioDiagnosticsRecorder MePage ArLoopBenchApp LodDebugPage BenchReplayPage ZeroArkitCaptureProbePage ArMinimalLoopPage; do
  printf '  %-34s %s\n' "$k" "$(grep -c -- "$k" /tmp/.vb_app_strings.$$)"
done
rm -f /tmp/.vb_app_strings.$$
echo "== Runner 符号(nm -gU 定义的)"
nm -gU "$RUN" > /tmp/.vb_nm.$$ 2>/dev/null
for pat in '_wgpuCreateInstance$' '_pwsfm_' '_aether_sfm_' '_XRSLAM' '_pw_jxl_' '_pw_zpaq_' '_pw_lepton_' '_pw_sqlite_' '_pw_telemetry$' '_pwlod_' '_pw_camera_slot_' '_pw_bench_replay_' '_OrtGetApiBase$' '_pw_vt_' '_PWXrslamTransport'; do
  printf '  %-24s %s\n' "$pat" "$(grep -cE " [TtSsDd] $pat" /tmp/.vb_nm.$$)"
done
echo "  wgpuCreateInstance 全部定义(含本地符号): $(nm "$RUN" 2>/dev/null | grep -cE ' [Tt] _wgpuCreateInstance$')"
rm -f /tmp/.vb_nm.$$
echo "== Runner 里的生产 Swift / 通道字符串"
strings -a "$RUN" > /tmp/.vb_run_strings.$$
for k in pocketworld_official_arkit pocketworld_vio_timebase pocketworld_vio_thermal pocketworld_official_archive_background aether_texture OfficialAetherARKitPlugin PwVioSlamFeeder "full-chain 168 plugins registered" pw_lod_texture; do
  printf '  %-44s %s\n' "$k" "$(grep -c -- "$k" /tmp/.vb_run_strings.$$)"
done
echo "== 与 168 出货 Runner 的字符串指纹(含 Official/PwVio/pocketworld_ 的字符串,台架包是否全都有)"
strings -a "$R168/Runner" | grep -E 'OfficialAetherARKit|PwVio|pocketworld_|\[AppDelegate\]|OfficialRecon|OfficialArchive' | sort -u > /tmp/.vb_168.$$
sort -u /tmp/.vb_run_strings.$$ > /tmp/.vb_run_sorted.$$
tot=$(wc -l < /tmp/.vb_168.$$); miss=$(comm -23 /tmp/.vb_168.$$ /tmp/.vb_run_sorted.$$ | wc -l)
echo "  168 指纹串 $tot 条,台架缺 $miss 条"; comm -23 /tmp/.vb_168.$$ /tmp/.vb_run_sorted.$$ | head -12 | sed 's/^/    缺: /'
rm -f /tmp/.vb_168.$$ /tmp/.vb_run_sorted.$$ /tmp/.vb_run_strings.$$
echo "== 嵌入框架 vs 168(去签名后 __text sha)"
for n in PWOfficialSfm PWDense PWOnnxRuntime; do
  t=$(mktemp); cp "$A/Frameworks/$n.framework/$n" "$t"; codesign --remove-signature "$t" 2>/dev/null
  u=$(mktemp); cp "$R168/Frameworks/$n.framework/$n" "$u"; codesign --remove-signature "$u" 2>/dev/null
  a=$(segedit "$t" -extract __TEXT __text /dev/stdout 2>/dev/null | shasum -a 256 | cut -c1-16)
  b=$(segedit "$u" -extract __TEXT __text /dev/stdout 2>/dev/null | shasum -a 256 | cut -c1-16)
  printf '  %-14s bench=%s 168=%s %s\n' "$n" "$a" "$b" "$([ "$a" = "$b" ] && echo SAME || echo DIFF)"
  rm -f "$t" "$u"
done
for f in casdiffmvs.onnx casdiffmvs_feat.onnx casdiffmvs_rest.onnx; do cmp -s "$A/Frameworks/PWDense.framework/$f" "$R168/Frameworks/PWDense.framework/$f" && echo "  $f SAME" || echo "  $f DIFF"; done
echo "== Frameworks 目录"; ls "$A/Frameworks"
if [ -n "$MAP" ] && [ -f "$MAP" ]; then
  echo "== 链接图:Dawn 目标文件来源"
  awk '/^# Object files:/{f=1;next} /^# Sections:/{f=0} f' "$MAP" > /tmp/.vb_obj.$$
  echo "  目标文件总数 $(wc -l < /tmp/.vb_obj.$$)"
  echo "  来自 libaether3d_ffi.a: $(grep -c 'libaether3d_ffi.a(' /tmp/.vb_obj.$$)"
  echo "  来自 Release-iphoneos/libwebgpu_dawn.a: $(grep -c 'Release-iphoneos/libwebgpu_dawn.a(' /tmp/.vb_obj.$$)"
  echo "  来自 Debug-iphoneos/libwebgpu_dawn.a: $(grep -c 'Debug-iphoneos/libwebgpu_dawn.a(' /tmp/.vb_obj.$$)"
  echo "  来自 libpw_gpu_frontend: $(grep -c 'libpw_gpu_frontend' /tmp/.vb_obj.$$)"
  echo "  来自 libpw_lod_: $(grep -c 'libpw_lod_' /tmp/.vb_obj.$$)"
  grep -E 'webgpu_dawn.a\(' /tmp/.vb_obj.$$ | head -5 | sed 's/^/    /'
  echo "  定义 _wgpuCreateInstance 的目标文件:"
  idx=$(grep -E '\] _wgpuCreateInstance$' "$MAP" | sed -E 's/.*\[ *([0-9]+)\] _wgpuCreateInstance$/\1/' | sort -u)
  echo "    定义条数: $(printf '%s\n' $idx | grep -c .)"
  for i in $idx; do grep -E "^\[ *$i\] " /tmp/.vb_obj.$$ | sed 's/^/    /'; done
  rm -f /tmp/.vb_obj.$$
fi
