set -o pipefail
cd /Users/kaidongwang/Developer/pocketworld-wt-zeroarkit || exit 9
export PW_PRODUCT_SOURCE_MANIFEST_SHA256="$(bash tool/product_source_manifest.sh 2>/dev/null | tail -1)"
export PW_DIAGNOSTIC_BUILD_ID="zeroarkit-verify-$(date +%Y%m%d%H%M)"
export PW_VIO_SHADOW_MODE="off"
echo "manifest=$PW_PRODUCT_SOURCE_MANIFEST_SHA256 build_id=$PW_DIAGNOSTIC_BUILD_ID"
# 磁盘看门狗:低于 1.2 GiB 就把构建掐掉,别把机器占满(同机还有别的 agent)。
( while true; do
    free=$(df -k /Users/kaidongwang | tail -1 | awk '{print $4}')
    if [ "$free" -lt 1258291 ]; then echo "DISK-GUARD: free=${free}K < 1.2GiB, killing build"; pkill -f "xcodebuild" ; pkill -f "flutter_tools" ; exit 1; fi
    sleep 15
  done ) &
GUARD=$!
flutter build ios --release --no-codesign 2>&1 | tail -60
RC=$?
kill $GUARD 2>/dev/null
echo "BUILD_RC=$RC"
df -h /Users/kaidongwang | tail -1
