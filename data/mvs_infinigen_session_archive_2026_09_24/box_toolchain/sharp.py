# -*- coding: utf-8 -*-
"""照片里到底有没有 12MP 的细节。两个量, 都是标准做法, 没有自研:
  ①【径向功率谱】把 2D FFT 的能量按径向频率分箱。最高一个倍频程 (f>0.25 cyc/px)
     只有 4032 宽才表示得出来; 2016 宽表示不了。看它占多少。
  ②【降采样-再上采样 残差】把图降到 2016 再双三次放回 4032 —— 这一步【按定义】
     抹掉全部最高倍频程内容。残差的 RMS 就是「12MP 相对 2016 多出来的东西」有多强。
     同时给一个对照: 4032→3024→4032 (只抹掉更高频的一小部分)。
"""
import glob, numpy as np, cv2
files = sorted(glob.glob("/root/mvs_P16k/images/*.jpg"))
print("共 %d 张" % len(files))
top, nxt, res2, res15, noise = [], [], [], [], []
for p in files[::11]:
    im = cv2.imread(p, cv2.IMREAD_GRAYSCALE).astype(np.float32)/255.0
    h, w = im.shape
    # ① 径向功率谱
    F = np.fft.fftshift(np.abs(np.fft.fft2(im - im.mean()))**2)
    cy, cx = h//2, w//2
    yy, xx = np.mgrid[:h, :w]
    r = np.sqrt(((yy-cy)/h)**2 + ((xx-cx)/w)**2)          # 0..~0.707, 0.5=Nyquist
    tot = F.sum()
    top.append(F[(r >= 0.25) & (r < 0.5)].sum()/tot)      # 只有 4032 能表示
    nxt.append(F[(r >= 0.125) & (r < 0.25)].sum()/tot)    # 2016 也能表示
    # ② 降-升采样残差
    d2 = cv2.resize(cv2.resize(im, (w//2, h//2), interpolation=cv2.INTER_AREA),
                    (w, h), interpolation=cv2.INTER_CUBIC)
    d15 = cv2.resize(cv2.resize(im, (int(w/1.333), int(h/1.333)), interpolation=cv2.INTER_AREA),
                     (w, h), interpolation=cv2.INTER_CUBIC)
    res2.append(float(np.sqrt(((im-d2)**2).mean())))
    res15.append(float(np.sqrt(((im-d15)**2).mean())))
    # 噪声地板: 用最平坦的 64x64 块的标准差
    bs = 64
    sub = im[:h//bs*bs, :w//bs*bs].reshape(h//bs, bs, w//bs, bs).transpose(0,2,1,3).reshape(-1, bs*bs)
    noise.append(float(np.percentile(sub.std(1), 1)))
f = lambda a: (np.mean(a), np.min(a), np.max(a))
print()
print("① 径向功率谱 (n=%d 张)" % len(top))
print("   最高倍频程 f∈[0.25,0.5) 的能量占比 : 均值 %.4f%%  (%.4f%% ~ %.4f%%)" % tuple(x*100 for x in f(top)))
print("   次高倍频程 f∈[0.125,0.25)        : 均值 %.4f%%  (%.4f%% ~ %.4f%%)" % tuple(x*100 for x in f(nxt)))
print("   ⇒ 最高倍频程 / 次高倍频程 = %.3f" % (np.mean(top)/np.mean(nxt)))
print()
print("② 降采样-再上采样 残差 RMS (灰度 0-1)")
print("   4032→2016→4032 (抹掉最高倍频程) : 均值 %.5f  (%.5f ~ %.5f)" % f(res2))
print("   4032→3024→4032 (只抹掉一部分)   : 均值 %.5f  (%.5f ~ %.5f)" % f(res15))
print("   平坦块噪声地板 (p1 标准差)       : 均值 %.5f  (%.5f ~ %.5f)" % f(noise))
print("   ⇒ 残差 / 噪声地板 = %.2f  (接近 1 = 多出来的全是噪声)" % (np.mean(res2)/np.mean(noise)))
