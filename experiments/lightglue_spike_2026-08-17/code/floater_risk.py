#!/usr/bin/env python3
"""浮点/鬼点风险代理指标:track 延长对下游有没有用,不能靠肉眼看稀疏点云
(点数几乎不变,毫米级位移人眼看不出),要看它改的那两个量对不对得上
生产判浮点的判据。

依据(旧账 [[project_pocketworld_floater_campaign_ceiling]] 等):浮点/鬼点战役里
反复验证的结论是 —— 视差角小的点(相机夹角窄,深度方向解算病态)和 track 短的点
(缺乏冗余交叉验证)是浮点的主要来源,AUC 上视差角是唯一稳定有效的判据。

这里算的是:每个点用它 track 里最大的相机对视差角(最大化,因为只要有一对
相机看得够开这个点就是稳的),track 延长若真有用,应该让"视差角小 + track 短"
的高风险点占比下降 —— 这才是"对下游有帮助"的可计算证据,不是重投影这种
BA自己就能优化的数字。
"""
import sys
import numpy as np
import pycolmap as pc


def max_tri_angle_deg(centers_by_img, p3):
    centers = [centers_by_img[e.image_id] for e in p3.track.elements
               if e.image_id in centers_by_img]
    if len(centers) < 2:
        return 0.0
    X = p3.xyz
    rays = [(c - X) for c in centers]
    rays = [r / (np.linalg.norm(r) + 1e-9) for r in rays]
    best = 0.0
    for i in range(len(rays)):
        for j in range(i + 1, len(rays)):
            cosv = np.clip(np.dot(rays[i], rays[j]), -1, 1)
            best = max(best, np.degrees(np.arccos(cosv)))
    return best


def main():
    rec = pc.Reconstruction(sys.argv[1])
    # ⚠️ 相机光心只算一次:原来每个点都重算所有相机的位姿分解,132×20万点重复浪费
    centers_by_img = {}
    for iid, im in rec.images.items():
        if not im.has_pose:
            continue
        cfw = im.cam_from_world()
        centers_by_img[iid] = -cfw.rotation.matrix().T @ np.asarray(cfw.translation)

    pts = list(rec.points3D.values())
    tl = np.array([len(p.track.elements) for p in pts])
    ang = np.array([max_tri_angle_deg(centers_by_img, p) for p in pts])

    # 生产的浮点战役判据:低视差角 + 短track = 高风险(旧账 tri-angle≥3°过滤门)
    for a_thr in (2.0, 3.0):
        risky = (ang < a_thr) & (tl < 3)
        print(f"  视差角<{a_thr}° 且 track<3:{risky.sum():,} 点 "
              f"({risky.mean()*100:.2f}%)")
    print(f"  视差角 中位 {np.median(ang):.2f}°  p10 {np.percentile(ang,10):.2f}°")
    print(f"  track  中位 {int(np.median(tl))}   均值 {tl.mean():.2f}")


if __name__ == "__main__":
    main()
