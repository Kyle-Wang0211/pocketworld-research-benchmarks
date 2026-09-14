#!/bin/bash
# GSO 的 mtl 写的是 "map_Kd texture.png",但文件在 materials/textures/ 下。
# 在 meshes/ 里补一个软链,让任何 OBJ 加载器都能找到。判据:软链指向的文件必须存在。
M=$1
T=$(find "$M" -name "texture.png" -path "*materials*" | head -1)
[ -z "$T" ] && { echo "  NO_TEXTURE $M"; exit 2; }
ln -sf "$T" "$M/meshes/texture.png"
[ -e "$M/meshes/texture.png" ] || { echo "  LINK_BROKEN $M"; exit 3; }
echo "  TEX_OK $(basename $M)  $(stat -Lc%s "$M/meshes/texture.png") bytes"
