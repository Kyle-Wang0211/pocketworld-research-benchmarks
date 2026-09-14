#!/bin/bash
# 下载并解压 TartanGround 单条轨迹的 image+depth+metadata(单前视相机)
# 用法: tg_fetch_one.sh <Env> <Data_ver> <Pnnnn> <workdir>
set -e
ENV=$1; VER=$2; TRAJ=$3; WD=$4
BASE="https://huggingface.co/datasets/theairlabcmu/TartanGround/resolve/main"
mkdir -p "$WD"
for M in image_lcam_front depth_lcam_front metadata; do
  U="$BASE/$ENV/$VER/$TRAJ/$M.zip"
  F="$WD/$M.zip"
  if [ ! -f "$F" ]; then
    curl -sL --fail -o "$F" "$U" || { echo "FETCH_FAIL $ENV/$VER/$TRAJ/$M"; exit 2; }
  fi
  printf "  %-22s %s bytes\n" "$M.zip" "$(stat -c%s "$F")"
  unzip -oq "$F" -d "$WD" || { echo "UNZIP_FAIL $M"; exit 3; }
done
echo "--- 解压后目录树(两层) ---"
find "$WD" -maxdepth 3 -type d | head -20
echo "--- 文件计数 ---"
find "$WD" -name "*.png" | sed "s#.*/\([^/]*\)/[^/]*\$#\1#" | sort | uniq -c | head
find "$WD" -name "*.txt" -o -name "*.json" -o -name "*.yaml" | head -10
