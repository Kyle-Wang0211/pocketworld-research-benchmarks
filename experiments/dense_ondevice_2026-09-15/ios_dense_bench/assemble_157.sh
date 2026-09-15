#!/usr/bin/env bash
# Runner-157-dense-stage.app = the on-device baseline Runner-156-detect-compact.app with
#   (1) Frameworks/App.framework replaced by the Dart AOT built from ~/Developer/pw-dense-stage (feat/dense-stage =
#       pw-head-0827 5939197 + its 4 uncommitted diffs + the dense stage),
#   (2) Frameworks/PWDense.framework + Frameworks/PWOnnxRuntime.framework added (device slices),
#   (3) CFBundleVersion 156 -> 157,
# everything else (Runner, Flutter, PWOfficialSfm, thermion_dart, assets) byte-identical to 156 (checked below),
# re-signed with the same identity and the same entitlements as 156. Ledger form "DART_ONLY + embedded frameworks".
set -euo pipefail
LEDGER=$HOME/Developer/pw_builds_20260904
BASE=$LEDGER/Runner-156-detect-compact.app
NEW=$LEDGER/Runner-157-dense-stage.app
BUILT=$HOME/Developer/pw-dense-stage/build/ios/iphoneos/Runner.app
VENDOR=$HOME/Developer/pw-dense-stage/vendor/pw_dense/Frameworks
IDENTITY="Apple Development: wkd20040211@gmail.com (8N5Z34UK5Y)"
STAGE=/private/tmp/pw157_stage; rm -rf "$STAGE"; mkdir -p "$STAGE"
[ -d "$BUILT/Frameworks/App.framework" ] || { echo "❌ no built App.framework at $BUILT"; exit 1; }
rm -rf "$NEW"; cp -R "$BASE" "$NEW"
# (1) App.framework from the new build
rm -rf "$NEW/Frameworks/App.framework"; cp -R "$BUILT/Frameworks/App.framework" "$NEW/Frameworks/App.framework"
# (2) the two dense frameworks
cp -R "$VENDOR/PWDense.xcframework/ios-arm64/PWDense.framework" "$NEW/Frameworks/PWDense.framework"
cp -R "$VENDOR/PWOnnxRuntime.xcframework/ios-arm64/PWOnnxRuntime.framework" "$NEW/Frameworks/PWOnnxRuntime.framework"
# (3) version
plutil -replace CFBundleVersion -string "157" "$NEW/Info.plist"
# entitlements = exactly the baseline's
codesign -d --entitlements :- "$BASE" 2>/dev/null > "$STAGE/entitlements.plist"
plutil -lint "$STAGE/entitlements.plist" >/dev/null
# sign: frameworks first, app last (same order the shipped builds used)
xattr -cr "$NEW"
for fw in "$NEW"/Frameworks/*.framework; do codesign --force --sign "$IDENTITY" --timestamp=none "$fw"; done
codesign --force --sign "$IDENTITY" --entitlements "$STAGE/entitlements.plist" --timestamp=none "$NEW"
codesign -vv --deep --strict "$NEW" 2>&1 | tail -2
echo "== self-checks vs 156 =="
# a) file set: only App.framework contents, the two new frameworks, Info.plist, _CodeSignature, embedded.mobileprovision may differ
(cd "$BASE" && find . -type f | sort) > "$STAGE/base.txt"; (cd "$NEW" && find . -type f | sort) > "$STAGE/new.txt"
echo "files base=$(wc -l < "$STAGE/base.txt") new=$(wc -l < "$STAGE/new.txt")"
echo "removed vs 156 (must be only App.framework internals):"; comm -23 "$STAGE/base.txt" "$STAGE/new.txt" | grep -v "^./Frameworks/App.framework/" | head -5
echo "added (must be App.framework internals + PWDense + PWOnnxRuntime):"; comm -13 "$STAGE/base.txt" "$STAGE/new.txt" | grep -vE "^./Frameworks/(App|PWDense|PWOnnxRuntime).framework/" | head -5
# b) untouched binaries byte-identical after stripping signatures
for b in Runner Frameworks/Flutter.framework/Flutter Frameworks/PWOfficialSfm.framework/PWOfficialSfm Frameworks/thermion_dart.framework/thermion_dart; do
  cp "$BASE/$b" "$STAGE/a.bin"; cp "$NEW/$b" "$STAGE/b.bin"
  codesign --remove-signature "$STAGE/a.bin" 2>/dev/null; codesign --remove-signature "$STAGE/b.bin" 2>/dev/null
  if cmp -s "$STAGE/a.bin" "$STAGE/b.bin"; then echo "  ✅ $b byte-identical (signature stripped)"; else echo "  🔴 $b DIFFERS"; fi
done
# c) the new pieces
echo "  App.framework: $(du -sh "$NEW/Frameworks/App.framework" | cut -f1) (156: $(du -sh "$BASE/Frameworks/App.framework" | cut -f1))"
echo "  PWDense exports: $(nm -gU "$NEW/Frameworks/PWDense.framework/PWDense" | awk '{print $3}' | tr '\n' ' ')"
echo "  model in framework: $(md5 -q "$NEW/Frameworks/PWDense.framework/casdiffmvs.onnx")"
echo "  version: $(plutil -extract CFBundleVersion raw "$NEW/Info.plist")  (156 -> 157)"
echo "  dense Dart present in AOT: $(grep -ac 'pwdense_run' "$NEW/Frameworks/App.framework/App") occurrences of pwdense_run (must be >0)"
echo "✅ → $NEW ($(du -sh "$NEW" | cut -f1))"
