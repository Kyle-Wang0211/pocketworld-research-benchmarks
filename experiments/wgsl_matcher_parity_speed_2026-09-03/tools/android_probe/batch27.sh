#!/bin/bash
# 第二十七批(接 batch26 后):ref / u8 / ref / u8 / ref,逐字节同,15 s 间隔。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-192.168.1.11:5555}; d=$PW_ADB_SERIAL
kg(){ adb -s $d shell dumpsys window 2>/dev/null | grep -oE 'isStatusBarKeyguard=[a-z]+' | head -1 | cut -d= -f2; }
adb -s $d shell svc power stayon true >/dev/null 2>&1
L=~/Developer/pw_android_probe/mate10_batch27_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkeyguard\tchain" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; F="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1;${P}DIRECT_W64=1;${P}DIRECT_KEYSCAN=1"; W=/data/data/com.kyle.pwprobe/files/wgsl
i=0; for a in aprime_ks2_ptr aprime_ks2_ptr_u8 aprime_ks2_ptr aprime_ks2_ptr_u8 aprime_ks2_ptr; do
  i=$((i+1)); arm=${a}_$i; ex="$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/$a.wgsl"
  adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; k=$(kg)
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); ch=$(echo "$out" | grep -oE "WGSL_FILE[^\n]{0,80}|锚点失配[^\n]{0,30}|error[^\n]{0,60}" | head -1)
  echo -e "Mate10 $arm\t${ms:-FAIL}\t${sha:-?}\t$k\t$ch" | tee -a $L; sleep 15
done
echo "BATCH26_DONE $L"
