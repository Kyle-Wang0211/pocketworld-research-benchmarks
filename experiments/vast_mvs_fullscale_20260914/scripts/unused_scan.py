# 统计三个真实域里「官方 blend.py 不会读到」的字节:
#   (a) 场景目录存在但 monotrain 没链接 (且 nviews=8 下元组数=0 的更是必删)
#   (b) 已链接场景里, 任何合格 ref (blend.py:41 srcs>=7) 的 {ref}∪srcs 都不含的帧
#   (c) 文件名不是 %08d.jpg / %08d.pfm / cams 的文件 (如 _masked.jpg)
import os, re, sys
NV = 8
ROOTS = {"bmvs": "/root/bmvs/data", "ta":   "/root/ta2/blendfmt", "tg":   "/root/tg_conv"}
linked = {}
for n in os.listdir("/root/monotrain"):
    p = os.path.join("/root/monotrain", n)
    if os.path.islink(p):
        linked[os.path.realpath(p)] = n
for dom, root in ROOTS.items():
    unl_scans = unl_bytes = unl_tup = 0
    used_b = unused_b = extra_b = 0; unused_frames = 0; total_frames = 0
    for s in sorted(os.listdir(root)):
        sd = os.path.join(root, s)
        if not os.path.isdir(sd): 
            continue
        pair = os.path.join(sd, "cams", "pair.txt")
        used = set(); tup = 0
        if os.path.isfile(pair):
            with open(pair) as f:
                try: n = int(f.readline())
                except: n = 0
                for _ in range(n):
                    r = f.readline().split()
                    t = f.readline().split()
                    if not r: break
                    srcs = t[1::2]
                    if len(srcs) >= NV - 1:
                        tup += 1; used.add(int(r[0])); used.update(int(x) for x in srcs)
        # 字节归类
        sb_used = sb_unused = sb_extra = 0; fr = set()
        for sub, pat in (("blended_images", r"^(\d{8})\.jpg$"), ("rendered_depth_maps", r"^(\d{8})\.pfm$")):
            d = os.path.join(sd, sub)
            if not os.path.isdir(d): continue
            with os.scandir(d) as it:
                for e in it:
                    sz = e.stat().st_size
                    m = re.match(pat, e.name)
                    if not m: sb_extra += sz; continue
                    fid = int(m.group(1)); fr.add(fid)
                    if fid in used: sb_used += sz
                    else: sb_unused += sz
        if os.path.realpath(sd) not in linked:
            unl_scans += 1; unl_bytes += sb_used + sb_unused + sb_extra; unl_tup += tup
            continue
        used_b += sb_used; unused_b += sb_unused; extra_b += sb_extra
        total_frames += len(fr); unused_frames += len(fr - used)
    print("%-4s 未链接场景 %4d 个 = %6.1f GB (它们在 nviews=8 下共 %d 元组)" % (dom, unl_scans, unl_bytes/1e9, unl_tup))
    print("     已链接场景: 会读到 %6.1f GB | 无任何元组引用的帧 %d/%d = %6.1f GB | 非官方文件名(_masked等) %6.1f GB"
          % (used_b/1e9, unused_frames, total_frames, unused_b/1e9, extra_b/1e9))
