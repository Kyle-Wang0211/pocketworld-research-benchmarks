#!/bin/bash
# SimpleProc 全量: 边下边转边删, 20 shard 一批, 批间重叠 1 个 shard (场景跨 shard, 与 sp_pipeline.sh 同)。
# 盘剩余 < MINFREE GB 时停下, 把下一批起点写进 /root/sp_stream.next (新机上从这里接着跑)。
set -u
set -o pipefail
PY=/venv/main/bin/python
LOG=/root/sp_stream.log
exec >> "$LOG" 2>&1
START=${1:-20}; END=${2:-895}; MINFREE=${MINFREE:-120}
echo "=== [$(date +%m-%d\ %H:%M)] sp_stream $START..$((END-1)) MINFREE=${MINFREE}G ==="
for ((lo=START; lo<END; lo+=20)); do
  hi=$((lo+20)); [ $hi -gt $END ] && hi=$END
  free=$(df -BG / | awk 'NR==2{print $4}' | tr -d G)
  if [ "$free" -lt "$MINFREE" ]; then
    echo "[stop] free=${free}G < ${MINFREE}G; 下一批从 shard $lo 起"; echo "$lo" > /root/sp_stream.next; exit 0
  fi
  echo "--- [$(date +%H:%M)] shards $lo..$((hi-1))  free=${free}G ---"
  $PY -u /root/sp_fetch_par.py $lo $hi | tail -2 || { echo "[fetch fail] batch $lo"; exit 1; }
  prev=$((lo-1)); TARS=""
  f=/root/sp_raw/shard-$(printf %06d $prev).tar; [ -f "$f" ] && TARS="$f"
  for i in $(seq $lo $((hi-1))); do TARS="$TARS /root/sp_raw/shard-$(printf %06d $i).tar"; done
  $PY -u /root/sp2mvsnet.py --tars $TARS --out /root/monotrain | tail -3 || { echo "[convert fail] batch $lo"; exit 1; }
  for i in $(seq $prev $((hi-2))); do rm -f /root/sp_raw/shard-$(printf %06d $i).tar; done   # 留本批最后一个给下批 carry
  echo "[batch $lo done $(date +%H:%M)] 盘上场景 $(ls -d /root/monotrain/sp_scene_* | wc -l)"
  echo "$hi" > /root/sp_stream.next
done
echo "[all done $(date +%H:%M)]"
