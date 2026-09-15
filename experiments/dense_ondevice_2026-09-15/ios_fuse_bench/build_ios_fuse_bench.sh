#!/usr/bin/env bash
# Stage-2 fusion device gate app: dense_fuse + test_fuse (main→fuse_run) + shell, linked against the very
# OpenCV 4.0.1 archive the product ships. Hand-rolled .app + codesign, same recipe as the proven CasDiffBench.
# Separate bundle id (com.kyle.casdifffusebench) — never touches com.kyle.PocketWorld.
set -euo pipefail
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/e8c0e65e-e731-470c-87b9-f01ba7ec3498/scratchpad
SRC=$HOME/Developer/Aether3D-cross/aether_cpp/src/dense
OCVS=$HOME/Developer/opencv-401-src; OCVB=$HOME/Developer/opencv-401-build-mac
ARCHIVE=$HOME/Developer/pocketworld/vendor/xrslam/libs/ios-arm64/libopencv_generic_4_0_1.a
PACK=$S/fuse_gate/subpack8
STAGE=/private/tmp/casdiff_fuse_stage; APP=$STAGE/CasDiffFuseBench.app
BUNDLE_ID=com.kyle.casdifffusebench; TEAM=26AH7V448L
IDENTITY="Apple Development: wkd20040211@gmail.com (8N5Z34UK5Y)"
MINOS=26.2   # the shipped archive's objects carry minos 26.2 (ld warned when linking for 14.0)
rm -rf "$STAGE"; mkdir -p "$APP/subpack8"
CXXFLAGS=(-arch arm64 -miphoneos-version-min="$MINOS" -std=c++20 -O2 -ffp-contract=off -fno-fast-math
          -I"$OCVB" -I"$OCVS/include" -I"$OCVS/modules/core/include" -I"$OCVS/modules/imgproc/include")
xcrun -sdk iphoneos clang++ "${CXXFLAGS[@]}" -c "$SRC/dense_fuse.cc" -o "$STAGE/dense_fuse.o"
xcrun -sdk iphoneos clang++ "${CXXFLAGS[@]}" -Dmain=fuse_run -c "$SRC/test_fuse.cc" -o "$STAGE/test_fuse.o"
xcrun -sdk iphoneos clang++ -arch arm64 -miphoneos-version-min="$MINOS" -fobjc-arc -c "$S/ios_fuse/ios_fuse_shell.mm" -o "$STAGE/shell.o"
xcrun -sdk iphoneos clang++ -arch arm64 -miphoneos-version-min="$MINOS" "$STAGE/shell.o" "$STAGE/test_fuse.o" "$STAGE/dense_fuse.o" \
  "$ARCHIVE" -lz -framework UIKit -framework Foundation -o "$APP/CasDiffFuseBench"
cp "$PACK"/{depth.f32,conf0.f32,conf1.f32,conf2.f32,rgb.u8,cams.f32,neighbors.i32,meta.txt} "$APP/subpack8/"
cat > "$APP/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>CasDiffFuseBench</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleName</key><string>CasDiffFuseBench</string>
  <key>CFBundleDisplayName</key><string>Fuse Gate</string>
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
[ -n "$PROF" ] || { echo "❌ 找不到通配描述文件 $TEAM.*"; exit 1; }
cp "$PROF" "$APP/embedded.mobileprovision"
cat > "$STAGE/fuse.entitlements" <<ENT
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>application-identifier</key><string>$TEAM.$BUNDLE_ID</string>
  <key>com.apple.developer.team-identifier</key><string>$TEAM</string>
  <key>get-task-allow</key><true/>
</dict></plist>
ENT
xattr -cr "$APP"
codesign --force --sign "$IDENTITY" --entitlements "$STAGE/fuse.entitlements" --timestamp=none "$APP"
codesign -vv "$APP" 2>&1 | tail -2
lipo -info "$APP/CasDiffFuseBench"
echo "✅ → $APP ($(du -sh "$APP" | cut -f1))"
