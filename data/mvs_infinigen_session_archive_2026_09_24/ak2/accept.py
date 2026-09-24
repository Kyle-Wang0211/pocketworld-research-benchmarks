#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 批量验收。
  --what load   : 随机抽 N 个场景过 blend.py (真 MVSDataset), 报 mask/depth 统计
  --what pfm    : 直接比【写好的 pfm】: v2(/root/ak_blend_v2) vs v1(/root/arkit_blend)
                  判据 = 2x2 邻块非常数比例 (x3 复制的理论上限 0.556)
                  阴性对照 = 把 v2 的图再压成 256x192 拉回, 必须掉回 v1 档
  --what agg    : 聚合转换日志的全部自证数字
"""
import argparse, glob, os, random, re, sys
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs_full")

def read_pfm(p):
    with open(p, "rb") as f:
        assert f.readline().strip() == b"Pf"
        w, h = (int(x) for x in f.readline().split())
        sc = float(f.readline())
        d = np.frombuffer(f.read(w*h*4), "<f4" if sc < 0 else ">f4").reshape(h, w)
    return np.flipud(d).copy()

def nonconst2x2(x):
    H, W = x.shape
    b = x[:H//2*2, :W//2*2].reshape(H//2, 2, W//2, 2).transpose(0, 2, 1, 3).reshape(-1, 4)
    ok = (b > 0).all(1); b = b[ok]
    return (float((b.max(1) != b.min(1)).mean()) if len(b) else np.nan), int(ok.sum())

ap = argparse.ArgumentParser(); ap.add_argument("--what", default="pfm"); ap.add_argument("--n", type=int, default=12)
a = ap.parse_args()
V2 = "/root/ak_blend_v2"; V1 = "/root/arkit_blend"
scans = sorted(os.path.basename(d) for d in glob.glob(V2+"/ak_*"))
random.seed(7)

if a.what == "load":
    os.chdir("/root/diffmvs_full")
    from datasets.blend import MVSDataset
    sel = random.sample(scans, min(a.n, len(scans)))
    open("/tmp/acc.txt", "w").write("\n".join(sel)+"\n")
    ds = MVSDataset(V2, "/tmp/acc.txt", mode="train", nviews=5, ndepths=384)
    print("随机 %d 个场景 -> %d metas" % (len(sel), len(ds)))
    mv = []; bad = 0
    idx = sorted(random.sample(range(len(ds)), min(200, len(ds))))
    for i in idx:
        s = ds[i]
        for k in ("stage1","stage2","stage3","stage4"):
            if not np.isfinite(s["depth"][k]).all(): bad += 1
        assert np.asarray(s["imgs"]).shape == (5,3,576,768), np.asarray(s["imgs"]).shape
        mv.append(float(s["mask"]["stage4"].mean()))
    print("  抽 %d 个 item: 全部 5x3x576x768, 非 finite 的 stage %d 个" % (len(idx), bad))
    print("  stage4 mask 有效比例: 中位 %.4f  p10 %.4f  min %.4f" % (np.median(mv), np.percentile(mv,10), min(mv)))
    print("  场景清单: %s" % ", ".join(sel))

elif a.what == "pfm":
    sel = random.sample(scans, min(a.n, len(scans)))
    r2, r1, rdeg = [], [], []
    for sc in sel:
        for p in sorted(glob.glob("%s/%s/rendered_depth_maps/*.pfm" % (V2, sc)))[::37][:4]:
            d = read_pfm(p); v, _ = nonconst2x2(d)
            if np.isfinite(v): r2.append(v)
            deg = cv2.resize(cv2.resize(d, (256,192), interpolation=cv2.INTER_AREA), (768,576),
                             interpolation=cv2.INTER_NEAREST)
            v, _ = nonconst2x2(deg)
            if np.isfinite(v): rdeg.append(v)
        for p in sorted(glob.glob("%s/%s/rendered_depth_maps/*.pfm" % (V1, sc)))[::37][:4]:
            v, _ = nonconst2x2(read_pfm(p))
            if np.isfinite(v): r1.append(v)
    print("2x2 邻块非常数比例 (x3 复制的理论上限 0.556) —— %d 个场景" % len(sel))
    print("  v2 FARO           中位 %.4f  p10 %.4f  (n=%d)" % (np.median(r2), np.percentile(r2,10), len(r2)))
    print("  v1 LiDAR 上采样    中位 %.4f  p90 %.4f  (n=%d)" % (np.median(r1), np.percentile(r1,90), len(r1)))
    print("  v2 退化对照(阴性)  中位 %.4f  (n=%d)  <- 必须掉回 v1 档" % (np.median(rdeg), len(rdeg)))

elif a.what == "agg":
    pat = re.compile(r"ak_(\d+)\[(\w+)\]: 帧 (\d+) \| 有位姿 (\d+) \| 关键帧 (\d+) \(间距中位 ([\d.]+).*插值 ([\d.]+) / 最近邻 ([\d.]+) / 写反 ([\d.]+) m \| 原生有效率 ([\d.]+) -> 768x576 ([\d.]+)")
    rows = []
    for f in ("/root/ak2_all_v2.log", "/root/ak2_smoke.log", "/root/ak2_pilot_hi.log", "/root/ak2_pilot_lo.log"):
        if os.path.exists(f):
            for l in open(f):
                m = pat.search(l)
                if m: rows.append(m.groups())
    seen = {}
    for r in rows: seen[r[0]] = r
    rows = list(seen.values())
    v1k = {}
    for l in open("/root/arkit_all.log"):
        m = re.match(r"\s+ak_(\d+): 图 \d+ \| 有位姿 \d+ \| 关键帧 (\d+)", l)
        if m: v1k[m.group(1)] = int(m.group(2))
    for mode in ("highres", "lowres"):
        rs = [r for r in rows if r[1] == mode]
        if not rs: continue
        A = np.array([[int(x[2]),int(x[3]),int(x[4]),float(x[5]),float(x[6]),float(x[7]),float(x[8]),float(x[9]),float(x[10])] for x in rs])
        print("== %s 臂  %d 个场景 ==" % (mode, len(rs)))
        print("   帧 %d -> 有位姿 %d (%.2f%%) -> 关键帧 %d" % (A[:,0].sum(), A[:,1].sum(), 100.*A[:,1].sum()/A[:,0].sum(), A[:,2].sum()))
        vs = [(int(x[4]), v1k.get(x[0])) for x in rs if v1k.get(x[0])]
        if vs:
            k2 = sum(a_ for a_,b_ in vs); k1 = sum(b_ for a_,b_ in vs)
            rr = np.array([a_/max(1,b_) for a_,b_ in vs])
            print("   v1 对照 (%d 个可配对): v1 %d -> v2 %d  总倍数 %.3f | 逐视频 中位 %.3f p10 %.3f p90 %.3f"
                  % (len(vs), k1, k2, k2/max(1,k1), np.median(rr), np.percentile(rr,10), np.percentile(rr,90)))
        print("   关键帧间距 中位 %.4f (设计 0.10)" % np.median(A[:,3]))
        print("   跨视|dz|: 插值 中位 %.4f p90 %.4f | 最近邻 中位 %.4f | 写反 中位 %.4f m" % (np.median(A[:,4]), np.percentile(A[:,4],90), np.median(A[:,5]), np.median(A[:,6])))
        print("   插值 < 写反 的场景: %d / %d ; 插值 < 最近邻: %d / %d" % (int((A[:,4]<A[:,6]).sum()), len(A), int((A[:,4]<A[:,5]).sum()), len(A)))
        if mode == "highres":
            print("   原生有效率 中位 %.4f p10 %.4f min %.4f | 768x576 中位 %.4f min %.4f"
                  % (np.median(A[:,7]), np.percentile(A[:,7],10), A[:,7].min(), np.median(A[:,8]), A[:,8].min()))
