#!/bin/bash
# 第四十四批(通用,无装机):KP vs 默认 A‴ 长序列 ×6,Wi-Fi adb。TAG/PW_ADB_SERIAL/ARMS 由环境给。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-192.168.1.6:5555}; d=$PW_ADB_SERIAL; TAG=${TAG:-P50P}
kg(){ adb -s $d shell dumpsys window 2>/dev/null | grep -oE 'isStatusBarKeyguard=[a-z]+' | head -1 | cut -d= -f2; }
adb -s $d shell am force-stop com.kyle.pwprobe >/dev/null 2>&1; adb -s $d shell svc power stayon true >/dev/null 2>&1; adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
L=~/Developer/pw_android_probe/${TAG}_batch44_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkeyguard\tlabel\tfile" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; D0="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1"; W=/data/data/com.kyle.pwprobe/files/wgsl
envfor(){ case $1 in default) echo "$D0";; kp) echo "$D0;${P}DIRECT_KP=1";; nokeyscan) echo "$D0;${P}DIRECT_NOKEYSCAN=1";; formA) echo "$D0;${P}DIRECT_NOW64=1;${P}DIRECT_NOKEYSCAN=1;${P}DIRECT_NOPTR=1";; esac; }
i=0; for a in ${ARMS:-default kp kp default default kp kp default default kp kp default}; do
  i=$((i+1)); arm=${a}_$i; ex="$(envfor $a)"
  adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; k=$(kg)
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); lb=$(echo "$out" | grep -oE "blocked\([^)]*\)" | head -1); fu=$(echo "$out" | grep -oE "WGSL_FILE [^ ]+ (len=[0-9]+|open failed)" | head -1 | sed -E 's#.*/##')
  echo -e "$TAG $arm\t${ms:-FAIL}\t${sha:-?}\t$k\t$lb\t$fu" | tee -a $L; sleep 15
done
echo "BATCH42_DONE $L"
