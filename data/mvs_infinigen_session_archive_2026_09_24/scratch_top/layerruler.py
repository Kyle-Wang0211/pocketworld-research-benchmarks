# -*- coding: utf-8 -*-
"""多层/粘连的尺子 —— 沿拍摄视线的逐像素深度成簇分析。

为什么是这个量: 用户判的「多层」物理定义就是【沿同一条视线, 本该一个表面, 却出现多簇点】。
  这正好可以把点云投回【拍摄相机】后逐像素统计: 单层 => 像素内深度紧成一簇;
  多层 => 排序后的深度里出现明显空隙。粘连则表现为厚度整体变大。

前四把尺子为什么废了(都试过):
  layer_gap2 的 ref 间分歧率     —— 三次与用户肉眼反向
  局部平面拟合厚度               —— 六个 epoch 只差 0.6 mm, 无分辨力
  渲染覆盖率                     —— 会饱和, 且沿视线堆叠根本看不见(被 z-buffer 挡住)
  ETH3D 激光 F1                  —— 我们自己的场景没有真值

判据(先声明, 后检验, 不事后调):
  多层率(G) = 满足「像素内点数>=MINPTS 且 排序深度的最大相邻空隙 > G」的像素占比
  厚度      = 像素内 深度max - 深度min
  G 扫 {0.5, 1, 2, 5} cm, 不挑单一阈值; 分「全图」与「低纹理区」两档。
  低纹理区口径与 layer_gap2 相同: 11x11 灰度 std 最平的 25%。

验收闸: 必须复现用户对 ep0..ep6 的既有判决(多层单调递增)。不过闸就报废, 不交付。
"""
import argparse, glob, json, math, os, sys
import numpy as np, torch

DEV = "cuda"
MINPTS = 4                      # 像素内至少几个点才参与统计(少于此无法判断成簇)
GAPS_CM = [0.5, 1.0, 2.0, 5.0]
LOWTEX_Q = 0.25                 # layer_gap2 口径: 最平的 25%
SLANT_REL = 0.0                 # 掠射控制: 实测使结果更差, 默认关闭(>0 启用)
COMP_MIN = [50, 200, 1000]      # 连通域大小档: 第二层是不是【连成片】


def read_cam(p):
    L = open(p).read().strip().split("\n")
    E = np.array([[float(x) for x in L[i].split()] for i in range(1, 5)], dtype=np.float64)
    K = np.array([[float(x) for x in L[i].split()] for i in range(7, 10)], dtype=np.float64)
    return E, K


def lowtex_mask(img_path, W, H):
    import cv2
    g = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    if g is None:
        return None
    g = cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)
    m = cv2.boxFilter(g, -1, (11, 11))
    s = np.sqrt(np.maximum(cv2.boxFilter(g * g, -1, (11, 11)) - m * m, 0))
    thr = np.quantile(s, LOWTEX_Q)
    return torch.from_numpy((s <= thr)).to(DEV).reshape(-1)


def analyse_cloud(pos, cams, W, H, chunk=40_000_000, per_pixel=None):
    """pos: (N,3) torch float32 on GPU, 展示帧(y,z 已翻)。cams: [(E,K,imgpath)]"""
    # 展示帧 -> COLMAP 帧 (ply2bins 做的是 y,z 取反)
    flip = torch.tensor([1.0, -1.0, -1.0], device=DEV)
    acc = {g: [] for g in GAPS_CM}
    acc_lt = {g: [] for g in GAPS_CM}
    th_all, th_lt = [], []
    for (E, K, imgp) in cams:
        R = torch.tensor(E[:3, :3], dtype=torch.float32, device=DEV)
        t = torch.tensor(E[:3, 3], dtype=torch.float32, device=DEV)
        fx, fy = float(K[0, 0]), float(K[1, 1])
        cx, cy = float(K[0, 2]), float(K[1, 2])
        keys = []
        for o in range(0, pos.shape[0], chunk):
            P = pos[o:o + chunk] * flip
            Pc = P @ R.T + t
            z = Pc[:, 2]
            ok = z > 1e-3
            u = (Pc[:, 0] * fx / z.clamp(min=1e-3) + cx).round().long()
            v = (Pc[:, 1] * fy / z.clamp(min=1e-3) + cy).round().long()
            ok &= (u >= 0) & (u < W) & (v >= 0) & (v < H)
            if not bool(ok.any()):
                continue
            pix = (v[ok] * W + u[ok]).to(torch.int64)
            zq = (z[ok] * 1e4).clamp(0, 2**31 - 1).to(torch.int64)      # 0.1 mm 量化
            keys.append((pix << 32) | zq)
            del P, Pc, z, u, v, ok
        if not keys:
            continue
        k = torch.cat(keys); del keys
        k, _ = torch.sort(k)
        pix = k >> 32
        zz = (k & 0xFFFFFFFF).to(torch.float32) / 1e4                   # 米
        # 段边界
        newseg = torch.ones_like(pix, dtype=torch.bool)
        newseg[1:] = pix[1:] != pix[:-1]
        seg = torch.cumsum(newseg.to(torch.int64), 0) - 1
        nseg = int(seg[-1].item()) + 1
        cnt = torch.zeros(nseg, dtype=torch.int64, device=DEV).scatter_add_(0, seg, torch.ones_like(seg))
        zmin = torch.full((nseg,), float("inf"), device=DEV).scatter_reduce_(0, seg, zz, reduce="amin")
        zmax = torch.full((nseg,), float("-inf"), device=DEV).scatter_reduce_(0, seg, zz, reduce="amax")
        d = torch.zeros_like(zz)
        d[1:] = zz[1:] - zz[:-1]
        d[newseg] = 0.0                                                  # 跨段的差无意义
        gmax = torch.zeros(nseg, device=DEV).scatter_reduce_(0, seg, d, reduce="amax")
        segpix = torch.zeros(nseg, dtype=torch.int64, device=DEV).scatter_reduce_(0, seg, pix, reduce="amax")
        # 🔴 掠射控制: 单个平面在掠射角下, 一个像素内本来就横跨很大深度, 会被误判成多层。
        #    用【逐像素最近深度】构成的深度图求梯度, 排除梯度大(=倾斜/边缘)的像素。
        #    阈值按「相邻像素深度差 < 该像素深度的 SLANT_REL」定, 是相对量不是绝对量。
        zimg = torch.full((W * H,), float("nan"), device=DEV)
        zimg[segpix] = zmin
        Z = zimg.reshape(H, W)
        gx = torch.zeros_like(Z); gy = torch.zeros_like(Z)
        gx[:, 1:-1] = (Z[:, 2:] - Z[:, :-2]).abs() / 2
        gy[1:-1, :] = (Z[2:, :] - Z[:-2, :]).abs() / 2
        grad = torch.nan_to_num(torch.maximum(gx, gy), nan=1e9).reshape(-1)
        frontal = grad[segpix] < (SLANT_REL * zmin) if SLANT_REL > 0 else torch.ones_like(cnt, dtype=torch.bool)
        use = (cnt >= MINPTS) & frontal
        # 逐像素落盘, 供跨臂配对(只在所有臂都覆盖到的公共像素上比, 消掉覆盖面差异这个混淆)
        if per_pixel is not None:
            for g in GAPS_CM:
                buf = torch.zeros(W * H, dtype=torch.int8, device=DEV)
                buf[segpix[use]] = (gmax[use] > g / 100.0).to(torch.int8) + 1   # 0=未覆盖 1=单层 2=多层
                per_pixel.setdefault(g, []).append(buf.cpu())
        lt = lowtex_mask(imgp, W, H)
        use_lt = use & lt[segpix] if lt is not None else None
        if int(use.sum()) == 0:
            continue
        th_all.append(float((zmax[use] - zmin[use]).median()))
        for g in GAPS_CM:
            acc[g].append(float((gmax[use] > g / 100.0).float().mean()))
        if use_lt is not None and int(use_lt.sum()) > 0:
            th_lt.append(float((zmax[use_lt] - zmin[use_lt]).median()))
            for g in GAPS_CM:
                acc_lt[g].append(float((gmax[use_lt] > g / 100.0).float().mean()))
        del k, pix, zz, seg, cnt, zmin, zmax, d, gmax, segpix
        torch.cuda.empty_cache()
    return (np.mean(th_all) if th_all else float("nan"),
            {g: (100 * np.mean(acc[g]) if acc[g] else float("nan")) for g in GAPS_CM},
            np.mean(th_lt) if th_lt else float("nan"),
            {g: (100 * np.mean(acc_lt[g]) if acc_lt[g] else float("nan")) for g in GAPS_CM})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bins", default="/root/bins_full")
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--camdir", default="/root/mvs_P16k")
    ap.add_argument("--ncam", type=int, default=16)
    ap.add_argument("--w", type=int, default=768)
    ap.add_argument("--h", type=int, default=576)
    a = ap.parse_args()

    camfs = sorted(glob.glob(os.path.join(a.camdir, "cams", "*_cam.txt")))
    step = max(1, len(camfs) // a.ncam)
    sel = camfs[::step][:a.ncam]
    cams = []
    for p in sel:
        E, K = read_cam(p)
        # cam.txt 内参是原生 4032x3024 的, 缩到 W x H
        import cv2
        ip = os.path.join(a.camdir, "images", os.path.basename(p).split("_")[0] + ".jpg")
        im = cv2.imread(ip); oh, ow = im.shape[:2]
        K = K.copy(); K[0] *= a.w / ow; K[1] *= a.h / oh
        cams.append((E, K, ip))
    print("相机 %d 个, 分辨率 %dx%d, MINPTS=%d, 低纹理=最平 %d%%\n" % (len(cams), a.w, a.h, MINPTS, int(100*LOWTEX_Q)))
    hdr = "%-14s %10s | %9s %s | %9s %s" % ("臂", "点数", "厚度中位", "".join("  >%.1fcm" % g for g in GAPS_CM),
                                            "低纹厚度", "".join("  >%.1fcm" % g for g in GAPS_CM))
    print(hdr); print("-" * len(hdr))
    PP = {}
    LT = []
    for p in sel:
        ip = os.path.join(a.camdir, "images", os.path.basename(p).split("_")[0] + ".jpg")
        LT.append(lowtex_mask(ip, a.w, a.h).cpu())
    for tg in a.tags:
        p = os.path.join(a.bins, tg + ".pos")
        n = os.path.getsize(p) // 12
        pos = torch.from_numpy(np.fromfile(p, dtype="<f4").reshape(-1, 3)).to(DEV)
        pp = {}
        th, rate, thl, ratel = analyse_cloud(pos, cams, a.w, a.h, per_pixel=pp)
        PP[tg] = pp
        print("%-14s %10s | %7.1fmm %s | %7.1fmm %s"
              % (tg, format(n, ","), th * 1000, "".join("  %6.2f%%" % rate[g] for g in GAPS_CM),
                 thl * 1000, "".join("  %6.2f%%" % ratel[g] for g in GAPS_CM)), flush=True)
        del pos; torch.cuda.empty_cache()

    # ---------------- 连通性: 第二层是「成片」还是「零散」 ----------------
    import cv2 as _cv
    print()
    print("连通性(用户原话「越来越坚实」): 有第二簇的像素里, 落在大连通域中的占比")
    print("  口径: >2cm 空隙的像素做 8 邻域连通, 统计落在 >=N 像素连通域里的比例")
    h3 = "%-14s | %s" % ("臂", "".join("  片>=%-5d" % c for c in COMP_MIN))
    print(h3); print("-" * len(h3))
    for tg in a.tags:
        fr = {c: [] for c in COMP_MIN}
        for ci, buf in enumerate(PP[tg][2.0]):
            m = ((buf == 2).numpy().reshape(a.h, a.w) & LT[ci].cpu().numpy().reshape(a.h, a.w)).astype("uint8")
            if m.sum() < 10:
                continue
            nlab, _, st, _ = _cv.connectedComponentsWithStats(m, 8)
            areas = st[1:, _cv.CC_STAT_AREA]
            tot = int(areas.sum())
            for c in COMP_MIN:
                fr[c].append(float(areas[areas >= c].sum()) / max(tot, 1))
        print("%-14s | %s" % (tg, "".join("  %7.2f%%" % (100 * np.mean(fr[c])) for c in COMP_MIN)), flush=True)

    # ---------------- 配对比较: 只用所有臂都覆盖到的公共像素 ----------------
    print()
    print("配对比较(只在【所有臂都覆盖到】的公共像素上, 消掉覆盖面差异)")
    hdr2 = "%-14s %10s | %s" % ("臂", "公共像素", "".join("  >%.1fcm" % g for g in GAPS_CM))
    print(hdr2); print("-" * len(hdr2))
    for band, bmask in (("全图", None), ("低纹理", LT)):
        for g in GAPS_CM[:1]:
            pass
        common = None
        for tg in a.tags:
            cov = torch.cat([(b > 0) for b in PP[tg][GAPS_CM[0]]])
            common = cov if common is None else (common & cov)
        if bmask is not None:
            common = common & torch.cat(bmask)
        ncom = int(common.sum())
        print("  [%s] 公共像素 %s" % (band, format(ncom, ",")))
        for tg in a.tags:
            vals = []
            for g in GAPS_CM:
                x = torch.cat(PP[tg][g])
                vals.append(100.0 * float((x[common] == 2).sum()) / max(ncom, 1))
            print("    %-12s %10s | %s" % (tg, format(ncom, ","), "".join("  %6.2f%%" % v for v in vals)))
