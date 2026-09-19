#!/usr/bin/env python3.11
"""低纹理占比度量(step0 证伪用)。

度量定义(单一口径,所有组共用):
  1. 读图 -> 灰度 float32(0..255)
  2. 统一尺度:按短边缩放到 SHORT_SIDE(默认 640,= TartanGround 原生分辨率),
     INTER_AREA。避免手机 4032x3024 与 TG 640x640 的尺度混杂。
  3. Sobel(ksize=3) 得 gx, gy;梯度能量 g2 = gx^2 + gy^2
  4. 5x5 均值滤波(box) 得局部梯度能量 E = mean_{5x5}(g2)
  5. 低纹理像素 := E < THR;单帧低纹理占比 = 该布尔图的均值
"""
import os, sys, json, argparse
import numpy as np
import cv2

SHORT_SIDE = 640


def load_gray(path, short_side=SHORT_SIDE, noise_sigma=0.0, seed=0):
    im = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if im is None:
        return None
    h, w = im.shape
    s = short_side / float(min(h, w))
    if abs(s - 1.0) > 1e-6:
        im = cv2.resize(im, (max(1, int(round(w * s))), max(1, int(round(h * s)))),
                        interpolation=cv2.INTER_AREA)
    f = im.astype(np.float32)
    if noise_sigma > 0:
        rng = np.random.default_rng(seed)
        f = np.clip(f + rng.normal(0.0, noise_sigma, f.shape).astype(np.float32), 0, 255)
    return f


def local_energy(path, short_side=SHORT_SIDE, noise_sigma=0.0, seed=0):
    f = load_gray(path, short_side, noise_sigma, seed)
    if f is None:
        return None
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    g2 = gx * gx + gy * gy
    E = cv2.blur(g2, (5, 5))
    return E


def energy_and_contrast(path, short_side=SHORT_SIDE, noise_sigma=0.0, seed=0):
    """返回 (E 绝对局部梯度能量, C 亮度归一化局部对比度, mean_gray)。

    C = sqrt(E) / (mean_5x5(I) + 1)  —— 用于剥离整体明暗对绝对梯度的影响。
    """
    f = load_gray(path, short_side, noise_sigma, seed)
    if f is None:
        return None, None, None
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    E = cv2.blur(gx * gx + gy * gy, (5, 5))
    mu = cv2.blur(f, (5, 5))
    C = np.sqrt(E) / (mu + 1.0)
    return E, C, float(f.mean())


def frac_below(E, thr):
    return float((E < thr).mean())


def list_images(d):
    out = []
    for root, _, files in os.walk(d):
        for f in sorted(files):
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                out.append(os.path.join(root, f))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', required=True)
    ap.add_argument('--name', required=True)
    ap.add_argument('--n', type=int, default=200)
    ap.add_argument('--thr', type=float, nargs='+', default=[100.0])
    ap.add_argument('--cthr', type=float, nargs='+', default=[0.02, 0.04, 0.08])
    ap.add_argument('--noise-sigma', type=float, default=0.0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    files = list_images(a.dir)
    if a.n > 0 and len(files) > a.n:
        idx = np.linspace(0, len(files) - 1, a.n).round().astype(int)
        idx = sorted(set(idx.tolist()))
        files = [files[i] for i in idx]

    rows = []
    for k, p in enumerate(files):
        E, C, mg = energy_and_contrast(p, noise_sigma=a.noise_sigma, seed=k)
        if E is None:
            continue
        rows.append({'path': p, 'mean_gray': mg,
                     **{('f%g' % t): frac_below(E, t) for t in a.thr},
                     **{('c%g' % t): frac_below(C, t) for t in a.cthr}})
        if len(rows) % 50 == 0:
            print('  %s %d/%d' % (a.name, len(rows), len(files)), flush=True)

    res = {'name': a.name, 'dir': a.dir, 'n_frames': len(rows),
           'short_side': SHORT_SIDE, 'thresholds': a.thr, 'cthresholds': a.cthr,
           'noise_sigma': a.noise_sigma, 'rows': rows}
    with open(a.out, 'w') as fh:
        json.dump(res, fh)
    print('%s: %d frames -> %s' % (a.name, len(rows), a.out))


if __name__ == '__main__':
    main()
