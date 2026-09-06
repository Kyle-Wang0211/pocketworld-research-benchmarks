#!/bin/bash
# 第十九批:A′(W64+KEYSCAN)在 Mate 10 上的段账,全部走 WGSL_FILE 推文件、不装 app。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-192.168.1.11:5555}
adb -s $PW_ADB_SERIAL shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
L=~/Developer/pw_android_probe/mate10_batch19_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tchain" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; F="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1;${P}DIRECT_W64=1;${P}DIRECT_KEYSCAN=1"; W=/data/data/com.kyle.pwprobe/files/wgsl
for spec in "aprime_env|$F" "aprime_file|$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/aprime.wgsl" "aprime_nomerge|$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/aprime_nomerge.wgsl" "aprime_noload|$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/aprime_noload.wgsl" "aprime_noscan|$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/aprime_noscan.wgsl" "aprime_env_2|$F"; do
  arm=${spec%%|*}; ex=${spec#*|}; out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); ch=$(echo "$out" | grep -oE "(W64|KEYSCAN|WGSL_FILE)[^\[]*applied=[01]|WGSL_FILE[^\n]{0,60}|锚点失配[^\n]{0,30}|error[^\n]{0,60}" | sed -E 's/ in=[0-9]+ out=[0-9]+//' | head -4 | tr '\n' '|')
  echo -e "Mate10 $arm\t${ms:-FAIL}\t${sha:-?}\t$ch" | tee -a $L; sleep 15
done
echo "BATCH19_DONE $L"
