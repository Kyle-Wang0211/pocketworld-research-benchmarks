# -*- coding: utf-8 -*-
"""同一把尺子量两边的【光学锐度】—— 唯一还没做过跨边对照的候选。

口径与 09-21 那次对我们照片的测量完全相同:
  径向功率谱按频率分箱, 比较【最高倍频程 f∈[0.25,0.5)】与【次高倍频程 f∈[0.125,0.25)】。
  自然图像功率谱约 1/f^2 ⇒ 每倍频程能量大致相等 ⇒ 比值接近 1 表示"锐到 Nyquist";
  比值远小于 1 表示最高倍频程被光学/运动/降噪/压缩吃掉了。
  这个比值【尺度无关】, 所以 4032 宽和 6221 宽可以直接比。

另外给一个直接可比的量: 降一半再升回来的残差 RMS / 平坦区噪声地板。
"""
import glob, sys
import numpy as np
import cv2


def measure(name, pat, n=12):
    fs = sorted(glob.glob(pat))
    if not fs:
        print("%s : 🔴 找不到图 %s" % (name, pat)); return
    step = max(1, len(fs) // n)
    top, nxt, res2, noise, sizes = [], [], [], [], []
    for p in fs[::step][:n]:
        im = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        im = im.astype(np.float32) / 255.0
        h, w = im.shape
        sizes.append((w, h))
        F = np.fft.fftshift(np.abs(np.fft.fft2(im - im.mean())) ** 2)
        cy, cx = h // 2, w // 2
        yy, xx = np.mgrid[:h, :w]
        r = np.sqrt(((yy - cy) / h) ** 2 + ((xx - cx) / w) ** 2)
        tot = F.sum()
        top.append(F[(r >= 0.25) & (r < 0.5)].sum() / tot)
        nxt.append(F[(r >= 0.125) & (r < 0.25)].sum() / tot)
        d2 = cv2.resize(cv2.resize(im, (w // 2, h // 2), interpolation=cv2.INTER_AREA),
                        (w, h), interpolation=cv2.INTER_CUBIC)
        res2.append(float(np.sqrt(((im - d2) ** 2).mean())))
        bs = 64
        sub = im[:h // bs * bs, :w // bs * bs].reshape(h // bs, bs, w // bs, bs)
        sub = sub.transpose(0, 2, 1, 3).reshape(-1, bs * bs)
        noise.append(float(np.percentile(sub.std(1), 1)))
    print("=" * 66)
    print("%s   n=%d   尺寸 %s" % (name, len(top), sizes[0]))
    print("  最高倍频程 f∈[0.25,0.5) 能量占比 : %.4f%%" % (100 * np.mean(top)))
    print("  次高倍频程 f∈[0.125,0.25)        : %.4f%%" % (100 * np.mean(nxt)))
    print("  ⇒ 【锐度比】最高/次高 = %.3f        (1/f^2 自然图像应 ≈1)" % (np.mean(top) / np.mean(nxt)))
    print("  降半再升回的残差 RMS = %.5f ; 平坦区噪声地板 = %.5f ; 比值 %.2f"
          % (np.mean(res2), np.mean(noise), np.mean(res2) / max(np.mean(noise), 1e-9)))


measure("我们 (手持 iPhone 12MP, 酒店房间)", "/root/mvs_P16k/images/*.jpg")
measure("ETH3D office (三脚架 DSLR)", "/root/eth3d/office/images/dslr_images_undistorted/*.JPG")
measure("ETH3D delivery_area", "/root/eth3d/delivery_area/images/dslr_images_undistorted/*.JPG")
