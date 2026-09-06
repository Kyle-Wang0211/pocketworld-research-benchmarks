#!/bin/bash
# 第二十三批(锁屏态,只看比值):ref 夹每一臂,WAKEUP 每臂前,15 s 间隔;臂:ks2 / ks2_ptr。thermalservice 温度记进表。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-192.168.1.11:5555}; d=$PW_ADB_SERIAL
L=~/Developer/pw_android_probe/mate10_batch23_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tgpu_C\tcl1_C\tkeyguard\tchain" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; F="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1;${P}DIRECT_W64=1;${P}DIRECT_KEYSCAN=1"; W=/data/data/com.kyle.pwprobe/files/wgsl
i=0; for a in ref ks2 ref ks2_ptr ref ks2 ref ks2_ptr ref; do
  i=$((i+1)); arm=${a}_$i; if [ "$a" = ref ]; then ex="$F"; else ex="$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/aprime_$a.wgsl"; fi
  adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
  th=$(adb -s $d shell dumpsys thermalservice 2>/dev/null | grep -E 'mName=gpu|mName=cluster1' | head -2 | grep -oE 'mValue=[0-9.]+' | cut -d= -f2 | tr '\n' ' '); kg=$(adb -s $d shell dumpsys window 2>/dev/null | grep -oE 'Keyguard=[a-z]+' | head -1 | cut -d= -f2)
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); ch=$(echo "$out" | grep -oE "WGSL_FILE[^\n]{0,80}|锚点失配[^\n]{0,30}|error[^\n]{0,60}" | head -1)
  echo -e "Mate10 $arm\t${ms:-FAIL}\t${sha:-?}\t${th% *}\t${th#* }\t$kg\t$ch" | tee -a $L; sleep 15
done
echo "BATCH23_DONE $L"
