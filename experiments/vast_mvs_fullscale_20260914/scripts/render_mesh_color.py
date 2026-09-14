#!/usr/bin/env python3
"""真彩网格渲染。OBJ 无顶点色/无贴图 => 从官方融合云(带照片原色)按最近邻把颜色转到网格顶点。
颜色全部来自照片,没有任何着色/伪彩。着色器用 defaultUnlit,避免光照把颜色压灰。"""
import os, numpy as np, open3d as o3d, cv2
from scipy.spatial import cKDTree
MESH="/root/av/mesh_avdense.obj"; CLOUD="/root/ws_gc8/official_full.ply"
OUT="/root/mesh_render"; os.makedirs(OUT, exist_ok=True)

m = o3d.io.read_triangle_mesh(MESH)
V = np.asarray(m.vertices).copy(); V[:,1]*=-1; V[:,2]*=-1
m.vertices = o3d.utility.Vector3dVector(V)
pc = o3d.io.read_point_cloud(CLOUD)
P = np.asarray(pc.points); C = np.asarray(pc.colors)
print(f"网格 {len(V):,} 顶点 | 云 {len(P):,} 点(带照片原色)")
t = cKDTree(P)
d, idx = t.query(V, k=1, workers=-1)
m.vertex_colors = o3d.utility.Vector3dVector(C[idx])
m.compute_vertex_normals()
print(f"最近邻取色: 距离 p50 {np.median(d)*1000:.1f} mm  p90 {np.percentile(d,90)*1000:.1f} mm")
o3d.io.write_triangle_mesh("/root/av/mesh_color.ply", m)

def read_cam(p):
    L=[l.rstrip() for l in open(p)]
    return (np.fromstring(" ".join(L[7:10]),dtype=np.float64,sep=" ").reshape(3,3),
            np.fromstring(" ".join(L[1:5]),dtype=np.float64,sep=" ").reshape(4,4))
W,H=1024,768
r = o3d.visualization.rendering.OffscreenRenderer(W,H)
mat = o3d.visualization.rendering.MaterialRecord(); mat.shader="defaultUnlit"
r.scene.add_geometry("m", m, mat); r.scene.set_background([0,0,0,1])
for i in (0,20,40,60,80,100,121,131):
    K,E = read_cam(f"/root/mvs_P16k/cams/{i:08d}_cam.txt")
    Kx=K.copy(); Kx[0]*=W/4032.0; Kx[1]*=H/3024.0
    r.setup_camera(o3d.camera.PinholeCameraIntrinsic(W,H,Kx[0,0],Kx[1,1],Kx[0,2],Kx[1,2]), E)
    cv2.imwrite(f"{OUT}/mesh_{i:03d}.png", np.asarray(r.render_to_image())[:,:,::-1])
    cv2.imwrite(f"{OUT}/photo_{i:03d}.png",
                cv2.resize(cv2.imread(f"/root/mvs_P16k/images/{i:08d}.jpg"),(W,H),interpolation=cv2.INTER_AREA))
print("真彩渲染完成")
