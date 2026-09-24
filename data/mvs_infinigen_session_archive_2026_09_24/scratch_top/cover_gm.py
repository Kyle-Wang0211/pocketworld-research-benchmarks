# -*- coding: utf-8 -*-
"""量【表面覆盖】,不是点数。

我把「点数 -28.3%」说成了「覆盖 -28.3%」, 这是错的:
多层闸扔掉的本来就是【沿同一条视线堆叠的重复点】—— 扔掉它们, 像素照样被覆盖,
只是不再有第二层。所以必须直接问: 投回拍摄相机后, 到底有多少像素【不再有任何点】。

口径与 layerruler.py 完全一致(同 16 个相机、同 768x576、同内参缩放), 只是统计量换成:
  ① 每臂覆盖的像素占比
  ② 【t2 覆盖到的像素里, 本臂还覆盖多少】 <- 这才是"丢没丢表面"
  ③ 本臂独有(t2 没有)的像素 <- 反向检查
"""
import glob, os, sys
import numpy as np, torch, cv2
sys.path.insert(0, "/root")
from layerruler import read_cam

DEV = "cuda"
W, H, NCAM = 768, 576, 16
CAMDIR = "/root/mvs_P16k"
TAGS = ["GM_t2", "GM_t3", "GM_dyn", "GM_rnd"]
LAB = {"GM_t2": "固定 thres=2 (现役)", "GM_t3": "固定 thres=3",
       "GM_dyn": "官方自适应 D2HC", "GM_rnd": "随机抽稀(阴性对照)"}

camfs = sorted(glob.glob(os.path.join(CAMDIR, "cams", "*_cam.txt")))
step = max(1, len(camfs) // NCAM)
sel = camfs[::step][:NCAM]
cams = []
for p in sel:
    E, K = read_cam(p)
    ip = os.path.join(CAMDIR, "images", os.path.basename(p).split("_")[0] + ".jpg")
    im = cv2.imread(ip); oh, ow = im.shape[:2]
    K = K.copy(); K[0] *= W / ow; K[1] *= H / oh
    cams.append((E, K))
print("相机 %d 个, %dx%d\n" % (len(cams), W, H), flush=True)

flip = torch.tensor([1., -1., -1.], device=DEV)   # 展示帧 -> COLMAP 帧, 同 layerruler:54

def hitmask(tag):
    """返回 (NCAM, H*W) bool: 该臂在每个相机里覆盖了哪些像素"""
    pos = torch.from_numpy(np.fromfile("/root/bins_gm/%s.pos" % tag,
                                       dtype="<f4").reshape(-1, 3)).to(DEV)
    out = torch.zeros((len(cams), H * W), dtype=torch.bool, device=DEV)
    for ci, (E, K) in enumerate(cams):
        Et = torch.tensor(E, dtype=torch.float32, device=DEV)
        Kt = torch.tensor(K, dtype=torch.float32, device=DEV)
        for o in range(0, pos.shape[0], 40_000_000):
            P = pos[o:o + 40_000_000] * flip
            C = P @ Et[:3, :3].T + Et[:3, 3]
            z = C[:, 2]
            ok = z > 1e-6
            uv = (C @ Kt.T)
            u = (uv[:, 0] / z).long(); v = (uv[:, 1] / z).long()
            ok &= (u >= 0) & (u < W) & (v >= 0) & (v < H)
            out[ci].scatter_(0, (v[ok] * W + u[ok]), True)
            del P, C, z, uv, u, v, ok
    del pos; torch.cuda.empty_cache()
    return out

M = {}
for t in TAGS:
    M[t] = hitmask(t)
    n = int(M[t].sum())
    print("  %-22s 覆盖像素 %12s / %s  = %.2f%%"
          % (LAB[t], format(n, ","), format(len(cams)*H*W, ","), 100.0*n/(len(cams)*H*W)), flush=True)

base = M["GM_t2"]; nb = int(base.sum())
print("\n相对现役 thres=2 (它覆盖 %s 个像素):" % format(nb, ","))
hdr = "  %-22s %14s %12s %14s" % ("臂", "仍覆盖", "丢掉的像素", "本臂独有")
print(hdr); print("  " + "-"*(len(hdr)-2))
for t in TAGS:
    keep = int((M[t] & base).sum())
    lost = nb - keep
    only = int((M[t] & ~base).sum())
    pts = os.path.getsize("/root/bins_gm/%s.pos" % t)//12
    print("  %-22s %8s (%5.2f%%) %12s %14s   [点数 %.1f%%]"
          % (LAB[t], format(keep, ","), 100.0*keep/nb, format(lost, ","), format(only, ","),
             100.0*pts/(os.path.getsize("/root/bins_gm/GM_t2.pos")//12)), flush=True)
