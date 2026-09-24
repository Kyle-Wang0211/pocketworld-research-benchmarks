#!/usr/bin/env python3
"""从真实拍摄相机位姿渲染三联图: 原照片 | Poisson 顶点色(③) | texrecon 官方贴图输出。
texrecon 的 obj+mtl+309 张 png 由 Open3D 官方 read_triangle_model 原样加载, 不改任何数据。
相机内外参逐字取自 scene_dense.sfm, 与网格同帧(均为 SfM 帧, 不做 y,z 取负 —— 那只是网页展示帧的事)。"""
import json, os, sys, time, numpy as np
os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
import cv2, open3d as o3d
from open3d.visualization import rendering
SFM='/root/av_ep0_off/scene_dense.sfm'; OUT='/root/cmp'; os.makedirs(OUT,exist_ok=True)
W,H=1344,1002                      # 4032x3008 的 1/3
d=json.load(open(SFM))
I=d['intrinsics'][0]; W0=int(I['width']); H0=int(I['height'])
f=float(I['focalLength'])/float(I['sensorWidth'])*W0; pp=[float(x) for x in I['principalPoint']]
s=W/W0
K=np.array([[f*s,0,(W0/2+pp[0])*s],[0,f*s,(H0/2+pp[1])*s],[0,0,1]])
poses={p['poseId']:p['pose']['transform'] for p in d['poses']}
views=sorted([v for v in d['views'] if v['poseId'] in poses], key=lambda v:v['path'])
t0=time.time()
print('加载 texrecon 官方输出(多材质 OBJ)...',flush=True)
model=o3d.io.read_triangle_model('/root/texrecon_out/poisson.obj')
print(f'  {len(model.meshes)} 个网格块 / {len(model.materials)} 个材质  ({time.time()-t0:.0f}s)',flush=True)
mesh3=o3d.io.read_triangle_mesh('/root/av_ep0_off/C_filt/mesh_aligned.obj')
import numpy as _np
from scipy.spatial import cKDTree
from plyfile import PlyData
pl=PlyData.read('/root/av_ep0_off/C/poisson.ply')['vertex']
P=_np.stack([pl['x'],pl['y'],pl['z']],1).astype(_np.float64)
C8=_np.stack([pl['red'],pl['green'],pl['blue']],1).astype(_np.float64)/255.0
V0=_np.asarray(o3d.io.read_triangle_mesh('/root/av_ep0_off/C_filt/mesh.obj').vertices)
_,ii=cKDTree(P).query(V0,k=1,workers=-1)
mesh3.vertex_colors=o3d.utility.Vector3dVector(C8[ii]); mesh3.compute_vertex_normals()
print(f'  ③ 顶点色就位 {len(mesh3.vertices):,} v  ({time.time()-t0:.0f}s)',flush=True)
m3=rendering.MaterialRecord(); m3.shader='defaultUnlit'
r=rendering.OffscreenRenderer(W,H)
def shot(scene_setup, ext):
    r.scene.clear_geometry(); r.scene.set_background([0,0,0,1]); scene_setup()
    r.setup_camera(K, ext, W, H)
    return np.asarray(r.render_to_image())[:,:,::-1]
PICK=[0,33,66,99]
for k in PICK:
    v=views[k]; vid=v['viewId']; t=poses[v['poseId']]
    R=np.array([float(x) for x in t['rotation']]).reshape(3,3); Cc=np.array([float(x) for x in t['center']])
    ext=np.eye(4); ext[:3,:3]=R; ext[:3,3]=-R@Cc
    with __import__('OpenEXR').File(f'/root/av_ep0_off/prep/{vid}.exr') as fh:
        ch=fh.channels(); img=np.asarray(ch['RGBA'].pixels,dtype=np.float32)[...,:3]
    img=np.clip(img,0,None); srgb=np.where(img<=0.0031308,img*12.92,1.055*img**(1/2.4)-0.055)
    photo=cv2.resize((np.clip(srgb,0,1)*255+0.5).astype(np.uint8)[:,:,::-1],(W,H),interpolation=cv2.INTER_AREA)
    a=shot(lambda: r.scene.add_geometry('m3',mesh3,m3), ext)
    b=shot(lambda: r.scene.add_model('tex',model), ext)
    cv2.imwrite(f'{OUT}/view{k:03d}.png', np.hstack([photo,a,b]))
    print(f'  view {k:3d} (viewId {vid}) 渲完  ({time.time()-t0:.0f}s)',flush=True)
print('三联图顺序: 原照片 | ③ Poisson 顶点色 | texrecon 官方贴图')
