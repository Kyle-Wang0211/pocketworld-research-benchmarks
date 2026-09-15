#!/usr/bin/env bash
# assemble_overlay.sh <num> <label> <baseline .app name> <built Runner.app path> <vendor Frameworks dir>
# Runner-<num>-<label>.app = baseline with Frameworks/App.framework replaced by the built one, PWDense.framework and
# PWOnnxRuntime.framework added, CFBundleVersion set, everything re-signed with the baseline's own entitlements.
# Then the protocol self-check: only App may DIFF; Runner/Flutter/PWOfficialSfm/thermion byte-identical after
# signature strip; added files only under the two new frameworks.
set -euo pipefail
NUM=$1; LABEL=$2; BASENAME=$3; BUILT=$4; VENDOR=$5
LEDGER=$HOME/Developer/pw_builds_20260904
BASE=$LEDGER/$BASENAME; NEW=$LEDGER/Runner-$NUM-$LABEL.app
IDENTITY="Apple Development: wkd20040211@gmail.com (8N5Z34UK5Y)"
STAGE=/private/tmp/pw${NUM}_stage; rm -rf "$STAGE"; mkdir -p "$STAGE"
[ -d "$BASE" ] || { echo "❌ baseline missing: $BASE"; exit 1; }
[ -d "$BUILT/Frameworks/App.framework" ] || { echo "❌ built App.framework missing at $BUILT"; exit 1; }
[ "$NEW" != "$BASE" ] || { echo "❌ target == baseline"; exit 1; }
rm -rf "$NEW"; cp -R "$BASE" "$NEW"
rm -rf "$NEW/Frameworks/App.framework"; cp -R "$BUILT/Frameworks/App.framework" "$NEW/Frameworks/App.framework"
rm -rf "$NEW/Frameworks/PWDense.framework" "$NEW/Frameworks/PWOnnxRuntime.framework"
cp -R "$VENDOR/PWDense.xcframework/ios-arm64/PWDense.framework" "$NEW/Frameworks/PWDense.framework"
cp -R "$VENDOR/PWOnnxRuntime.xcframework/ios-arm64/PWOnnxRuntime.framework" "$NEW/Frameworks/PWOnnxRuntime.framework"
plutil -replace CFBundleVersion -string "$NUM" "$NEW/Info.plist"
codesign -d --entitlements :- "$BASE" 2>/dev/null > "$STAGE/entitlements.plist"; plutil -lint "$STAGE/entitlements.plist" >/dev/null
xattr -cr "$NEW"
for fw in "$NEW"/Frameworks/*.framework; do codesign --force --sign "$IDENTITY" --timestamp=none "$fw" >/dev/null 2>&1; done
codesign --force --sign "$IDENTITY" --entitlements "$STAGE/entitlements.plist" --timestamp=none "$NEW" >/dev/null 2>&1
codesign -vv --deep --strict "$NEW" 2>&1 | tail -1
echo "== self-check vs $BASENAME =="
(cd "$BASE" && find . -type f | sort) > "$STAGE/base.txt"; (cd "$NEW" && find . -type f | sort) > "$STAGE/new.txt"
echo "files base=$(wc -l < "$STAGE/base.txt" | tr -d ' ') new=$(wc -l < "$STAGE/new.txt" | tr -d ' ')"
echo "removed outside App.framework: $(comm -23 "$STAGE/base.txt" "$STAGE/new.txt" | grep -vc '^./Frameworks/App.framework/' || true)"
echo "added outside App/PWDense/PWOnnxRuntime: $(comm -13 "$STAGE/base.txt" "$STAGE/new.txt" | grep -vcE '^./Frameworks/(App|PWDense|PWOnnxRuntime).framework/' || true)"
ok=1
for b in Runner Frameworks/Flutter.framework/Flutter Frameworks/PWOfficialSfm.framework/PWOfficialSfm Frameworks/thermion_dart.framework/thermion_dart; do
  cp "$BASE/$b" "$STAGE/a.bin"; cp "$NEW/$b" "$STAGE/b.bin"
  codesign --remove-signature "$STAGE/a.bin" 2>/dev/null || true; codesign --remove-signature "$STAGE/b.bin" 2>/dev/null || true
  if cmp -s "$STAGE/a.bin" "$STAGE/b.bin"; then echo "  SAME  $b"; else echo "  DIFF  $b  🔴"; ok=0; fi
done
cmp -s "$BASE/Frameworks/App.framework/App" "$NEW/Frameworks/App.framework/App" && { echo "  ⚠️ App identical to baseline — nothing new was built"; ok=0; } || echo "  DIFF  Frameworks/App.framework/App (expected)"
echo "  pwdense_run in App AOT: $(grep -ac pwdense_run "$NEW/Frameworks/App.framework/App")  PWDense exports: $(nm -gU "$NEW/Frameworks/PWDense.framework/PWDense" | wc -l | tr -d ' ')  model md5 $(md5 -q "$NEW/Frameworks/PWDense.framework/casdiffmvs.onnx")"
echo "  CFBundleVersion $(plutil -extract CFBundleVersion raw "$NEW/Info.plist")  size $(du -sh "$NEW" | cut -f1)"
[ "$ok" = 1 ] && echo "✅ overlay self-check passed → $NEW" || { echo "🔴 self-check failed"; exit 1; }
