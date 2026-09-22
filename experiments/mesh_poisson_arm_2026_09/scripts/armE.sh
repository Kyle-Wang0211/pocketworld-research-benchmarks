#!/bin/bash
# Arm E: 公平对照 —— 与 ①② 同一份 2016x1504 过滤深度, 与 ③ 同一个 Poisson 配方(depth=11, 裁最低 2%)和同样的点数。
#   vs A/D: 同输入深度, 只换成网方法  =>  隔离「方法」
#   vs C  : 同方法同点数, 只换源分辨率(768 -> 2016) =>  隔离「输入分辨率」
set -u
R=/root/av_ep0_off; AV=/root/meshroom2023/Meshroom-2023.3.0/aliceVision
export ALICEVISION_ROOT=$AV; export LD_LIBRARY_PATH=$AV/lib
PY=/venv/main/bin/python
log(){ echo "[$(date +%H:%M:%S)] $*"; }
mkdir -p $R/E $R/E_filt
log 'E/1 反投影过滤深度 -> 点云(官方 SfM 帧), 抽到 36,232,793 点 = arm C 同数'
$PY /root/unproject_filt.py $R/filt $R/prep $R/scene_dense.sfm $R/E/cloud.ply 36232793 || { touch $R/E_FAILED; exit 1; }
log 'E/2 Poisson depth=11 + 裁最低 2%(逐字复用 09-17 的 poisson_ep0.py)'
$PY $R/poisson_ep0.py $R/E/cloud.ply $R/scene_dense.sfm $R/E/poisson.ply 11 0.02 || { touch $R/E_FAILED; exit 1; }
log 'E/3 ply -> obj'
$AV/bin/aliceVision_convertMesh --input $R/E/poisson.ply --output $R/E/poisson.obj --verboseLevel info > $R/E_conv.log 2>&1
echo "  rc=$?"
log 'E/4 官方 meshFiltering(与 A/D/C 同参)'
$AV/bin/aliceVision_meshFiltering --inputMesh $R/E/poisson.obj --outputMesh $R/E_filt/mesh.obj   --keepLargestMeshOnly 0 --smoothingSubset all --smoothingBoundariesNeighbours 0 --smoothingIterations 5   --smoothingLambda 1.0 --filteringSubset all --filteringIterations 1 --filterLargeTrianglesFactor 60.0   --filterTrianglesRatio 0.0 --verboseLevel info > $R/E_meshfilt.log 2>&1
echo "  rc=$? $(grep -i 'Output mesh' $R/E_meshfilt.log)"
log 'E/5 y,z 反号搬进 OBJ 帧(与 A/D/C 一致; 自证过 A_filt 顶点到云 p50 1.2mm)'
$PY - <<'PYEOF'
import sys
src='/root/av_ep0_off/E_filt/mesh.obj'; dst='/root/av_ep0_off/E_filt/mesh_objframe.obj'
n=0
with open(src,errors='ignore') as f, open(dst,'w') as g:
    for ln in f:
        if ln.startswith('v ') or ln.startswith('vn '):
            k,a,b,c=ln.split()[:4]
            g.write(f'{k} {a} {-float(b):.6f} {-float(c):.6f}\n'); n+= (k=='v')
        else: g.write(ln)
print('flipped vertices', n)
PYEOF
log 'E DONE'; touch $R/E.DONE
