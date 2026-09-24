# -*- coding: utf-8 -*-
"""1:1 裁切对照: 原生 4032 vs 「降到 2016 再放大回 4032」。
自动选两块: 梯度能量最高的一块(12MP 的最好情况) + 最平的一块(白墙, 多层的战场)。"""
import cv2, numpy as np
P = "/root/mvs_P16k/images/00000000.jpg"
im = cv2.imread(P)
h, w = im.shape[:2]
g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, 3); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, 3)
e = cv2.boxFilter(gx*gx+gy*gy, -1, (129, 129))
S = 512
e[:S, :] = -1; e[-S:, :] = -1; e[:, :S] = -1; e[:, -S:] = -1
iy, ix = np.unravel_index(np.argmax(e), e.shape)
fy, fx = np.unravel_index(np.argmin(np.where(e < 0, 1e18, e)), e.shape)
d2 = cv2.resize(cv2.resize(im, (w//2, h//2), interpolation=cv2.INTER_AREA),
                (w, h), interpolation=cv2.INTER_CUBIC)
def put(img, t):
    cv2.rectangle(img, (0, 0), (S, 34), (0, 0, 0), -1)
    cv2.putText(img, t, (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
    return img
rows = []
for (cy, cx), nm in [((iy, ix), "high-texture"), ((fy, fx), "flat / wall")]:
    a = im[cy-S//2:cy+S//2, cx-S//2:cx+S//2].copy()
    b = d2[cy-S//2:cy+S//2, cx-S//2:cx+S//2].copy()
    rows.append(np.hstack([put(a, "native 4032  [%s]" % nm),
                           np.full((S, 6, 3), 60, np.uint8),
                           put(b, "2016 -> upscaled to 4032")]))
out = np.vstack([rows[0], np.full((6, rows[0].shape[1], 3), 60, np.uint8), rows[1]])
cv2.imwrite("/root/crop_1to1.png", out)
print("写出 /root/crop_1to1.png", out.shape)
print("高纹理块中心 (%d,%d)  平坦块中心 (%d,%d)" % (ix, iy, fx, fy))
