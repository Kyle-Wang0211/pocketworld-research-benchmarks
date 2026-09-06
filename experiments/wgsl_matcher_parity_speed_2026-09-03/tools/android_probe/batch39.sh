#!/bin/bash
# 第三十九批(P50 Pocket,稳态、无重装):default(A‴)/ formA / nokeyscan(W128+PTR)轮换 ×5,定 Adreno 上 A‴ 是持平还是赔。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-PHQ0223207007217}; d=$PW_ADB_SERIAL; TAG=${TAG:-P50P}
kg(){ adb -s $d shell dumpsys window 2>/dev/null | grep -oE 'isStatusBarKeyguard=[a-z]+' | head -1 | cut -d= -f2; }
adb -s $d shell svc power stayon true >/dev/null 2>&1
L=~/Developer/pw_android_probe/${TAG}_batch39_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkeyguard\tlabel" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; D0="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1"
envfor(){ case $1 in default) echo "$D0";; nokeyscan) echo "$D0;${P}DIRECT_NOKEYSCAN=1";; formA) echo "$D0;${P}DIRECT_NOW64=1;${P}DIRECT_NOKEYSCAN=1;${P}DIRECT_NOPTR=1";; esac; }
i=0; for a in default formA nokeyscan nokeyscan formA default formA default nokeyscan default nokeyscan formA nokeyscan default formA; do
  i=$((i+1)); arm=${a}_$i; ex="$(envfor $a)"
  adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; k=$(kg)
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); lb=$(echo "$out" | grep -oE "blocked\([^)]*\)" | head -1)
  echo -e "$TAG $arm\t${ms:-FAIL}\t${sha:-?}\t$k\t$lb" | tee -a $L; sleep 15
done
echo "BATCH39_DONE $L"
