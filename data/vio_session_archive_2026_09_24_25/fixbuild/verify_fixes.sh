#!/bin/bash
# verify_fixes.sh <fixes Runner.app> <baseline Runner.app> <committed unsigned PWOfficialSfm>
F=$1; B=$2; COMMITTED=$3
t=$(mktemp -d)
unsign() { cp "$1" "$2"; codesign --remove-signature "$2" 2>/dev/null; }
text() { segedit "$1" -extract __TEXT __text /dev/stdout 2>/dev/null | shasum -a 256 | cut -c1-16; }
echo "== Info.plist"; for a in $B $F; do printf '  %s PWFullChainBench=%s id=%s\n' "$(basename $(dirname $(dirname $(dirname $a))))" "$(/usr/libexec/PlistBuddy -c 'Print :PWFullChainBench' $a/Info.plist)" "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' $a/Info.plist)"; done
echo "== PWOfficialSfm"
unsign $F/Frameworks/PWOfficialSfm.framework/PWOfficialSfm $t/f; unsign $B/Frameworks/PWOfficialSfm.framework/PWOfficialSfm $t/b
echo "  __text baseline=$(text $t/b) fixes=$(text $t/f) committed=$(text $COMMITTED)"
cmp -s $t/f $COMMITTED && echo "  fixes embedded (unsigned) == committed vendor binary: byte-identical" || echo "  fixes embedded vs committed: differ at byte level (__text above decides)"
for s in _pwofficial_add_jpeg_frame_v2 _pwofficial_add_frame_v2 _pwofficial_registration_evidence_stats_v1 _pwofficial_add_jpeg_frame _pwofficial_add_frame; do
  printf '  export %-44s baseline=%s fixes=%s\n' $s "$(nm -gU $t/b | grep -c " $s\$")" "$(nm -gU $t/f | grep -c " $s\$")"; done
echo "  exports total baseline=$(nm -gU $t/b | wc -l | tr -d ' ') fixes=$(nm -gU $t/f | wc -l | tr -d ' ')"
for s in _aether_sfm_add_frame_v2 _aether_sfm_registration_evidence_stats_v1 _aether_sfm_device_alignment_v1; do
  printf '  internal %-42s baseline=%s fixes=%s\n' $s "$(nm $t/b | grep -c " $s\$")" "$(nm $t/f | grep -c " $s\$")"; done
for k in '"type\\":\\"device_alignment_v1' device_alignment_v1 OFFICIAL_AETHER_DEVICE_ALIGN_V1 OFFICIAL_AETHER_REG_EVIDENCE OFFICIAL_AETHER_FINALIZE_VIA_RESUME reg_evidence_v1 OFFICIAL_AETHER_GSS_FUSED; do
  printf '  string %-40s baseline=%s fixes=%s\n' "$k" "$(strings -a $t/b | grep -c -- "$k")" "$(strings -a $t/f | grep -c -- "$k")"; done
echo "== Dart AOT (App.framework/App)"
for k in pwofficial_add_jpeg_frame_v2 pwofficial_add_jpeg_frame devicePoseTrustHonored official_device_sessions.jsonl OFFICIAL_AETHER_SCALE_ANCHOR moved_to_core_device_align_v1 feature_disabled OfficialARCapturePage; do
  printf '  %-36s baseline=%s fixes=%s\n' $k "$(strings -a $B/Frameworks/App.framework/App | grep -c -- $k)" "$(strings -a $F/Frameworks/App.framework/App | grep -c -- $k)"; done
echo "== Runner (Swift)"
for k in OFFICIAL_AETHER_SCALE_ANCHOR "full-chain 168 plugins registered" pocketworld_official_arkit; do
  printf '  %-36s baseline=%s fixes=%s\n' "$k" "$(strings -a $B/Runner | grep -c -- "$k")" "$(strings -a $F/Runner | grep -c -- "$k")"; done
echo "== other embedded binaries (unsigned __text)"
for n in PWDense PWOnnxRuntime thermion_dart Flutter; do
  unsign $B/Frameworks/$n.framework/$n $t/x; unsign $F/Frameworks/$n.framework/$n $t/y
  printf '  %-14s %s\n' $n "$([ "$(text $t/x)" = "$(text $t/y)" ] && echo SAME || echo DIFF)"; done
echo "== Frameworks dirs"; diff <(ls $B/Frameworks) <(ls $F/Frameworks) && echo "  same set: $(ls $F/Frameworks | tr '\n' ' ')"
rm -rf $t
