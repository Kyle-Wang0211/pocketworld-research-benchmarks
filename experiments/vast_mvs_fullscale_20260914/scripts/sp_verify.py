# -*- coding: utf-8 -*-
"""SimpleProc 转换自证。每项:先用公式算出预期值,再拿实测对。"""
import os, sys, glob, io, tarfile, numpy as np
from PIL import Image
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_pfm

OUT="/root/monotrain"; TAR="/root/sp_raw/shard-000000.tar"
scans=sorted([d for d in os.listdir(OUT) if d.startswith("sp_scene_")], key=lambda s:int(s.split("_")[-1]))
print("转出场景数 = %d" % len(scans))
fail=[]
def ck(name, got, exp, tol=0.0):
    ok = (abs(got-exp)<=tol) if isinstance(exp,(int,float)) and not isinstance(exp,bool) else (got==exp)
    print("  %-46s 预期 %-22s 实测 %-22s %s" % (name, exp, got, "OK" if ok else "*** FAIL ***"))
    if not ok: fail.append(name)

print()
print("=== 自证1 文件计数 (公式: 场景数x(8jpg+8cam+8pfm) + 场景数x1 pair) ===")
nj=len(glob.glob(OUT+"/sp_scene_*/blended_images/*.jpg"))
nc=len(glob.glob(OUT+"/sp_scene_*/cams/*_cam.txt"))
nd=len(glob.glob(OUT+"/sp_scene_*/rendered_depth_maps/*.pfm"))
np_=len(glob.glob(OUT+"/sp_scene_*/pair.txt"))
ck("jpg", nj, len(scans)*8); ck("cam", nc, len(scans)*8)
ck("pfm", nd, len(scans)*8); ck("pair.txt", np_, len(scans))

print()
print("=== 自证2 pfm 往返无损 (预期: read_pfm(写出) 与原 npy 逐元素严格相等) ===")
src={}
with tarfile.open(TAR) as tf:
    for m in tf:
        if m.isfile() and m.name.endswith(".npy"):
            src[m.name[:-4]]=tf.extractfile(m).read()
nbad=0; ncmp=0
for sc in scans[:10]:
    base=sc[3:]
    for fid in range(8):
        d0=np.load(io.BytesIO(src["%s_%08d"%(base,fid)]))
        d1=np.array(read_pfm("%s/%s/rendered_depth_maps/%08d.pfm"%(OUT,sc,fid))[0],dtype=np.float32)
        ncmp+=1
        if not np.array_equal(d0.astype(np.float32), d1): nbad+=1
ck("逐元素不等的深度图数 (比对 %d 张)"%ncmp, nbad, 0)

print()
print("=== 自证3 cam.txt 经 blend.py read_cam_file 回读,K/E 与原 txt 一致 ===")
class _D:
    def read_cam_file(self, filename):   # 逐字复刻 blend.py:51-61
        with open(filename) as f: lines=[l.rstrip() for l in f.readlines()]
        E=np.fromstring(" ".join(lines[1:5]),dtype=np.float32,sep=" ").reshape((4,4))
        K=np.fromstring(" ".join(lines[7:10]),dtype=np.float32,sep=" ").reshape((3,3))
        return K,E,float(lines[11].split()[0]),float(lines[11].split()[-1])
D=_D()
srctxt={}
with tarfile.open(TAR) as tf:
    for m in tf:
        if m.isfile() and m.name.endswith(".txt"): srctxt[m.name[:-4]]=tf.extractfile(m).read().decode()
maxKE=0.0
for sc in scans[:10]:
    base=sc[3:]
    for fid in range(8):
        K,E,_,_=D.read_cam_file("%s/%s/cams/%08d_cam.txt"%(OUT,sc,fid))
        L=[l.rstrip() for l in srctxt["%s_%08d"%(base,fid)].splitlines()]
        E0=np.fromstring(" ".join(L[1:5]),dtype=np.float32,sep=" ").reshape(4,4)
        K0=np.fromstring(" ".join(L[7:10]),dtype=np.float32,sep=" ").reshape(3,3)
        maxKE=max(maxKE, float(np.abs(E-E0).max()), float(np.abs(K-K0).max()))
ck("K/E 最大逐元素差", maxKE, 0.0)

print()
print("=== 自证4 depth_min/max == 独立重算的 p1/p99 (colmap2mvsnet 公式) ===")
maxdr=0.0
for sc in scans[:10]:
    base=sc[3:]
    for fid in range(8):
        _,_,dmin,dmax=D.read_cam_file("%s/%s/cams/%08d_cam.txt"%(OUT,sc,fid))
        d=np.load(io.BytesIO(src["%s_%08d"%(base,fid)]))
        zs=np.sort(d[np.isfinite(d)&(d>0)&(d<1e3)].astype(np.float64))
        e0=float(zs[int(len(zs)*.01)]); e1=float(zs[int(len(zs)*.99)])
        maxdr=max(maxdr, abs(dmin-e0)/e0, abs(dmax-e1)/e1)
ck("p1/p99 最大相对差 (<=写出精度 1e-6)", round(maxdr,9), 0.0, tol=2e-6)

print()
print("=== 自证5 blend.py mask —— 预期可精确算出 ===")
print("  公式: mask=(d>=p1)&(d<=p99).  有效像素中恰 98% 落在 [p1,p99];")
print("        背景(d>=1e3)全部 > p99 故被排除.  => mask.mean() 预期 = 0.98 x valid_frac")
worst=0.0; minmask=1.0
for sc in scans[:10]:
    base=sc[3:]
    for fid in range(8):
        _,_,dmin,dmax=D.read_cam_file("%s/%s/cams/%08d_cam.txt"%(OUT,sc,fid))
        d=np.array(read_pfm("%s/%s/rendered_depth_maps/%08d.pfm"%(OUT,sc,fid))[0],dtype=np.float32)
        v=np.isfinite(d)&(d>0)&(d<1e3)
        exp=0.98*float(v.mean()); got=float(((d>=dmin)&(d<=dmax)).mean())
        worst=max(worst, abs(got-exp)); minmask=min(minmask, got)
ck("|实测 mask 占比 - 0.98xvalid| 最大值", round(worst,6), 0.0, tol=0.01)
ck("最小 mask 占比 > 0 (上次训练崩在 assert mask.sum()>0)", minmask>0, True)
print("  最小 mask 占比实测 = %.4f" % minmask)

print()
print("=== 自证6 pair.txt 经 blend.py 解析 == 官方元组 ===")
off={}
for line in open("/root/mvsa_fork/data_splits/infinigen_cubism/train_pair_44000scenes.txt"):
    t=line.split()
    if t: off.setdefault(t[0],[]).append((int(t[1]),[int(x) for x in t[2:]]))
mism=0; nsrc=set(); ntup=0
for sc in scans:
    base=sc[3:]
    with open("%s/%s/pair.txt"%(OUT,sc)) as f:
        n=int(f.readline().rstrip())
        for k in range(n):                        # 逐字复刻 blend.py:39-40
            ref=int(f.readline().rstrip())
            srcs=[int(x) for x in f.readline().rstrip().split()[1::2]]
            nsrc.add(len(srcs)); ntup+=1
            if (ref,srcs)!=off[base][k]: mism+=1
ck("与官方元组不一致的条数 (共 %d 条)"%ntup, mism, 0)
ck("每条元组的 src 数取值集合", sorted(nsrc), [7])
ck("元组总数 = 场景数 x 8", ntup, len(scans)*8)

print()
print("=== 自证7 blend.py:41 不跳过 —— len(src)>=nviews-1 ===")
print("  src=7 => 可用的最大 nviews = 8.  官方 CasDiffMVS 用 9 会把全部元组跳光.")
ck("trainviews=8 可用", 7>=8-1, True)
ck("trainviews=9 会被跳光(阴性对照)", 7>=9-1, False)

print()
print("===== %s =====" % ("全部自证通过" if not fail else "失败项: "+", ".join(fail)))
sys.exit(1 if fail else 0)
