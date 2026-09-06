#!/bin/bash
# 第三十批:A″ 切默认后的 ref 对照(用户 09-06 裁决)。default(无 env)vs formA(NOW64+NOKEYSCAN+NOPTR),ABBA ×3;先装 out/pwprobe.apk(TU 63443541bba1,主机侧默认改了)。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-192.168.1.11:5555}; d=$PW_ADB_SERIAL
kg(){ adb -s $d shell dumpsys window 2>/dev/null | grep -oE 'isStatusBarKeyguard=[a-z]+' | head -1 | cut -d= -f2; }
adb -s $d shell am force-stop com.kyle.pwprobe >/dev/null 2>&1; adb -s $d shell svc power stayon true >/dev/null 2>&1; adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
adb -s $d install -r -t out/pwprobe.apk 2>&1 | grep -E "Success|Failure"
L=~/Developer/pw_android_probe/mate10_batch30_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkeyguard\tlabel" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; A="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1;${P}DIRECT_NOW64=1;${P}DIRECT_NOKEYSCAN=1;${P}DIRECT_NOPTR=1"
i=0; for a in default formA formA default default formA; do
  i=$((i+1)); arm=${a}_$i; if [ "$a" = default ]; then ex="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1"; else ex="$A"; fi
  adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; k=$(kg)
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); lb=$(echo "$out" | grep -oE "blocked\([^)]*\)" | head -1); bid=$(echo "$out" | grep -oE "BUILD_ID 不一致[^\n]{0,40}")
  echo -e "Mate10 $arm\t${ms:-FAIL}\t${sha:-?}\t$k\t${lb}${bid}" | tee -a $L; sleep 15
done
echo "BATCH30_DONE $L"
