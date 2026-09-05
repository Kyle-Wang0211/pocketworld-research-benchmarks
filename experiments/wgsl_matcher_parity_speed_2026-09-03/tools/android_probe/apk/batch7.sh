#!/bin/bash
# 第七批:8x4 能否靠 SCANMEM+NOPB 挤进 64 寄存器线;最优 44 组合 + chunk_off。13312²。
cd "$(dirname "$0")"; REPS=${1:-1}
L=~/Developer/pw_android_probe/mate10_batch7_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkernel\tbuild" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; C=OFFICIAL_AETHER_MATCH_CHUNK_TARGET_MS; D8="${P}DIRECT=1"; D4="${P}DIRECT=1;${P}44=1"
for spec in "sm84nopb|$D8;${P}DIRECT_SCANMEM=1;${P}DIRECT_NOPB=1" "sm84nopbtex|$D8;${P}DIRECT_SCANMEM=1;${P}DIRECT_NOPB=1;${P}DIRECT_TEX=1" "sm84nopbtexa|$D8;${P}DIRECT_SCANMEM=1;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1" "best44_ref|$D4;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1" "best44+chunk_off|$D4;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1;${C}=0" "best44+chunk64|$D4;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1;${C}=64" "sm84nopb_again|$D8;${P}DIRECT_SCANMEM=1;${P}DIRECT_NOPB=1" "best44_again|$D4;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1"; do
  arm=${spec%%|*}; ex=${spec#*|}
  out=$(./run_apk.sh 13312 $REPS "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); k=$(echo "$out" | grep -oE "backend=[^ ]+" | head -1); bid=$(echo "$out" | grep -oE "^BUILD_ID [0-9a-f]+" | cut -d' ' -f2); bad=$(echo "$out" | grep -q "BUILD_ID 不一致" && echo " STALE")
  echo -e "$arm\t${ms:-FAIL}\t${sha:-?}\t$k\t${bid:-?}$bad" | tee -a $L; sleep 15
done
echo "BATCH7_DONE $L"
