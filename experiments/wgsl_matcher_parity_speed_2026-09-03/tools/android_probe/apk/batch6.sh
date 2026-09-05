#!/bin/bash
# 第六批:SCANMEM(行扫描状态落 RowP,少 3 个跨循环寄存器)× 最优组合,13312²。
cd "$(dirname "$0")"; REPS=${1:-1}
L=~/Developer/pw_android_probe/mate10_batch6_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkernel\tbuild" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; D="${P}DIRECT=1;${P}44=1"
for spec in "nopb44texa_ref|$D;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1" "sm44nopbtexa|$D;${P}DIRECT_SCANMEM=1;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1" "sm44nopbtex|$D;${P}DIRECT_SCANMEM=1;${P}DIRECT_NOPB=1;${P}DIRECT_TEX=1" "sm44nopb|$D;${P}DIRECT_SCANMEM=1;${P}DIRECT_NOPB=1" "sm44|$D;${P}DIRECT_SCANMEM=1" "nopb44tex_ref|$D;${P}DIRECT_NOPB=1;${P}DIRECT_TEX=1" "sm44nopbtexa_again|$D;${P}DIRECT_SCANMEM=1;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1" "nopb44texa_again|$D;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1"; do
  arm=${spec%%|*}; ex=${spec#*|}
  out=$(./run_apk.sh 13312 $REPS "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); k=$(echo "$out" | grep -oE "backend=[^ ]+" | head -1); bid=$(echo "$out" | grep -oE "^BUILD_ID [0-9a-f]+" | cut -d' ' -f2); bad=$(echo "$out" | grep -q "BUILD_ID 不一致" && echo " STALE")
  echo -e "$arm\t${ms:-FAIL}\t${sha:-?}\t$k\t${bid:-?}$bad" | tee -a $L; sleep 15
done
echo "BATCH6_DONE $L"
