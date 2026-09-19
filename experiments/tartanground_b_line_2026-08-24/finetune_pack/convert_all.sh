#!/usr/bin/env bash
# 把 sel/*.json 里选中的 TG 白墙帧,逐 scan 过官方格式转换器。
#
# 用法: bash convert_all.sh [OUT_ROOT] [OUT_W] [OUT_H] [PARALLEL]
# 默认: OUT_ROOT=finetune_pack/tg_mvs  OUT_W=768 OUT_H=576 PARALLEL=4
#
# 🔴 OUT_W/OUT_H 必须与 BlendedMVG 的图像尺寸一致:datasets/blend.py 全程不 resize,
#    DataLoader 默认 collate 要求同 batch 内张量同形状。租用机上先量,再决定要不要重跑。
set -u
BASE=/Users/kaidongwang/Developer/tartanground_b_line
PACK=$BASE/finetune_pack
OUT_ROOT=${1:-$PACK/tg_mvs}
OUT_W=${2:-768}
OUT_H=${3:-576}
PAR=${4:-4}

mkdir -p "$OUT_ROOT" "$PACK/logs_convert"

# scan 前缀 -> 原始数据目录 的映射
srcdir_for() {
  case "$1" in
    tg_office_p0000_*) echo "$BASE/raw_download/unzipped:image/image_lcam_front:depth/depth_lcam_front:metadata/pose_lcam_front.txt" ;;
    tg_office_p0001_*) echo "$PACK/unz/Office_P0001:image_lcam_front:depth_lcam_front:metadata/pose_lcam_front.txt" ;;
    tg_house_p0000_*)  echo "$PACK/unz/House_P0000:image_lcam_front:depth_lcam_front:metadata/pose_lcam_front.txt" ;;
    tg_house_p0001_*)  echo "$PACK/unz/House_P0001:image_lcam_front:depth_lcam_front:metadata/pose_lcam_front.txt" ;;
    tg_house_p0002_*)  echo "$PACK/unz/House_P0002:image_lcam_front:depth_lcam_front:metadata/pose_lcam_front.txt" ;;
    *) echo "" ;;
  esac
}

running=0
for j in "$PACK"/sel/*_c[0-9][0-9].json; do
  scan=$(basename "$j" .json)
  spec=$(srcdir_for "$scan")
  if [ -z "$spec" ]; then echo "[skip] 未知 scan 前缀: $scan"; continue; fi
  root=${spec%%:*}; rest=${spec#*:}
  imgd=${rest%%:*}; rest=${rest#*:}
  depd=${rest%%:*}; posef=${rest#*:}

  if [ -f "$OUT_ROOT/$scan/conversion_meta.json" ]; then
    echo "[skip] $scan 已转换"; continue
  fi

  echo "[run] $scan"
  python3.11 "$BASE/tartanground2mvsnet.py" \
    --image_dir "$root/$imgd" \
    --depth_dir "$root/$depd" \
    --pose_file "$root/$posef" \
    --out_root "$OUT_ROOT" --scan_name "$scan" \
    --frame_ids_json "$j" --max_frames 0 \
    --out_w "$OUT_W" --out_h "$OUT_H" --num_src 10 \
    > "$PACK/logs_convert/$scan.log" 2>&1 &

  running=$((running+1))
  if [ "$running" -ge "$PAR" ]; then wait -n 2>/dev/null || wait; running=$((running-1)); fi
done
wait

# 转换器每次都会覆盖 lists/train.txt(只写自己那一行),这里统一重建全量清单
ls -1 "$OUT_ROOT" | grep -E '^tg_(office|house)_p[0-9]{4}_c[0-9]{2}$' | sort > "$OUT_ROOT/lists_all_scans.txt"
mkdir -p "$OUT_ROOT/lists"
cp "$OUT_ROOT/lists_all_scans.txt" "$OUT_ROOT/lists/train.txt"
echo "[done] 共 $(wc -l < "$OUT_ROOT/lists_all_scans.txt") 个 scan -> $OUT_ROOT/lists_all_scans.txt"
