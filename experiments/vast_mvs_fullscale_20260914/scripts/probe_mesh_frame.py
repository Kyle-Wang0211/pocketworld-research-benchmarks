#!/usr/bin/env python3
"""网格到底在哪个系:把网格顶点投进相机 0,看落在画面内的比例 + 深度是否为正。
对照四种假设:恒等 / y,z 反号 / 全反号 / 只 z 反号。正确的那个应该有高 in-frame 率。"""
import numpy as np, open3d as o3d

def read_cam(p):
    L = [l.rstrip() for l in open(p)]
    E = np.fromstring(" ".join(L[1:5]), dtype=np.float64, sep=" ").reshape(4, 4)
    K = np.fromstring(" ".join(L[7:10]), dtype=np.float64, sep=" ").reshape(3, 3)
    return K, E

K, E = read_cam("/root/mvs_P16k/cams/00000000_cam.txt")
W, H = 768, 576
sc = np.array([W / 4032.0, H / 3024.0])          # cam 文件的 K 是全分辨率的
Kx = K.copy(); Kx[0] *= sc[0]; Kx[1] *= sc[1]
C = -E[:3,:3].T @ E[:3,3]
print(f"相机0 中心 {np.round(C,3)}")

for name, f in (("恒等", np.array([1,1,1.0])), ("y,z反号", np.array([1,-1,-1.0])),
                ("全反号", np.array([-1,-1,-1.0])), ("只z反号", np.array([1,1,-1.0])),
                ("x,y反号", np.array([-1,-1,1.0]))):
    for tag, path in (("网格", "/root/av/mesh_avdense.obj"), ("官方云", "/root/ws_gc8/official_full.ply")):
        if tag == "网格":
            V = np.asarray(o3d.io.read_triangle_mesh(path).vertices)
        else:
            if name != "恒等": continue
            V = np.asarray(o3d.io.read_point_cloud(path).points)
        P = V * f
        cam = (E[:3,:3] @ P.T + E[:3,3:4])
        front = cam[2] > 1e-6
        uv = Kx @ cam[:, front]
        u, v = uv[0]/uv[2], uv[1]/uv[2]
        infr = ((u>=0)&(u<W)&(v>=0)&(v<H)).mean() if front.sum() else 0
        print(f"  {tag} {name:<8} 前方 {front.mean()*100:5.1f}%  其中入画 {infr*100:5.1f}%  中心 {np.round(P.mean(0),2)}")
