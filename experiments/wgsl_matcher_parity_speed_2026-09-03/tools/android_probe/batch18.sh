#!/bin/bash
# 第十八批(Mate 10 回来后):KEYSCAN(寄存器预归约+打包键,barrier 仍 2 次、8 KiB 复用)vs 形态 A 默认,交替 3 轮,13312²。
# TU 见 out_build_id.txt(W64 已加)(形态 A 已是默认,不需要 DIRECT/44/W128/F16/NOPB 的 env)。先装 out/pwprobe.apk。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-D3H7N18328002468}
adb -s $PW_ADB_SERIAL shell am force-stop com.kyle.pwprobe >/dev/null 2>&1; adb -s $PW_ADB_SERIAL shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
adb -s $PW_ADB_SERIAL install -r -t out/pwprobe.apk 2>&1 | grep -E "Success|Failure"
L=~/Developer/pw_android_probe/mate10_batch18_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tchain" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; F="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1"
for spec in "A_ref|$F" "A_keyscan|$F;${P}DIRECT_KEYSCAN=1" "A_w64|$F;${P}DIRECT_W64=1" "A_w64_keyscan|$F;${P}DIRECT_W64=1;${P}DIRECT_KEYSCAN=1" "A_keyscan_2|$F;${P}DIRECT_KEYSCAN=1" "A_ref_2|$F" "A_w64_keyscan_2|$F;${P}DIRECT_W64=1;${P}DIRECT_KEYSCAN=1" "A_w64_2|$F;${P}DIRECT_W64=1" "A_ref_3|$F" "A_keyscan_3|$F;${P}DIRECT_KEYSCAN=1"; do
  arm=${spec%%|*}; ex=${spec#*|}; out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); ch=$(echo "$out" | grep -oE "(W64|KEYSCAN|NOPB|F16)[^\[]*applied=[01]|锚点失配[^\n]{0,30}|BUILD_ID 不一致[^\n]{0,40}" | sed -E 's/ in=[0-9]+ out=[0-9]+//' | tr '\n' '|')
  echo -e "Mate10 $arm\t${ms:-FAIL}\t${sha:-?}\t$ch" | tee -a $L; sleep 15
done
echo "BATCH18_DONE $L"
