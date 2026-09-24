#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARKitScenes lowres_wide.traj (10 Hz) -> 任意时间戳的位姿 (slerp + lerp)。

出处 / 偏离清单 (先 grep 后写):
  D1  官方 apple/ARKitScenes 仓 HEAD 474aaa8 【没有】任何位姿插值实现。
      实测: `grep -rn -iE "slerp|interp|lerp|quaternion" --include=*.py .` 在
      threedod/ 与 depth_upsampling/ 下的全部命中都是【图像/特征图】的 resize
      (dataset.py:96, image_utils.py:14, msg.py:49, MultiscaleConvDepthEncoder.py:65,
       multi_scale_depth.py:52), 与位姿无关。官方 tenFpsDataLoader.py:332-336 只做
      "精确键, 否则 |Δt| < 0.005 s 取最近" —— 因为官方那条链用的是 lowres_depth,
      而 3dod 的帧就取自 traj 所在的同一时间网格。
      => 插值没有官方参考实现可抄, 本文件【偏离官方】。
  D2  旋转插值用 scipy.spatial.transform.Slerp (scipy 1.18.1, BSD-3),
      平移用 np.interp。不自己写四元数代码。
      Slerp 是 Shoemake 1985 的标准实现, 与 tartanair_to_blend.py:25 已在用的
      scipy.spatial.transform.Rotation 同一个库。
  D3  【在 camera->world 里插值】。traj 行给的是 extrinsics = [r_w_to_p | t_w_to_p]
      (world->camera), 官方 TrajStringToMatrix 返回 Rt = inv(extrinsics)。
      相机中心 C = -R_w2c^T t_w2c 才是物理上匀速运动的量; 对 t_w_to_p 直接线性插值
      在转动时是错的。本文件对 (R_c2w, C) 插值。
      这条是【可证伪的】: interp_space="w2c" 走另一条路, 留出法的误差必须明显更大 (见 ak_pose_interp_check.py)。
  D4  MAX_GAP=0.20 s 守卫 (= 2 倍 10 Hz 标称周期)。traj 里的大洞 = ARKit 跟丢,
      跨洞插值无意义。无官方出处, 是本文件自定的闸; 实测分布见检查脚本输出。
      时间戳落在 traj 首尾之外 (外推) 一律拒绝。
"""
import numpy as np
import cv2
from scipy.spatial.transform import Rotation, Slerp

MAX_GAP = 0.20          # D4


def read_traj(path):
    """返回 (ts[N], R_c2w[N,3,3], C[N,3])。逐字沿用 arkit2blend.py:32-40 的 traj_line。"""
    ts, Rs, Cs = [], [], []
    for line in open(path):
        if not line.strip():
            continue
        t = line.split()
        assert len(t) == 7, line
        R, _ = cv2.Rodrigues(np.asarray([float(x) for x in t[1:4]]))   # r_w_to_p
        E = np.eye(4, dtype=np.float64)
        E[:3, :3] = R
        E[:3, 3] = [float(x) for x in t[4:7]]                          # t_w_to_p
        Rt = np.linalg.inv(E)                                          # camera->world
        ts.append(float(t[0])); Rs.append(Rt[:3, :3]); Cs.append(Rt[:3, 3])
    o = np.argsort(np.asarray(ts))
    return np.asarray(ts)[o], np.asarray(Rs)[o], np.asarray(Cs)[o]


class TrajInterp(object):
    """t -> T(camera->world) 4x4, 落在 traj 区间外或跨 >max_gap 的洞时返回 None。"""

    def __init__(self, ts, R_c2w, C, max_gap=MAX_GAP, space="c2w"):
        self.ts = np.asarray(ts, dtype=np.float64)
        self.max_gap = float(max_gap)
        self.space = space
        keep = np.concatenate([[True], np.diff(self.ts) > 0])           # 去重复时间戳
        self.ts = self.ts[keep]
        R_c2w = np.asarray(R_c2w)[keep]; C = np.asarray(C)[keep]
        if space == "c2w":
            self.rot = Rotation.from_matrix(R_c2w)
            self.vec = np.asarray(C, dtype=np.float64)
        else:                                                           # D3 的阴性对照
            R_w2c = np.transpose(R_c2w, (0, 2, 1))
            t_w2c = -np.einsum("nij,nj->ni", R_w2c, C)
            self.rot = Rotation.from_matrix(R_w2c)
            self.vec = t_w2c
        self.slerp = Slerp(self.ts, self.rot)

    def gap_at(self, t):
        k = int(np.searchsorted(self.ts, t))
        if k <= 0 or k >= len(self.ts):
            return None
        return self.ts[k] - self.ts[k - 1]

    def __call__(self, t):
        t = float(t)
        if t < self.ts[0] or t > self.ts[-1]:
            return None                                                 # D4 不外推
        g = self.gap_at(t)
        if g is None:                                                   # 恰好等于首/末样本
            if abs(t - self.ts[0]) < 1e-12 or abs(t - self.ts[-1]) < 1e-12:
                g = 0.0
            else:
                return None
        if g > self.max_gap:
            return None
        R = self.slerp([t]).as_matrix()[0]
        v = np.stack([np.interp(t, self.ts, self.vec[:, i]) for i in range(3)])
        T = np.eye(4, dtype=np.float64)
        if self.space == "c2w":
            T[:3, :3] = R; T[:3, 3] = v
        else:
            T[:3, :3] = R.T; T[:3, 3] = -R.T @ v
        return T


def from_file(path, max_gap=MAX_GAP, space="c2w"):
    ts, R, C = read_traj(path)
    return TrajInterp(ts, R, C, max_gap=max_gap, space=space)


def pose_err(Ta, Tb):
    """(平移误差 m, 旋转误差 deg) —— 两个 camera->world 4x4 之间。"""
    dt = float(np.linalg.norm(Ta[:3, 3] - Tb[:3, 3]))
    dR = Ta[:3, :3].T @ Tb[:3, :3]
    c = (np.trace(dR) - 1.0) / 2.0
    return dt, float(np.degrees(np.arccos(max(-1.0, min(1.0, c)))))
