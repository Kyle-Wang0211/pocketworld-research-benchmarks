# -*- coding: utf-8 -*-
"""为什么同样 2.5x 分辨率步长, ETH3D 完整度 +15.9pp 而我们只 +0.45pp?
三项独立候选, 全部从两边的 COLMAP 稀疏模型 + 原图直接量, 同一把尺子。

① 位姿/SfM 精度  = points3D 的平均重投影误差 (COLMAP 自带字段, 单位=重建时的像素)
   🔑 换算到推理分辨率: err_at_W = err_native * W / native_width
      这个数如果 >= geo_pixel_thres, 那么【位姿误差本身就超过几何闸】, 提分辨率必然无效。
② 低纹理占比    = 11x11 局部灰度标准差, 与 layer_gap2 同口径
③ 视角几何      = 每个 3D 点的最大三角化角 + 轨迹长度(被几个视图看到) + 相机间基线

读 COLMAP 模型直接复用 APD-MVS 的 colmap2mvsnet 里的读函数, 不自己写解析。
"""
import sys, os, glob, math
import numpy as np
sys.path.insert(0, "/root")
import importlib.util
spec = importlib.util.spec_from_file_location("c2m", "/root/colmap2mvsnet_np2.py")
c2m = importlib.util.module_from_spec(spec); spec.loader.exec_module(c2m)


def load_model(path, ext):
    if ext == ".txt":
        cams = c2m.read_cameras_text(os.path.join(path, "cameras.txt"))
        imgs = c2m.read_images_text(os.path.join(path, "images.txt"))
        pts = c2m.read_points3D_text(os.path.join(path, "points3D.txt"))
    else:
        cams = c2m.read_cameras_binary(os.path.join(path, "cameras.bin"))
        imgs = c2m.read_images_binary(os.path.join(path, "images.bin"))
        pts = c2m.read_points3d_binary(os.path.join(path, "points3D.bin"))
    return cams, imgs, pts


def cam_center(im):
    R = c2m.qvec2rotmat(im.qvec)
    return -R.T @ im.tvec


def analyse(name, model_path, ext, img_glob, native_w):
    cams, imgs, pts = load_model(model_path, ext)
    print("=" * 62)
    print("%s   视图 %d   3D 点 %d   原图宽 %d" % (name, len(imgs), len(pts), native_w))

    # ---------- ① 重投影误差 ----------
    err = np.array([p.error for p in pts.values()], dtype=np.float64)
    err = err[np.isfinite(err)]
    print("\n① SfM 重投影误差 (原生像素)")
    print("   中位 %.4f   均值 %.4f   p90 %.4f   p99 %.4f" %
          (np.median(err), err.mean(), np.percentile(err, 90), np.percentile(err, 99)))
    for W in (768, 1920, 2048):
        s = W / native_w
        print("   折算到 %4d 宽: 中位 %.4f px   p90 %.4f px" % (W, np.median(err) * s, np.percentile(err, 90) * s))

    # ---------- ③ 视角几何 ----------
    C = {iid: cam_center(im) for iid, im in imgs.items()}
    tri, tracklen = [], []
    keys = list(pts.keys())
    rng = np.random.default_rng(20260922)
    sel = keys if len(keys) <= 20000 else [keys[i] for i in rng.choice(len(keys), 20000, replace=False)]
    for k in sel:
        p = pts[k]
        ids = list(dict.fromkeys(p.image_ids.tolist() if hasattr(p.image_ids, "tolist") else list(p.image_ids)))
        tracklen.append(len(ids))
        if len(ids) < 2:
            continue
        cs = [C[i] for i in ids if i in C]
        if len(cs) < 2:
            continue
        X = np.asarray(p.xyz, dtype=np.float64)
        rays = [(c - X) / (np.linalg.norm(c - X) + 1e-12) for c in cs]
        best = 0.0
        for a in range(len(rays)):
            for b in range(a + 1, len(rays)):
                d = float(np.clip(np.dot(rays[a], rays[b]), -1, 1))
                ang = math.degrees(math.acos(d))
                if ang > best:
                    best = ang
        tri.append(best)
    tri = np.array(tri); tracklen = np.array(tracklen)
    ctr = np.array(list(C.values()))
    from itertools import combinations
    bl = [np.linalg.norm(a - b) for a, b in combinations(ctr, 2)]
    print("\n③ 视角几何")
    print("   最大三角化角  中位 %.2f°   p10 %.2f°   p90 %.2f°" %
          (np.median(tri), np.percentile(tri, 10), np.percentile(tri, 90)))
    print("   轨迹长度(被几个视图看到)  中位 %.1f   均值 %.1f" % (np.median(tracklen), tracklen.mean()))
    print("   相机中心两两距离 中位 %.3f   场景对角 %.3f" %
          (np.median(bl), float(np.linalg.norm(ctr.max(0) - ctr.min(0)))))

    # ---------- ② 低纹理占比 ----------
    import cv2
    fs = sorted(glob.glob(img_glob))
    if not fs:
        print("\n② 低纹理: 🔴 找不到图 %s" % img_glob)
        return
    fr = []
    stds = []
    for p in fs[::max(1, len(fs) // 12)][:12]:
        g = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        g = cv2.resize(g, (768, int(768 * g.shape[0] / g.shape[1])), interpolation=cv2.INTER_AREA).astype(np.float32)
        m = cv2.boxFilter(g, -1, (11, 11))
        s = np.sqrt(np.maximum(cv2.boxFilter(g * g, -1, (11, 11)) - m * m, 0))
        stds.append(np.percentile(s, [10, 25, 50]))
        fr.append(float((s < 3.0).mean()))
    stds = np.array(stds)
    print("\n② 低纹理 (统一缩到 768 宽后, 11x11 局部灰度 std)")
    print("   std<3.0 的像素占比  中位 %.1f%%   范围 %.1f%% – %.1f%%" %
          (100 * np.median(fr), 100 * min(fr), 100 * max(fr)))
    print("   局部 std 分位  p10 %.2f   p25 %.2f   p50 %.2f" % tuple(np.median(stds, 0)))


analyse("我们 (手持 iPhone 12MP, 酒店房间)",
        "/root/old_box_archive/mvs_scene/sparse", ".bin",
        "/root/mvs_P16k/images/*.jpg", 4032)
analyse("ETH3D office (三脚架 DSLR)",
        "/root/eth3d/office/dslr_calibration_undistorted", ".txt",
        "/root/eth3d/office/images/dslr_images_undistorted/*.JPG", 6221)
