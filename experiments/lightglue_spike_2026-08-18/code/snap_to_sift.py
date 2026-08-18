#!/usr/bin/env python3
"""把 ALIKED 关键点就近吸附到全分辨率 DSP-SIFT 关键点上,匹配索引保持不动。

目的:纯 CPU 检验"重投影赤字来自 ALIKED 的关键点坐标"这一诊断。
若把坐标换成 DSP-SIFT 的亚像素精确值后重投影下降 ⇒ 诊断成立,D 臂的架构方向正确。

⚠️ 这不是最终架构(D 才是:在 SIFT 坐标上采 ALIKED 描述子)。这里描述子仍是在
ALIKED 自己的位置上采的,只是**上报的坐标**换了 —— 作为判据足够,作为产品不成立。

半径要小:吸附到"另一个物理特征"上会引入真实误差,宁可不吸附。
"""
import argparse, shutil, sqlite3
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="ALIKED 臂的 DB(B2)")
    ap.add_argument("--sift-db", required=True, help="含全分辨率 DSP-SIFT 关键点的源 DB")
    ap.add_argument("--out", required=True)
    ap.add_argument("--radius", type=float, default=1.5)
    args = ap.parse_args()

    shutil.copy(args.db, args.out)
    for suf in ("-wal", "-shm"):
        Path(args.out + suf).unlink(missing_ok=True)

    sift = sqlite3.connect(args.sift_db)
    S = {i: np.frombuffer(d, np.float32).reshape(-1, c)[:, :2]
         for i, c, d in sift.execute("select image_id,cols,data from keypoints")}
    sift.close()

    db = sqlite3.connect(args.out)
    tot = snapped = 0
    disp = []
    for iid, c, d in db.execute("select image_id,cols,data from keypoints").fetchall():
        kp = np.frombuffer(d, np.float32).reshape(-1, c)[:, :2].copy()
        tree = cKDTree(S[iid])
        dist, idx = tree.query(kp, distance_upper_bound=args.radius)
        ok = np.isfinite(dist)
        kp[ok] = S[iid][idx[ok]]
        disp.append(dist[ok])
        tot += len(kp); snapped += int(ok.sum())
        db.execute("update keypoints set rows=?,cols=?,data=? where image_id=?",
                   (kp.shape[0], 2, kp.astype(np.float32).tobytes(), iid))
    db.execute("delete from two_view_geometries")
    db.commit(); db.close()

    dd = np.concatenate(disp)
    print(f"关键点 {tot:,},在 {args.radius}px 内找到 SIFT 对应并吸附 {snapped:,} ({snapped/tot:.1%})")
    print(f"  吸附位移 中位 {np.median(dd):.4f}px  均值 {dd.mean():.4f}  p90 {np.percentile(dd,90):.4f}")
    print(f"已写出 {args.out}")


if __name__ == "__main__":
    main()
