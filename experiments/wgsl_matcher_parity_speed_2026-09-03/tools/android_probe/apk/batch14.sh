#!/bin/bash
# 第十四批:f16 + 4x4 + W128 下的预取形态(两端都不赔的那个)。13312²。
cd "$(dirname "$0")"; export PW_ADB_SERIAL=${PW_ADB_SERIAL:-D3H7N18328002468}
while pgrep -f "batch13|run_apk.sh 13312" >/dev/null; do sleep 5; done
L=~/Developer/pw_android_probe/mate10_batch14_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkernel" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; F="${P}DIRECT=1;${P}44=1;${P}DIRECT_W128=1;${P}DIRECT_F16=1"
for spec in "f16_w128_ref|$F" "f16_w128_pipea|$F;${P}DIRECT_NOPB=1;${P}DIRECT_PIPEA=1" "f16_w128_sm|$F;${P}DIRECT_SCANMEM=1" "f16_w128_nopb_sm|$F;${P}DIRECT_NOPB=1;${P}DIRECT_SCANMEM=1" "f16_w128_nopb_unroll2|$F;${P}DIRECT_NOPB=1;${P}DIRECT_UNROLL=2" "f16_w128_fma|$F;${P}DIRECT_FMA=1" "f16_w128_ref_again|$F" "f16_w128_pipea_again|$F;${P}DIRECT_NOPB=1;${P}DIRECT_PIPEA=1"; do
  arm=${spec%%|*}; ex=${spec#*|}; out=$(./run_apk.sh 13312 1 "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); k=$(echo "$out" | grep -oE "backend=[^ ]+" | head -1)
  echo -e "Mate10 $arm\t${ms:-FAIL}\t${sha:-?}\t$k" | tee -a $L; sleep 15
done
echo "BATCH14_DONE $L"
