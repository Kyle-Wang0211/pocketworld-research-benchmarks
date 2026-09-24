#!/bin/bash
# 抄 GauStudio README 的 texrecon 参数(它是 KIRI 官方指向的上游, 商用产品关联):
#   --outlier_removal=gauss_clamping --data_term=area
# 我们主跑用的是默认 none / gmi。唯一变量就是这两个。
set -u
B=/root/texrecon_build/build/apps/texrecon/texrecon
rm -rf /root/texrecon_gaus; mkdir -p /root/texrecon_gaus
$B --outlier_removal=gauss_clamping --data_term=area    /root/texrecon_scene /root/texrecon_scene_mesh.ply /root/texrecon_gaus/poisson
echo rc=$?
touch /root/TEXGAUS_DONE
