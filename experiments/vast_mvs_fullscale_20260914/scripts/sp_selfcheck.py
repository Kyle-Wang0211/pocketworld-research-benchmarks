import os, sys, glob, numpy as np
from PIL import Image
sys.path.insert(0, "/root")
os.environ.setdefault("DIFFMVS_DIR", "/root/diffmvs")
import tartanground2mvsnet as tg   # 复用已验证的官方复刻 reproject_with_depth

EX = "/root/sp_probe/ex"

def load(scene, fid):
    im = Image.open("%s/scene_%s_%08d.png" % (EX, scene, fid))
    d  = np.load("%s/scene_%s_%08d.npy" % (EX, scene, fid))
    L  = [l.rstrip() for l in open("%s/scene_%s_%08d.txt" % (EX, scene, fid))]
    E  = np.fromstring(" ".join(L[1:5]), dtype=np.float32, sep=" ").reshape(4,4)
    K  = np.fromstring(" ".join(L[7:10]), dtype=np.float32, sep=" ").reshape(3,3)
    return im, d, K, E

print("=== ① alpha 通道 ===")
im, d, K, E = load("0", 0)
a = np.array(im)[:, :, 3]
print("mode", im.mode, " alpha uniq", np.unique(a)[:8], " alpha==255 frac %.6f" % float((a==255).mean()))
print("depth: min %.4f max %.4f  finite&>0 %.6f  >=1e3 frac %.6f" % (
      float(d.min()), float(d.max()), float((np.isfinite(d)&(d>0)).mean()), float((d>=1e3).mean())))
if (a==255).mean() < 1.0:
    bg = a < 128
    print("  背景(alpha<128)占比 %.6f  该处深度中位 %.4f" % (float(bg.mean()), float(np.median(d[bg]))))

print()
print("=== ② 全 shard alpha/深度体检 (398 帧) ===")
tot=0; nonopaque=0; dmax_all=[]; bad=0
for p in sorted(glob.glob(EX+"/*.png")):
    aa = np.array(Image.open(p))
    tot += 1
    if aa.shape[2]==4 and (aa[:,:,3]!=255).any(): nonopaque += 1
    dd = np.load(p[:-4]+".npy")
    if not (np.isfinite(dd).all() and (dd>0).all()): bad += 1
    dmax_all.append(float(dd.max()))
print("帧数 %d  有非不透明像素的帧 %d  深度非法帧 %d" % (tot, nonopaque, bad))
print("各帧 depth_max: 中位 %.2f  最大 %.2f  >=1e3 的帧数 %d" % (
      float(np.median(dmax_all)), float(np.max(dmax_all)), int(sum(1 for x in dmax_all if x>=1e3))))

print()
print("=== ③ 深度约定自证: 跨视图重投影 (只用相邻视角) ===")
def reproj_err(scene, i, j):
    _, di, Ki, Ei = load(scene, i)
    _, dj, Kj, Ej = load(scene, j)
    d2r, x2r, y2r = tg.reproject_with_depth(di, Ki, Ei, dj, Kj, Ej)
    H, W = di.shape
    xx, yy = np.meshgrid(np.arange(W), np.arange(H))
    dist = np.sqrt((x2r-xx)**2 + (y2r-yy)**2)
    dd = np.abs(d2r-di)/di
    m = (dist < 1.0)
    return float(np.median(dist)), float(np.median(dd[m])) if m.sum()>100 else float("nan"), float(m.mean())

for j in (1,2,3,7):
    px, rel, cov = reproj_err("0", 0, j)
    print("  view0 -> view%d :  像素误差中位 %8.4f px   深度相对差中位 %.5f   1px内占比 %.4f" % (j, px, rel, cov))

print()
print("=== ④ 背景(哨兵 d>=1e3)占比 —— OmniObject3D 就是栽在这 ===")
fr=[]
for p in sorted(glob.glob(EX+"/*.npy")):
    dd=np.load(p); fr.append(float((dd>=1e3).mean()))
fr=np.array(fr)
print("背景占比 p5/25/50/75/95: " + "  ".join("%.4f"%x for x in np.percentile(fr,[5,25,50,75,95])))
print("有效(前景)面积 中位 %.4f   背景>50%% 的帧数 %d/%d   背景>90%% 的帧 %d" % (
      1-np.median(fr), int((fr>0.5).sum()), len(fr), int((fr>0.9).sum())))
print()
print("=== ⑤ 官方过滤后的 p1/p99 (colmap2mvsnet 公式) vs 未过滤 ===")
for p in sorted(glob.glob(EX+"/*.npy"))[:5]:
    dd=np.load(p).ravel()
    raw=np.percentile(dd,[1,99])
    v=dd[(dd>0)&(dd<1e3)]
    flt=np.percentile(v,[1,99])
    print("  %s  未过滤 p1/p99 = %8.3f /%9.3f   |   官方过滤后 = %8.3f /%9.3f" % (
          os.path.basename(p), raw[0], raw[1], flt[0], flt[1]))

print()
print("=== 4 背景(哨兵 d>=1e3)占比 —— OmniObject3D 就是栽在这 ===")
fr=[]
for p in sorted(glob.glob(EX+"/*.npy")):
    dd=np.load(p); fr.append(float((dd>=1e3).mean()))
fr=np.array(fr)
print("背景占比 p5/25/50/75/95: " + "  ".join("%.4f"%x for x in np.percentile(fr,[5,25,50,75,95])))
print("有效(前景)面积中位 %.4f   背景>50%% 帧 %d/%d   背景>90%% 帧 %d" % (
      1-np.median(fr), int((fr>0.5).sum()), len(fr), int((fr>0.9).sum())))
print()
print("=== 5 官方过滤前后的 p1/p99 (colmap2mvsnet 公式) ===")
for p in sorted(glob.glob(EX+"/*.npy"))[:5]:
    dd=np.load(p).ravel(); raw=np.percentile(dd,[1,99])
    v=dd[(dd>0)&(dd<1e3)]; flt=np.percentile(v,[1,99])
    print("  %s  未过滤 %8.3f /%9.3f  |  官方过滤后 %8.3f /%9.3f" % (
          os.path.basename(p), raw[0], raw[1], flt[0], flt[1]))
