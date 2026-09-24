#!/bin/bash
# 单变量:关掉全局接缝校平,看整体亮度是否回到照片水平。其余参数与主跑逐字相同。
set -u
B=/root/texrecon_build/build/apps/texrecon/texrecon
rm -rf /root/texrecon_noglobal; mkdir -p /root/texrecon_noglobal
$B --skip_global_seam_leveling /root/texrecon_scene /root/texrecon_scene_mesh.ply /root/texrecon_noglobal/poisson
echo rc=$?
touch /root/TEXABL_DONE
