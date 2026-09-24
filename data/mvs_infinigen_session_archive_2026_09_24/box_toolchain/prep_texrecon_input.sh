#!/bin/bash
# 给 texrecon 备料: prep 的线性 EXR -> sRGB PNG(按 .cam 的序号命名), 网格 obj -> ply
set -eu
AV=/root/meshroom2023/Meshroom-2023.3.0/aliceVision; export ALICEVISION_ROOT=$AV; export LD_LIBRARY_PATH=$AV/lib
log(){ echo "[$(date +%H:%M:%S)] $*"; }
log '1/2 EXR -> PNG(映射来自相机中心比对, 不是猜的)'
/venv/main/bin/python - <<'PY'
import json, os, numpy as np, time
os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
import cv2, OpenEXR
m=json.load(open('/root/texrecon_scene_map.json'))
t0=time.time(); n=0
for cam, vid in sorted(m.items()):
    stem=cam[:-4]
    out=f'/root/texrecon_scene/{stem}.png'
    if os.path.exists(out): n+=1; continue
    with OpenEXR.File(f'/root/av_ep0_off/prep/{vid}.exr') as f:
        ch=f.channels()
        img=np.asarray(ch['RGBA'].pixels,dtype=np.float32)[...,:3] if 'RGBA' in ch else np.asarray(ch['RGB'].pixels,dtype=np.float32)
    img=np.clip(img,0,None)
    s=np.where(img<=0.0031308, img*12.92, 1.055*img**(1/2.4)-0.055)
    cv2.imwrite(out, (np.clip(s,0,1)*255+0.5).astype(np.uint8)[:,:,::-1], [cv2.IMWRITE_PNG_COMPRESSION,3])
    n+=1
    if n%30==0: print(f'  {n}/{len(m)}  ({time.time()-t0:.0f}s)', flush=True)
print(f'  转完 {n} 张 ({time.time()-t0:.0f}s)')
PY
log '2/2 网格 obj -> ply(texrecon 走 mve 的 mesh_io)'
$AV/bin/aliceVision_convertMesh --input /root/av_ep0_off/C_filt/mesh_aligned.obj --output /root/texrecon_scene_mesh.ply --verboseLevel info > /root/convert_ply.log 2>&1
echo "  rc=$?  $(ls -la /root/texrecon_scene_mesh.ply 2>/dev/null | awk '{print $5" B"}')"
log 'READY'; touch /root/TEXPREP_DONE
