#!/bin/bash
# 边下边转边删。🔴 场景跨 shard 切分,故批间重叠 1 个 shard(上批保留末尾那个 tar)。
set -u
PY=/venv/main/bin/python
for b in 0 1 2 3; do
  lo=$((20 + b*20)); hi=$((lo + 20))
  echo "=== batch $b : shards $lo..$((hi-1)) ===" 
  $PY -u /root/sp_fetch.py $lo $hi || exit 1
  prev=$((lo-1))
  TARS=""
  [ -f /root/sp_raw/shard-$(printf %06d $prev).tar ] && TARS="/root/sp_raw/shard-$(printf %06d $prev).tar"
  for i in $(seq $lo $((hi-1))); do TARS="$TARS /root/sp_raw/shard-$(printf %06d $i).tar"; done
  $PY -u /root/sp2mvsnet.py --tars $TARS --out /root/monotrain || exit 1
  # 删本批 tar,但保留最后一个供下批做重叠
  [ -f /root/sp_raw/shard-$(printf %06d $prev).tar ] && rm -f /root/sp_raw/shard-$(printf %06d $prev).tar
  for i in $(seq $lo $((hi-2))); do rm -f /root/sp_raw/shard-$(printf %06d $i).tar; done
  echo "batch $b done: $(ls -d /root/monotrain/sp_scene_* | wc -l) 场景, df: $(df -h / | tail -1 | awk "{print \$4}")"
done
echo "ALL DONE: $(ls -d /root/monotrain/sp_scene_* | wc -l) 场景"
