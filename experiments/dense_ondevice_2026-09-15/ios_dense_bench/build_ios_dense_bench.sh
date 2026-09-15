#!/usr/bin/env bash
# Dense chain bench app (com.kyle.casdiffdensebench): dense_* + dense_bench_main (main→dense_bench_run) + shell,
# linked with the self-built ORT 1.29.0 dylib (WebGPU EP), the product's OpenCV 4.0.1 archive, and the pinned
# libjpeg-turbo iOS archive. Hand-rolled .app + codesign (dylib first, then .app), as the proven benches.
set -euo pipefail
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/e8c0e65e-e731-470c-87b9-f01ba7ec3498/scratchpad
SRC=$HOME/Developer/Aether3D-cross/aether_cpp/src/dense
AC=$HOME/Developer/Aether3D-cross/aether_cpp
OCVS=$HOME/Developer/opencv-401-src; OCVB=$HOME/Developer/opencv-401-build-mac
ARCHIVE=$HOME/Developer/pocketworld/vendor/xrslam/libs/ios-arm64/libopencv_generic_4_0_1.a
JPEG_A=$AC/build-ios-device-dawn/third_party/libjpeg-turbo-build/libjpeg.a; JPEG_INC=$AC/third_party/libjpeg-turbo/src; JPEG_CFG=$AC/build-ios-device-dawn/third_party/libjpeg-turbo-build
ORT_DYLIB=$HOME/ort_ios_build/build_ios/Release/Release-iphoneos/libonnxruntime.1.29.0.dylib
ORT_INC=$HOME/ort_ios_build/onnxruntime/include/onnxruntime/core/session
MODEL=/Users/kaidongwang/Documents/progecttwo/_artifacts/ios_bench_abep2/casdiffmvs_abep2.onnx
INPUTS=$S/ios_dense/dense_inputs
STAGE=/private/tmp/casdiff_dense_stage; APP=$STAGE/CasDiffDenseBench.app
BUNDLE_ID=com.kyle.casdiffdensebench; TEAM=26AH7V448L
IDENTITY="Apple Development: wkd20040211@gmail.com (8N5Z34UK5Y)"
MINOS=26.2
rm -rf "$STAGE"; mkdir -p "$APP/Frameworks" "$APP/dense_inputs"
CXX=(-arch arm64 -miphoneos-version-min="$MINOS" -std=c++20 -O2 -ffp-contract=off -fno-fast-math
     -I"$SRC" -I"$ORT_INC" -I"$JPEG_INC" -I"$JPEG_CFG" -I"$OCVB" -I"$OCVS/include" -I"$OCVS/modules/core/include" -I"$OCVS/modules/imgproc/include")
OBJS=()
for f in dense_session dense_inputs dense_images dense_fuse dense_fuse_pack dense_runner dense_pipeline; do
  xcrun -sdk iphoneos clang++ "${CXX[@]}" -c "$SRC/$f.cc" -o "$STAGE/$f.o"; OBJS+=("$STAGE/$f.o")
done
xcrun -sdk iphoneos clang++ "${CXX[@]}" -Dmain=dense_bench_run -c "$S/ios_dense/dense_bench_main.cc" -o "$STAGE/bench_main.o"
xcrun -sdk iphoneos clang++ -arch arm64 -miphoneos-version-min="$MINOS" -fobjc-arc -c "$S/ios_dense/ios_dense_shell.mm" -o "$STAGE/shell.o"
xcrun -sdk iphoneos clang++ -arch arm64 -miphoneos-version-min="$MINOS" "$STAGE/shell.o" "$STAGE/bench_main.o" "${OBJS[@]}" \
  "$ORT_DYLIB" "$ARCHIVE" "$JPEG_A" -lz -framework UIKit -framework Foundation \
  -Wl,-rpath,@executable_path/Frameworks -o "$APP/CasDiffDenseBench" 2>&1 | grep -vE "was built for newer 'iOS'" || true
[ -x "$APP/CasDiffDenseBench" ] || { echo "LINK_FAIL"; exit 1; }
cp "$ORT_DYLIB" "$APP/Frameworks/libonnxruntime.1.dylib"
cp -R "$INPUTS"/. "$APP/dense_inputs/"; cp "$MODEL" "$APP/dense_inputs/casdiffmvs_abep2.onnx"
cat > "$APP/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>CasDiffDenseBench</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleName</key><string>CasDiffDenseBench</string>
  <key>CFBundleDisplayName</key><string>Dense Chain</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>MinimumOSVersion</key><string>$MINOS</string>
  <key>UIDeviceFamily</key><array><integer>1</integer></array>
  <key>UILaunchScreen</key><dict/>
  <key>UIFileSharingEnabled</key><true/>
  <key>LSSupportsOpeningDocumentsInPlace</key><true/>
  <key>UISupportedInterfaceOrientations</key><array><string>UIInterfaceOrientationPortrait</string></array>
</dict></plist>
PLIST
plutil -convert binary1 "$APP/Info.plist"
PROF=""
for p in ~/Library/Developer/Xcode/UserData/Provisioning\ Profiles/*.mobileprovision; do
  aid=$(security cms -D -i "$p" 2>/dev/null | plutil -extract Entitlements.application-identifier raw - 2>/dev/null || true)
  if [ "$aid" = "$TEAM.*" ]; then PROF="$p"; break; fi
done
[ -n "$PROF" ] || { echo "❌ no wildcard profile"; exit 1; }
cp "$PROF" "$APP/embedded.mobileprovision"
cat > "$STAGE/dense.entitlements" <<ENT
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>application-identifier</key><string>$TEAM.$BUNDLE_ID</string>
  <key>com.apple.developer.team-identifier</key><string>$TEAM</string>
  <key>get-task-allow</key><true/>
</dict></plist>
ENT
xattr -cr "$APP"
codesign --force --sign "$IDENTITY" --timestamp=none "$APP/Frameworks/libonnxruntime.1.dylib"
codesign --force --sign "$IDENTITY" --entitlements "$STAGE/dense.entitlements" --timestamp=none "$APP"
codesign -vv "$APP" 2>&1 | tail -1; otool -L "$APP/CasDiffDenseBench" | grep -E "onnxruntime|libc\+\+" ; echo "✅ → $APP ($(du -sh "$APP" | cut -f1))"
