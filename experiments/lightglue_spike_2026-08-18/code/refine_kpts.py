#!/usr/bin/env python3
"""把 ALIKED 关键点拿回**全分辨率**原图做亚像素精化,匹配关系一个字不动。

诊断依据:B2 在每个轨迹长度档上都恒定高出基线约 +0.06px,说明是系统性定位赤字,
而不是点群成分。ALIKED 在 resize=1600 上定位、坐标 ×2.52 放大回 4032,亚像素误差
被同比放大;DSP-SIFT 则是在全分辨率上精化的。

做法:cv2.cornerSubPix 在原图上局部精化。位移超过 cap 的点判为"漂到别的特征上了",
回退到原坐标 —— 宁可不改,也不能悄悄换掉对应关系。
"""
import argparse, shutil, sqlite3, time
from pathlib import Path

import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="臂 B2 的 DB(含 ALIKED 关键点与匹配)")
    ap.add_argument("--images", required=True)
    ap.add_argument("--frame-map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--win", type=int, default=5, help="cornerSubPix 半窗")
    ap.add_argument("--cap", type=float, default=2.0, help="最大允许位移(px),超出回退")
    args = ap.parse_args()

    import json
    fmap = json.load(open(args.frame_map))
    shutil.copy(args.db, args.out)
    for suf in ("-wal", "-shm"):
        Path(args.out + suf).unlink(missing_ok=True)
    db = sqlite3.connect(args.out)
    names = dict(db.execute("select image_id,name from images"))

    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.001)
    tot = moved = revert = 0
    disp_all = []
    t0 = time.perf_counter()
    for iid in sorted(names):
        r = db.execute("select rows,cols,data from keypoints where image_id=?", (iid,)).fetchone()
        kp = np.frombuffer(r[2], np.float32).reshape(-1, r[1])[:, :2].copy()
        img = cv2.imread(str(Path(args.images) / fmap[str(iid)]), cv2.IMREAD_GRAYSCALE)
        ref = kp.reshape(-1, 1, 2).astype(np.float32)
        cv2.cornerSubPix(img, ref, (args.win, args.win), (-1, -1), crit)
        ref = ref.reshape(-1, 2)
        d = np.linalg.norm(ref - kp, axis=1)
        bad = ~np.isfinite(d) | (d > args.cap)
        ref[bad] = kp[bad]
        disp_all.append(d[~bad])
        tot += len(kp); moved += int((~bad).sum()); revert += int(bad.sum())
        db.execute("update keypoints set rows=?,cols=?,data=? where image_id=?",
                   (ref.shape[0], 2, ref.astype(np.float32).tobytes(), iid))
    db.execute("delete from two_view_geometries")
    db.commit(); db.close()
    d = np.concatenate(disp_all)
    print(f"精化 {tot:,} 点,{time.perf_counter()-t0:.0f}s")
    print(f"  接受 {moved:,} ({moved/tot:.1%})   超 {args.cap}px 回退 {revert:,} ({revert/tot:.1%})")
    print(f"  位移 中位 {np.median(d):.4f}px  均值 {d.mean():.4f}  p90 {np.percentile(d,90):.4f}")
    print(f"已写出 {args.out}(TVG 已清空待重验)")


if __name__ == "__main__":
    main()
