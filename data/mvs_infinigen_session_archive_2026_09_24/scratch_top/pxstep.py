# 量一件事: 网络在【最细一级】把深度假设撒开时, 相邻两个假设在源图上差多少【像素】。
#
# 为什么这个数重要 —— 平面扫描的设计规则(Collins 1996 space-sweep 起, MVS 沿用至今):
#   相邻深度假设在源视图上应相隔约 1 像素。更密是浪费算力, 更疏则代价曲线发生混叠,
#   真正的匹配峰落在两个假设之间, 亚像素回归读不出来。
#
# 代码事实(上游 cd10d5c, 已核):
#   diffusion.py:144   depth_interval = 1.0 / depth_values.size(1)     # =1/384, 归一化【逆深度】
#   diffusion.py:15    depth_interals_ratio=[4,2,1]                    # 最细级 ratio=1
#   module.py:616      depth_inteval_pixel=depth_interval              # 变量名带 pixel, 实际不是像素
#   脚本               --min_radius 0.125 --max_radius 8  --CostNum 0 4 4
#   => 搜索半径 = (1/384) * ratio * mult,  mult 由置信度在 [0.125, 8] 之间调
#   => 4 个样本铺满 [-r,+r], 步长 = 2r/3
#   全程【没有任何一项依赖图像分辨率】。
#
# 而像素位移 = f_px * B * Δ(1/z), 其中 f_px 【正比于分辨率】。
# 所以同一个归一化步长, 分辨率翻 5.25 倍, 在图上就是 5.25 倍的像素。
import numpy as np, os, sys, glob

def read_cam(p):
    t = open(p).read().split()
    E = np.array(t[1:17], dtype=np.float64).reshape(4,4)
    K = np.array(t[18:27], dtype=np.float64).reshape(3,3)
    tail = [float(x) for x in t[27:]]
    dmin = tail[0]
    if len(tail) >= 4:   dmax = tail[3]
    elif len(tail) == 2: dmax = dmin + tail[1]*384      # 退化格式: min + interval*N
    else:                dmax = tail[-1]
    return E, K, dmin, dmax

def cam_center(E):
    R, t = E[:3,:3], E[:3,3]
    return -R.T @ t

def read_pair(p):
    L = open(p).read().split('\n')
    n = int(L[0]); out = []
    for i in range(n):
        ref = int(L[1+2*i]); f = L[2+2*i].split()
        k = int(f[0]); src = [int(f[1+2*j]) for j in range(k)]
        out.append((ref, src))
    return out

def adaptive_hw(h, w, max_h, max_w, base=32):
    """逐字复刻 datasets/mvs.py:104-123 scale_img_adaptive"""
    if h > max_h or w > max_w:
        sh, sw = 1.0*max_h/h, 1.0*max_w/w
        new_w, new_h = sw*w//base*base, sh*h//base*base
    else:
        new_w, new_h = 1.0*w//base*base, 1.0*h//base*base
    return new_h, new_w, new_w/w, new_h/h

def analyse(root, name, rungs, native_wh=None, nview=10):
    camdir = None
    for c in ("cams","cams_1","cam"):
        if os.path.isdir(os.path.join(root,c)): camdir = os.path.join(root,c); break
    if camdir is None:
        print("  %-14s 没找到 cams/" % name); return
    pairs = read_pair(os.path.join(root,"pair.txt"))
    if native_wh is None:
        import cv2
        im = sorted(glob.glob(os.path.join(root,"images","*")))[0]
        a = cv2.imread(im); native_wh = (a.shape[1], a.shape[0])
    W0, H0 = native_wh
    cams = {}
    for f in glob.glob(os.path.join(camdir,"*_cam.txt")):
        vid = int(os.path.basename(f).split('_')[0]); cams[vid] = read_cam(f)

    print("  %s   原生 %dx%d   视图 %d   对 %d" % (name, W0, H0, len(cams), len(pairs)))
    # 用 cam.txt 的内参先归一到原生像素
    k0 = cams[pairs[0][0]][1]
    print("    cam.txt 内参 fx=%.1f fy=%.1f cx=%.1f cy=%.1f  (若 cx≈W0/2 则内参就是按原生写的)"
          % (k0[0,0],k0[1,1],k0[0,2],k0[1,2]))

    rows = []
    for (tag, max_h, max_w) in rungs:
        nh, nw, sw, sh = adaptive_hw(H0, W0, max_h, max_w)
        steps = []
        for ref, src in pairs:
            if ref not in cams: continue
            Er,Kr,dmin,dmax = cams[ref]
            if dmax <= dmin or dmin <= 0: continue
            qmin, qmax = 1.0/dmax, 1.0/dmin
            f_native = 0.5*(Kr[0,0]+Kr[1,1])
            f = f_native * 0.5*(sw+sh)
            Cr = cam_center(Er)
            for s in src[:nview-1]:
                if s not in cams: continue
                B = np.linalg.norm(Cr - cam_center(cams[s][0]))
                if B <= 0: continue
                for mult, lab in ((0.125,'lo'), (8.0,'hi')):
                    r_norm = (1.0/384)*1.0*mult          # 最细级 ratio=1
                    step_norm = 2*r_norm/3               # CostNum=4 个样本铺满 ±r
                    dq = step_norm*(qmax-qmin)
                    steps.append((lab, f*B*dq))
        lo = np.median([v for l,v in steps if l=='lo'])
        hi = np.median([v for l,v in steps if l=='hi'])
        rows.append((tag, int(nw), int(nh), lo, hi))
    print("    %-12s %-12s %14s %14s" % ("档","实际尺寸","步长@最小半径","步长@最大半径"))
    for tag,nw,nh,lo,hi in rows:
        print("    %-12s %-12s %11.3f px %11.3f px" % (tag, "%dx%d"%(nw,nh), lo, hi))
    return rows

OURS = [("768x576",576,768),("1536x1152",1152,1536),("2016x1504",1504,2016),
        ("2048x1536",1536,2048),("4032x3024",3024,4032)]
ETH  = [("官方1920x1280",1280,1920),("768x576",576,768),("原生",4800,6400)]

print("="*74)
print("我们的素材 (mvs_P16k)")
print("="*74)
analyse("/root/mvs_P16k","mvs_P16k",OURS)
print()
print("="*74)
print("ETH3D 阳性对照 (官方跑 1920x1280)")
print("="*74)
for sc in ("office","delivery_area","pipes","kicker"):
    p = "/root/eth3d_mvs/"+sc
    if os.path.isdir(p): analyse(p, sc, ETH)
