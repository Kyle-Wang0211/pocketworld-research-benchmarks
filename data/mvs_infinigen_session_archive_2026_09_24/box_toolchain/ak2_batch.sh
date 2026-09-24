#!/bin/bash
# 批量: 逐视频 取资产 -> 转换 -> 立刻删 raw。8 路并行。
# 用法: ak2_batch.sh <ids文件: "vid split" 每行> <highres|lowres> [并行数]
#
# 硬闸 (用户指令):
#   - 每个视频【下载前】查一次剩余空间, < MIN_FREE_GB 立刻 touch STOP 并退出
#   - STOP 文件存在时所有 worker 立即停手 (不再开新视频)
#   - raw 中间产物逐个用完即删 (zip 在 ak2_fetch.sh 里解压后就删, 解压目录在本脚本删)
#   - GPU 一律不碰 (本脚本只有 curl / unzip / numpy-cv2 的 CPU 路径)
set -u
LIST=$1; MODE=$2; NPAR=${3:-8}
RAW=/root/ak2_batch_raw; OUT=/root/ak_blend_v2; PY=/venv/main/bin/python
STOP=/root/AK2_STOP; MIN_FREE_GB=150
mkdir -p "$RAW"; rm -f "$STOP"
if [ "$MODE" = highres ]; then A="lowres_wide.traj wide wide_intrinsics highres_depth"
else A="lowres_wide.traj vga_wide vga_wide_intrinsics lowres_depth"; fi

freegb(){ df -BG --output=avail /root | tail -1 | tr -dc '0-9'; }

one(){
  read -r v s <<< "$1"
  [ -f "$STOP" ] && return 0
  [ -f "$OUT/ak_$v/cams/pair.txt" ] && { echo "[skip-done] $v"; return 0; }
  f=$(freegb)
  if [ "$f" -lt "$MIN_FREE_GB" ]; then
    echo "[STOP] 剩余空间 ${f} GB < ${MIN_FREE_GB} GB, 在 $v 之前停手" | tee -a /root/ak2_batch_stop.txt
    touch "$STOP"; return 1
  fi
  t0=$(date +%s)
  if ! timeout 1800 /root/ak2_fetch.sh "$s" "$v" "$RAW" $A > "$RAW/$v.dl" 2>&1; then
    echo "[FAIL-dl] $v $s : $(tail -1 "$RAW/$v.dl" 2>/dev/null)" | tee -a /root/ak2_batch_fail.txt
    rm -rf "${RAW:?}/raw/$s/$v" "$RAW/$v.dl"; return 0
  fi
  t1=$(date +%s)
  rawmb=$(du -sm "$RAW/raw/$s/$v" 2>/dev/null | cut -f1)
  out=$(timeout 3600 $PY /root/arkit2blend_v2.py --raw "$RAW/raw/$s" --out "$OUT" \
          --vids "$v" --depth "$MODE" 2>&1 | grep -E "ak_|SKIP")
  rc=$?
  t2=$(date +%s)
  [ -z "$out" ] && { echo "[FAIL-conv] $v $s rc=$rc" | tee -a /root/ak2_batch_fail.txt; }
  echo "$out"
  nf=$(ls "$OUT/ak_$v/blended_images" 2>/dev/null | wc -l)
  mb=$(du -sm "$OUT/ak_$v" 2>/dev/null | cut -f1); mb=${mb:-0}
  echo "    [res] $v $MODE dl=$((t1-t0))s conv=$((t2-t1))s raw=${rawmb:-0}MB out=${mb}MB frames=$nf free=$(freegb)GB"
  rm -rf "${RAW:?}/raw/$s/$v" "$RAW/$v.dl"
}
export -f one freegb; export RAW OUT PY STOP MIN_FREE_GB A MODE
echo "[batch start $(date +%H:%M:%S)] $(wc -l < "$LIST") 个视频, mode=$MODE, 并行 $NPAR, 起始剩余 $(freegb) GB"
xargs -P "$NPAR" -I{} bash -c 'one "{}"' < "$LIST"
echo "[batch end $(date +%H:%M:%S)] 场景总数 $(ls -d $OUT/ak_* 2>/dev/null | wc -l), 剩余 $(freegb) GB"
[ -f "$STOP" ] && echo "[!!] 因磁盘硬闸提前停止"
rm -rf "${RAW:?}/raw" 2>/dev/null
exit 0
