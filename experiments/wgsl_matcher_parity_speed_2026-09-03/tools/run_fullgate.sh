#!/usr/bin/env bash
# run_fullgate.sh — 最终候选全量闸:cap7_day 全部时间 K12 真实对上
# native vs <kernel> 的逐字节 pairs 对拍。
# usage: run_fullgate.sh <kernel> [max_frames]
set -euo pipefail
K="${1:?kernel}"; MAXF="${2:-146}"
B=~/Developer/pw_h2_fullgate_20260902/bin
B=$(eval echo $B)
DB=${FULLGATE_DB:-$HOME/Developer/pw_h2_fullgate_20260902/db51.db}
ROOT=~/Developer/pw_h2_fullgate_20260902
LIB=$ROOT/frames; PAIR=$ROOT/pairwork; LOG=$ROOT/fullgate_${K}.log
mkdir -p "$LIB" "$PAIR"
: > "$LOG"

# 1) 每帧描述子只抽一次(抽 (i,i) 对,a.u8 即该帧)
for ((i=1;i<=MAXF;i++)); do
  d="$LIB/f$i"
  [ -s "$d/a.u8" ] && continue
  mkdir -p "$d"
  "$B/fair_match_extract_fixture" "$DB" "$d" "$i" "$i" >/dev/null 2>&1 || { echo "extract-skip $i" >> "$LOG"; rm -rf "$d"; }
done

# 2) 时间 K12 对:i vs i-1..i-12,native 与候选核各跑 1 rep,比 pairs sha
pass=0; fail=0; skip=0
for ((i=2;i<=MAXF;i++)); do
  for ((j=i-1;j>=i-12 && j>=1;j--)); do
    [ -s "$LIB/f$i/a.u8" ] && [ -s "$LIB/f$j/a.u8" ] || { skip=$((skip+1)); continue; }
    rm -rf "$PAIR"; mkdir -p "$PAIR/n" "$PAIR/p"
    cp "$LIB/f$i/a.u8" "$PAIR/a.u8"; cp "$LIB/f$j/a.u8" "$PAIR/b.u8"
    # 拼合 manifest:行数取各自帧的 rows_a,哈希现算(装载器 fail-closed 校验)
    python3 - "$LIB/f$i/manifest.json" "$LIB/f$j/manifest.json" "$PAIR" <<'PYEOF'
import json,sys,hashlib
mi=json.load(open(sys.argv[1])); mj=json.load(open(sys.argv[2])); d=sys.argv[3]
sha=lambda f: hashlib.sha256(open(f,'rb').read()).hexdigest()
json.dump({"rows_a":mi["rows_a"],"rows_b":mj["rows_a"],
           "sha256_a":sha(d+"/a.u8"),"sha256_b":sha(d+"/b.u8"),"cols":128},
          open(d+"/manifest.json","w"))
PYEOF
    na=$("$B/fair_match_native_arm" "$PAIR" "$PAIR/n" 1 0 0.7 2>/dev/null | grep -o '"pairs_sha256":"[a-f0-9]*"' | head -1)
    po=$("$B/fair_match_portable_arm" "$PAIR" "$PAIR/p" 1 0 0.7 "$K" 2>/dev/null | grep -o '"pairs_sha256":"[a-f0-9]*"' | head -1)
    if [ -n "$na" ] && [ "$na" = "$po" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "MISMATCH i=$i j=$j na=$na po=$po" >> "$LOG"; fi
  done
done
echo "FULLGATE kernel=$K pass=$pass fail=$fail skip=$skip" | tee -a "$LOG"
