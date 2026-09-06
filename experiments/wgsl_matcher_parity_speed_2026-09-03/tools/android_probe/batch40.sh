#!/bin/bash
# 第四十批(P50 Pocket,接 batch39):A‴ 在 Adreno 的段账 + KS3@W128 —— default / nomerge / noload / notail / w128ks3 / nokeyscan / default(全走文件+env,无重装)。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-PHQ0223207007217}; d=$PW_ADB_SERIAL; TAG=${TAG:-P50P}
kg(){ adb -s $d shell dumpsys window 2>/dev/null | grep -oE 'isStatusBarKeyguard=[a-z]+' | head -1 | cut -d= -f2; }
adb -s $d shell svc power stayon true >/dev/null 2>&1
L=~/Developer/pw_android_probe/${TAG}_batch40_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkeyguard\tlabel\tfile" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; D0="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1"; W=/data/data/com.kyle.pwprobe/files/wgsl
envfor(){ case $1 in default) echo "$D0";; nomerge) echo "$D0;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/a3_nomerge.wgsl";; noload) echo "$D0;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/a3_noload.wgsl";; notail) echo "$D0;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/a3_notail.wgsl";; w128ks3) echo "$D0;${P}DIRECT_NOW64=1;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/w128_ks3_ptr.wgsl";; nokeyscan) echo "$D0;${P}DIRECT_NOKEYSCAN=1";; esac; }
i=0; for a in default nomerge noload notail w128ks3 nokeyscan default w128ks3 nomerge default; do
  i=$((i+1)); arm=${a}_$i; ex="$(envfor $a)"
  adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; k=$(kg)
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); lb=$(echo "$out" | grep -oE "blocked\([^)]*\)" | head -1); fu=$(echo "$out" | grep -oE "WGSL_FILE [^ ]+ (len=[0-9]+|open failed)" | head -1 | sed -E 's#.*/##')
  echo -e "$TAG $arm\t${ms:-FAIL}\t${sha:-?}\t$k\t$lb\t$fu" | tee -a $L; sleep 15
done
echo "BATCH40_DONE $L"
