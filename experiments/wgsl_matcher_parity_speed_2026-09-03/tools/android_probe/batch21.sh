#!/bin/bash
# 第二十一批:A′ vs A′+KEYSCAN2,ABBA,每臂间隔 60 s,全程采样 GPU 频率(cur_freq)记 max/众数 —— 09-06 中午 batch20 撞上热降频(ref 600→2100)。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-192.168.1.11:5555}; d=$PW_ADB_SERIAL
adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
L=~/Developer/pw_android_probe/mate10_batch21_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tgpu_mhz_max\tgpu_mhz_mode\tbatt_dC\tchain" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; F="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1;${P}DIRECT_W64=1;${P}DIRECT_KEYSCAN=1"; W=/data/data/com.kyle.pwprobe/files/wgsl
for spec in "aprime|$F" "aprime_ks2|$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/aprime_ks2.wgsl" "aprime_ks2_2|$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/aprime_ks2.wgsl" "aprime_2|$F" "aprime_3|$F" "aprime_ks2_3|$F;OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=$W/aprime_ks2.wgsl"; do
  arm=${spec%%|*}; ex=${spec#*|}
  bt=$(adb -s $d shell dumpsys battery | grep -oE 'temperature: [0-9]+' | grep -oE '[0-9]+')
  adb -s $d shell 'while :; do cat /sys/class/devfreq/gpufreq/cur_freq; sleep 0.1; done' > /private/tmp/gpufreq_$arm.txt 2>/dev/null & sp=$!
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1); kill $sp 2>/dev/null; wait $sp 2>/dev/null
  fmax=$(sort -n /private/tmp/gpufreq_$arm.txt | tail -1); fmode=$(sort /private/tmp/gpufreq_$arm.txt | uniq -c | sort -rn | head -1 | awk '{print $2}')
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); ch=$(echo "$out" | grep -oE "WGSL_FILE[^\n]{0,70}|锚点失配[^\n]{0,30}|error[^\n]{0,60}" | head -2 | tr '\n' '|')
  echo -e "Mate10 $arm\t${ms:-FAIL}\t${sha:-?}\t$((${fmax:-0}/1000000))\t$((${fmode:-0}/1000000))\t${bt:-?}\t$ch" | tee -a $L; sleep 60
done
echo "BATCH21_DONE $L"
