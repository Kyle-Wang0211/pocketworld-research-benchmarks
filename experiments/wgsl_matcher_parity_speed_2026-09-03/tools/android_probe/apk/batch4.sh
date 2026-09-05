#!/bin/bash
# 第四批:8x4 能否不溢出(NOPB)+ 44 的延迟隐藏(PIPEA),13312²。用法: batch4.sh [reps]
cd "$(dirname "$0")"; REPS=${1:-1}
L=~/Developer/pw_android_probe/mate10_batch4_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkernel" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_
for spec in "nopb84|${P}DIRECT=1;${P}DIRECT_NOPB=1" "nopb84tex|${P}DIRECT=1;${P}DIRECT_NOPB=1;${P}DIRECT_TEX=1" "nopipeb_lds84|${P}NOPIPEB=1" "pipea44|${P}DIRECT=1;${P}44=1;${P}DIRECT_PIPEA=1" "pipea44tex|${P}DIRECT=1;${P}44=1;${P}DIRECT_PIPEA=1;${P}DIRECT_TEX=1" "nopb44|${P}DIRECT=1;${P}44=1;${P}DIRECT_NOPB=1" "nopb44tex|${P}DIRECT=1;${P}44=1;${P}DIRECT_NOPB=1;${P}DIRECT_TEX=1" "direct44tex_ref|${P}DIRECT=1;${P}44=1;${P}DIRECT_TEX=1" "nopb84_again|${P}DIRECT=1;${P}DIRECT_NOPB=1" "base_ref|"; do
  arm=${spec%%|*}; ex=${spec#*|}
  out=$(./run_apk.sh 13312 $REPS "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); k=$(echo "$out" | grep -oE "backend=[^ ]+" | head -1); bid=$(echo "$out" | grep -oE "^BUILD_ID [0-9a-f]+" | cut -d' ' -f2); bad=$(echo "$out" | grep -c "BUILD_ID 不一致")
  echo -e "$arm\t${ms:-FAIL}\t${sha:-?}\t$k\tbuild=${bid:-?}${bad:+ STALE}" | tee -a $L; sleep 15
done
echo "BATCH4_DONE $L"
