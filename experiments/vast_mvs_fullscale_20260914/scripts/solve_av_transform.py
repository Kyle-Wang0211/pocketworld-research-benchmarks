#!/usr/bin/env python3
"""解 AliceVision 世界系 -> 我们 COLMAP 世界系 的刚体变换(不猜反号)。
用两边的相机中心做 Kabsch/Umeyama 对齐;阳性对照 = 对齐后的中心残差应接近 0。
09-07 那次是猜 y,z 反号,脚本注释自己标了 61%/67% 的黄旗 —— 这次用数值解。"""
import json, sys, numpy as np

sfm = json.load(open("/root/av/sfm_poses_pp.sfm"))
poses = {}
for p in sfm.get("poses", []):
    t = p["pose"]["transform"]
    R = np.array([float(x) for x in t["rotation"]], dtype=np.float64).reshape(3, 3)
    C = np.array([float(x) for x in t["center"]], dtype=np.float64)
    poses[int(p["poseId"])] = (R, C)
vid2pid = {int(v["viewId"]): int(v["poseId"]) for v in sfm["views"]}
print(f"AliceVision: {len(poses)} 个位姿 / {len(vid2pid)} 个视图")

def read_cam(p):
    L = [l.rstrip() for l in open(p)]
    E = np.fromstring(" ".join(L[1:5]), dtype=np.float64, sep=" ").reshape(4, 4)
    return E                                  # cam_T_world

A, B = [], []
for vid, pid in sorted(vid2pid.items()):
    if pid not in poses: continue
    E = read_cam(f"/root/mvs_P16k/cams/{vid:08d}_cam.txt")
    C_ours = (-E[:3, :3].T @ E[:3, 3])        # 我们的相机中心(世界系)
    A.append(poses[pid][1]); B.append(C_ours)
A, B = np.array(A), np.array(B)
print(f"配对 {len(A)} 台相机")

# Umeyama(含尺度), 求 B ≈ s*R@A + t
ma, mb = A.mean(0), B.mean(0)
X, Y = A - ma, B - mb
H = X.T @ Y / len(A)
U, S, Vt = np.linalg.svd(H)
d = np.sign(np.linalg.det(Vt.T @ U.T))
D = np.diag([1, 1, d])
R = Vt.T @ D @ U.T
s = float((S * np.array([1, 1, d])).sum() / (X ** 2).sum() * len(A))
t = mb - s * R @ ma
res = np.linalg.norm((s * (R @ A.T).T + t) - B, axis=1)
print(f"\n阳性对照 —— 对齐后相机中心残差: 中位 {np.median(res)*1000:.3f} mm  最大 {res.max()*1000:.3f} mm")
print(f"尺度 s = {s:.6f}   (应接近 1)")
print(f"旋转 R =\n{np.round(R,4)}")
print(f"平移 t = {np.round(t,4)}")
np.savez("/root/av/av2ours.npz", R=R, t=t, s=s)
print("\n变换已存 /root/av/av2ours.npz")
