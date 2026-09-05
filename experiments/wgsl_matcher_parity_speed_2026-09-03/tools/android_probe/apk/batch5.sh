#!/bin/bash
# 第五批:44 形态上 TEXA(A 也走纹理)× NOPB × TEX,13312²。用法: batch5.sh [reps]
cd "$(dirname "$0")"; REPS=${1:-1}
L=~/Developer/pw_android_probe/mate10_batch5_$(date +%m%d_%H%M).tsv; echo -e "arm\tms\tsha12\tkernel\tbuild" > $L
P=OFFICIAL_AETHER_MATCH_DAWN_BLK_; D="${P}DIRECT=1;${P}44=1"
for spec in "nopb44tex_ref|$D;${P}DIRECT_NOPB=1;${P}DIRECT_TEX=1" "texa44|$D;${P}DIRECT_TEXA=1" "nopb44texa|$D;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1" "nopb44texa_tex|$D;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1;${P}DIRECT_TEX=1" "texa44tex|$D;${P}DIRECT_TEXA=1;${P}DIRECT_TEX=1" "pipea44texa_tex|$D;${P}DIRECT_PIPEA=1;${P}DIRECT_TEXA=1;${P}DIRECT_TEX=1" "nopb44_ref|$D;${P}DIRECT_NOPB=1" "nopb44tex_again|$D;${P}DIRECT_NOPB=1;${P}DIRECT_TEX=1" "nopb44texa_tex_again|$D;${P}DIRECT_NOPB=1;${P}DIRECT_TEXA=1;${P}DIRECT_TEX=1"; do
  arm=${spec%%|*}; ex=${spec#*|}
  out=$(./run_apk.sh 13312 $REPS "" "$ex" 900 2>&1)
  ms=$(echo "$out" | grep -oE "p50_ms=[0-9.]+" | cut -d= -f2); sha=$(echo "$out" | grep -oE "sha256=[0-9a-f]{12}" | cut -d= -f2); k=$(echo "$out" | grep -oE "backend=[^ ]+" | head -1); bid=$(echo "$out" | grep -oE "^BUILD_ID [0-9a-f]+" | cut -d' ' -f2); bad=$(echo "$out" | grep -q "BUILD_ID 不一致" && echo " STALE")
  echo -e "$arm\t${ms:-FAIL}\t${sha:-?}\t$k\t${bid:-?}$bad" | tee -a $L; sleep 15
done
echo "BATCH5_DONE $L"
