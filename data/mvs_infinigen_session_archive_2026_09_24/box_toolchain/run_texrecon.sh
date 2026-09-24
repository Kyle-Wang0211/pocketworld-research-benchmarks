#!/bin/bash
# texrecon 给 Poisson 网格贴图。全部走默认参数 = Waechter 2014 的官方配方,不自调。
# 场景: /root/texrecon_scene (132 个 .cam + 132 张 sRGB PNG, 序号映射由相机中心比对钉死)
# 网格: C_filt/mesh_aligned.obj (Poisson depth=11 + 裁 2% + 官方 meshFiltering + Sim3 搬正)
set -u
B=/root/texrecon_build/build/apps/texrecon/texrecon
rm -rf /root/texrecon_out; mkdir -p /root/texrecon_out
echo "[$(date +%H:%M:%S)] start"
$B /root/texrecon_scene /root/texrecon_scene_mesh.ply /root/texrecon_out/poisson
echo "[$(date +%H:%M:%S)] rc=$?"
ls -la /root/texrecon_out/
touch /root/TEXRECON_RUN_DONE
