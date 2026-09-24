#!/bin/bash
# 只取 lowres_wide.traj (244 KB) + vga_wide_intrinsics.zip (~1.4 MB) 就能【不下任何图】
# 精确算出 v2 的 有位姿帧数 / 关键帧数: 帧集合 = vga_wide_intrinsics 的文件名时间戳
# (实测与 vga_wide 一一对应, 41048190: 7557 == 7557), 位姿全部来自 traj。
# 用法: ak2_project.sh <ids file: "vid split" 每行> <out tsv>
set -u
U=https://docs-assets.developer.apple.com/ml-research/datasets/arkitscenes/v1
D=/root/ak2_proj; mkdir -p "$D"
one(){ read -r v s <<< "$1"
  [ -f "$D/$v.ts" ] && return 0
  curl -s --max-time 120 --fail "$U/raw/$s/$v/lowres_wide.traj" -o "$D/$v.traj" || return 1
  curl -s --max-time 300 --fail "$U/raw/$s/$v/vga_wide_intrinsics.zip" -o "$D/$v.zip" || return 1
  unzip -Z1 "$D/$v.zip" 2>/dev/null | sed -n "s#.*/${v}_\(.*\)\.pincam#\1#p" | sort -n > "$D/$v.ts.tmp"
  mv "$D/$v.ts.tmp" "$D/$v.ts"; rm -f "$D/$v.zip"; }
export -f one; export U D
xargs -P 12 -I{} bash -c 'one "{}"' < "$1"
echo "[fetched] $(ls $D/*.ts 2>/dev/null | wc -l)"
