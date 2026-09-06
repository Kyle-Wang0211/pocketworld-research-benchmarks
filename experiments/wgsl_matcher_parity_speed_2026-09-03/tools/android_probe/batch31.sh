#!/bin/bash
# 第三十一批:P50 Pocket(PAL-AL00,HarmonyOS 4.2 / Adreno 660)首测:装 APK、推夹具、默认 A″ vs 形态 A,ABBA ×3。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-PHQ0223207007217}; d=$PW_ADB_SERIAL
kg(){ adb -s $d shell dumpsys window 2>/dev/null | grep -oE 'isStatusBarKeyguard=[a-z]+' | head -1 | cut -d= -f2; }
adb -s $d shell svc power stayon true >/dev/null 2>&1; adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
adb -s $d install -r -t out/pwprobe.apk 2>&1 | grep -E "Success|Failure|rror"
adb -s $d shell "run-as com.kyle.pwprobe ls files/fixtures/fx13/a.u8" >/dev/null 2>&1 || { adb -s $d push ~/Developer/pw_android_probe/fx13 /data/local/tmp/pwmatch/fx13 | tail -1; adb -s $d shell "run-as com.kyle.pwprobe sh -c 'mkdir -p files/fixtures && cp -r /data/local/tmp/pwmatch/fx13 files/fixtures/ && ls files/fixtures/fx13 | wc -l'"; }
echo "gpu: $(adb -s $d shell dumpsys SurfaceFlinger 2>/dev/null | grep -oE 'Adreno \(TM\) [0-9]+' | head -1) keyguard=$(kg)"
L=~/Developer/pw_android_probe/p50pocket_batch31_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkeyguard\tlabel" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; A="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1;${P}DIRECT_NOW64=1;${P}DIRECT_NOKEYSCAN=1;${P}DIRECT_NOPTR=1"
i=0; for a in default formA formA default default formA; do
  i=$((i+1)); arm=${a}_$i; if [ "$a" = default ]; then ex="OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1"; else ex="$A"; fi
  adb -s $d shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; k=$(kg)
  out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); lb=$(echo "$out" | grep -oE "blocked\([^)]*\)|adapter[^\n]{0,80}|error[^\n]{0,80}|FAIL[^\n]{0,80}" | head -2 | tr '\n' '|')
  echo -e "P50P $arm\t${ms:-FAIL}\t${sha:-?}\t$k\t$lb" | tee -a $L; sleep 15
done
echo "BATCH31_DONE $L"
