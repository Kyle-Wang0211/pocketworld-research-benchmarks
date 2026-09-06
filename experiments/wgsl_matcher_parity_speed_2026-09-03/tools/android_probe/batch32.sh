#!/bin/bash
# 第三十二批(P50 Pocket,接 batch31):A″ 三刀在 Adreno 660 上的分解 —— default(A″)/ NOW64(W128+KS2+PTR)/ NOPTR(W64+KS2)/ NOKEYSCAN(W128+PTR)/ formA,default 夹两头。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-PHQ0223207007217}; d=$PW_ADB_SERIAL
kg(){ adb -s $d shell dumpsys window 2>/dev/null | grep -oE 'isStatusBarKeyguard=[a-z]+' | head -1 | cut -d= -f2; }
adb -s $d shell svc power stayon true >/dev/null 2>&1
L=~/Developer/pw_android_probe/p50pocket_batch32_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkeyguard\tlabel" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; D0="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1"
declare -A E=( [default]="$D0" [now64]="$D0;${P}DIRECT_NOW64=1" [noptr]="$D0;${P}DIRECT_NOPTR=1" [nokeyscan]="$D0;${P}DIRECT_NOKEYSCAN=1" [formA]="$D0;${P}DIRECT_NOW64=1;${P}DIRECT_NOKEYSCAN=1;${P}DIRECT_NOPTR=1" )
i=0; for a in default now64 noptr nokeyscan default formA nokeyscan noptr now64 default; do
  i=$((i+1)); arm=${a}_$i; ex="${E[$a]}"
  adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; k=$(kg)
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); lb=$(echo "$out" | grep -oE "blocked\([^)]*\)" | head -1)
  echo -e "P50P $arm\t${ms:-FAIL}\t${sha:-?}\t$k\t$lb" | tee -a $L; sleep 15
done
echo "BATCH32_DONE $L"
