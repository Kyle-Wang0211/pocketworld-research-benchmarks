#!/bin/bash
# 最小 APK:aapt2 → javac → d8 → 打包 .so → zipalign → apksigner(debug key)。不需要 Gradle。
set -euo pipefail
export JAVA_HOME=${JAVA_HOME:-/opt/homebrew/opt/openjdk}; export PATH=$JAVA_HOME/bin:$PATH
SDK=${SDK:-$HOME/Library/Android/sdk}; BT=$SDK/build-tools/34.0.0; AJ=$SDK/platforms/android-34/android.jar
cd "$(dirname "$0")"; rm -rf out; mkdir -p out/res out/cls
[ -f debug.keystore ] || keytool -genkeypair -keystore debug.keystore -storepass android -keypass android -alias androiddebugkey -dname "CN=Android Debug,O=Android,C=US" -keyalg RSA -keysize 2048 -validity 10000 >/dev/null 2>&1
$BT/aapt2 compile --dir res -o out/res.zip 2>/dev/null || $BT/aapt2 compile -o out/res.zip 2>/dev/null || true
$BT/aapt2 link -I "$AJ" --manifest AndroidManifest.xml -o out/base.apk --java out/gen $( [ -s out/res.zip ] && echo out/res.zip ) 
$JAVA_HOME/bin/javac --release 8 -classpath "$AJ" -d out/cls $(find src out/gen -name '*.java') 2>&1 | grep -v "warning:" || true
$BT/d8 --min-api 26 --output out $(find out/cls -name '*.class')
cp out/base.apk out/unsigned.apk
( cd out && zip -q unsigned.apk classes.dex )
( cd "$(dirname "$0")" && zip -q out/unsigned.apk lib/arm64-v8a/libpwprobe.so )
$BT/zipalign -f -p 4 out/unsigned.apk out/aligned.apk
$BT/apksigner sign --ks debug.keystore --ks-pass pass:android --key-pass pass:android --out out/pwprobe.apk out/aligned.apk
ls -la out/pwprobe.apk | awk '{print "APK:", $5, "bytes"}'
