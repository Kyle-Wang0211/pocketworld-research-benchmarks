#!/bin/bash
# ARKitScenes 逐视频: 官方 download_data.py 拉 4 个 raw 资产 -> arkit2blend.py -> 删 raw。
# 用法: arkit_stream.sh <Training|Validation> <video_id 列表文件> <并行数>
# 已有 ak_<vid>/cams/pair.txt 的直接跳过 (断点续跑)。第一个视频先串行跑, 让 metadata.csv 落盘后再并行。
set -u
SPLIT=$1; LIST=$2; NPAR=${3:-4}
RAW=/root/arkit_raw; OUT=/root/arkit_blend; PY=/venv/main/bin/python
mkdir -p "$RAW" "$OUT"
one() {
  vid=$1
  [ -f "$OUT/ak_$vid/cams/pair.txt" ] && { echo "[skip] $vid"; return 0; }
  ( cd /root/ARKitScenes && $PY download_data.py raw --split "$SPLIT" --video_id "$vid" --download_dir "$RAW" \
      --raw_dataset_assets vga_wide vga_wide_intrinsics lowres_depth lowres_wide.traj ) > "$RAW/$vid.dl.log" 2>&1 \
    || { echo "[dl fail] $vid: $(tail -1 $RAW/$vid.dl.log)"; return 1; }
  $PY /root/arkit2blend.py --raw "$RAW/raw/$SPLIT" --out "$OUT" --vids "$vid" 2>&1 | grep -E "ak_|SKIP"
  rm -rf "$RAW/raw/$SPLIT/$vid" "$RAW/$vid.dl.log"
}
export -f one; export SPLIT RAW OUT PY
first=$(head -1 "$LIST"); one "$first"
tail -n +2 "$LIST" | xargs -P "$NPAR" -I{} bash -c 'one {}'
echo "[done] $(ls -d $OUT/ak_* 2>/dev/null | wc -l) scans"
