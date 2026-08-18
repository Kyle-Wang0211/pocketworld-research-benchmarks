#!/usr/bin/env python3
"""把重建里的位姿/内参/深度范围导成 npz,供共视裁剪用。

⚠️ 必须单独一个进程:torch 与 pycolmap 同进程 = OMP Error #15。

深度范围:按每台相机实际看到的 3D 点取 [p2, p98],再各留 20% 余量。
生产端等价物 = 拍摄期 live 稀疏云的深度分布(已经有),不需要新东西。
"""
import argparse
import numpy as np
import pycolmap as pc
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", required=True, help="work_*/sparse/0")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    r = pc.Reconstruction(args.rec)
    ids, K, R, t, dlo, dhi, wh = [], [], [], [], [], [], []
    for iid, im in sorted(r.images.items()):
        if not im.has_pose:
            continue
        cam = r.cameras[im.camera_id]
        Kc = cam.calibration_matrix()
        cfw = im.cam_from_world()          # ⚠️ pycolmap 4.1 里这是方法,不是属性
        Rw = cfw.rotation.matrix()
        tw = np.asarray(cfw.translation)
        # 该相机实际看到的点的深度
        d = []
        for p2d in im.points2D:
            if p2d.has_point3D():
                X = r.points3D[p2d.point3D_id].xyz
                d.append((Rw @ X + tw)[2])
        d = np.array(d) if d else np.array([1.0, 10.0])
        lo, hi = np.percentile(d, 2), np.percentile(d, 98)
        ids.append(iid); K.append(Kc); R.append(Rw); t.append(tw)
        dlo.append(max(lo * 0.8, 1e-3)); dhi.append(hi * 1.2)
        wh.append([cam.width, cam.height])

    np.savez(args.out, ids=np.array(ids), K=np.array(K), R=np.array(R),
             t=np.array(t), dlo=np.array(dlo), dhi=np.array(dhi), wh=np.array(wh))
    print(f"导出 {len(ids)} 台相机 → {args.out}")
    print(f"深度范围 中位 [{np.median(dlo):.2f}, {np.median(dhi):.2f}] m")


if __name__ == "__main__":
    main()
