#!/bin/bash
# 第二批:DIRECT 家族 × 分块目标,13312²,逐臂记账。用法: batch2.sh [reps]
cd "$(dirname "$0")"; REPS=${1:-1}
L=~/Developer/pw_android_probe/mate10_batch2_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkernel" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; C=OFFICIAL_AETHER_MATCH_CHUNK_TARGET_MS
for spec in "base|" "direct|${P}DIRECT=1" "direct44|${P}DIRECT=1;${P}44=1" "directg|${P}DIRECT=1;${P}DIRECT_G=1" "direct44g|${P}DIRECT=1;${P}44=1;${P}DIRECT_G=1" "direct+chunk_off|${P}DIRECT=1;${C}=0" "directg+chunk_off|${P}DIRECT=1;${P}DIRECT_G=1;${C}=0" "direct44g+chunk_off|${P}DIRECT=1;${P}44=1;${P}DIRECT_G=1;${C}=0" "directtex|${P}DIRECT=1;${P}DIRECT_TEX=1" "directgtex|${P}DIRECT=1;${P}DIRECT_G=1;${P}DIRECT_TEX=1" "direct44gtex|${P}DIRECT=1;${P}44=1;${P}DIRECT_G=1;${P}DIRECT_TEX=1" "base_again|" "direct_again|${P}DIRECT=1"; do
  arm=${spec%%|*}; ex=${spec#*|}
  out=$(./run_apk.sh 13312 $REPS "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); k=$(echo "$out" | grep -oE "backend=[^ ]+" | head -1)
  echo -e "$arm\t${ms:-FAIL}\t${sha:-?}\t$k" | tee -a $L; sleep 15
done
echo "BATCH2_DONE $L"
