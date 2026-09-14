#!/usr/bin/env python3
"""把 fuseCut 网格按我们自己的相机位姿渲出来 —— 交付形态就是网格本身,不是点云。
同机位同时渲原始照片对照,直接看"网格交付"长什么样。"""
import os, sys, numpy as np, open3d as o3d, cv2
MESH = "/root/av/mesh_avdense.obj"
OUT = "/root/mesh_render"; os.makedirs(OUT, exist_ok=True)
m = o3d.io.read_triangle_mesh(MESH, enable_post_processing=True)
V = np.asarray(m.vertices); V[:,1] *= -1; V[:,2] *= -1     # 网格→我们的世界系(已验:入画 66.9%)
m.vertices = o3d.utility.Vector3dVector(V)
m.compute_vertex_normals()
print(f"网格 {len(m.vertices):,} 顶点 {len(m.triangles):,} 面 | 顶点色 {m.has_vertex_colors()}")

def read_cam(p):
    L=[l.rstrip() for l in open(p)]
    E=np.fromstring(" ".join(L[1:5]),dtype=np.float64,sep=" ").reshape(4,4)
    K=np.fromstring(" ".join(L[7:10]),dtype=np.float64,sep=" ").reshape(3,3)
    return K,E
W,H = 1024, 768
views = [0, 20, 40, 60, 80, 100, 121, 131]
r = o3d.visualization.rendering.OffscreenRenderer(W, H)
mat = o3d.visualization.rendering.MaterialRecord(); mat.shader = "defaultLit"
r.scene.add_geometry("m", m, mat)
r.scene.set_background([0,0,0,1])
for i in views:
    K,E = read_cam(f"/root/mvs_P16k/cams/{i:08d}_cam.txt")
    Kx = K.copy(); Kx[0] *= W/4032.0; Kx[1] *= H/3024.0
    r.setup_camera(o3d.camera.PinholeCameraIntrinsic(W,H,Kx[0,0],Kx[1,1],Kx[0,2],Kx[1,2]), E)
    img = np.asarray(r.render_to_image())
    cv2.imwrite(f"{OUT}/mesh_{i:03d}.png", img[:,:,::-1])
    photo = cv2.imread(f"/root/mvs_P16k/images/{i:08d}.jpg")
    cv2.imwrite(f"{OUT}/photo_{i:03d}.png", cv2.resize(photo,(W,H),interpolation=cv2.INTER_AREA))
print(f"渲出 {len(views)} 个机位 -> {OUT}")
