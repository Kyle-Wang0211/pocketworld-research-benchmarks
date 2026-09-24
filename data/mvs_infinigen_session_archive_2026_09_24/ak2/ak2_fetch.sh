#!/bin/bash
# 取 v2 需要的 raw 资产。URL 拼法逐字照 download_data.py:7,176,193-200:
#   {ARkitscense_url}/raw/{split}/{video_id}/{file_name}  ->  curl --fail  ->  unzip -oq  ->  删 zip
# 🔴 偏离 D4: wide / wide_intrinsics 不在 download_data.py:13-15 的 choices 里 (所以不能
#    用官方 CLI 取), 但 raw/README.md 正文把它们列为 raw 的正式资产, 且同一个 URL 前缀下
#    实测 HTTP 200。其余资产 (highres_depth / lowres_wide.traj / vga_wide / lowres_depth /
#    vga_wide_intrinsics) 与官方 CLI 取到的是同一批文件。
# 用法: ak2_fetch.sh <Training|Validation> <video_id> <dst_root> <asset...>
set -eu
U=https://docs-assets.developer.apple.com/ml-research/datasets/arkitscenes/v1
SPLIT=$1; VID=$2; DST=$3/raw/$1/$2; shift 3
mkdir -p "$DST"
for a in "$@"; do
  case "$a" in
    lowres_wide.traj) f=lowres_wide.traj ;;
    *)                f=$a.zip ;;
  esac
  [ -e "$DST/${f%.zip}" ] && [ "$f" != "lowres_wide.traj" ] && { echo "[have] $VID/$a"; continue; }
  [ -f "$DST/$f" ] && [ "$f" = "lowres_wide.traj" ] && { echo "[have] $VID/$a"; continue; }
  curl -s "$U/raw/$SPLIT/$VID/$f" -o "$DST/$f.tmp" --fail || { echo "[dl fail] $VID/$a"; exit 1; }
  mv "$DST/$f.tmp" "$DST/$f"
  case "$f" in *.zip) unzip -oq "$DST/$f" -d "$DST" && rm -f "$DST/$f" ;; esac
done
