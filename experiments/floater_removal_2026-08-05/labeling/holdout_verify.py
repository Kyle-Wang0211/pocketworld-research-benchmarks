#!/usr/bin/env python3
"""浮点真值标注:留出视角光度验证(与所有候选判据独立)。
真点:投影到不在其 track 里的相机上,应看到同一块表面纹理(NCC 高)。
浮点(深度错):投影落到别处,NCC 低。
输出 per-point NCC 统计 + 供人眼复核的 patch 条带图。"""
import struct, sys, zlib, json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = f"{HERE}/../scale_knife/out_model"
PHOTOS = f"{HERE}/../photos_decoded"
ORDER = [l.strip() for l in open(f"{HERE}/../scale_knife/work/order.txt") if l.strip()]

def read_cams(p):
    d = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        NP = {0:3,1:4,2:4,3:5,4:8}
        for _ in range(n):
            cid, mid, w, h = struct.unpack("<IiQQ", f.read(24))
            k = NP.get(mid, 4)
            d[cid] = (np.array(struct.unpack("<%dd"%k, f.read(8*k))), w, h)
    return d

def read_imgs(p):
    d = {}
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            iid = struct.unpack("<I", f.read(4))[0]
            q = np.array(struct.unpack("<4d", f.read(32)))
            t = np.array(struct.unpack("<3d", f.read(24)))
            cid = struct.unpack("<I", f.read(4))[0]
            nm = b""
            while True:
                c = f.read(1)
                if c == b"\x00": break
                nm += c
            np2 = struct.unpack("<Q", f.read(8))[0]; f.read(24*np2)
            q = q/np.linalg.norm(q); w,x,y,z = q
            R = np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                          [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                          [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
            d[iid] = dict(R=R, t=t, cid=cid, name=nm.decode(), C=-R.T@t)
    return d

def read_pts(p):
    xyz, tracks = [], []
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            struct.unpack("<Q", f.read(8))
            xyz.append(struct.unpack("<ddd", f.read(24))); f.read(3)
            struct.unpack("<d", f.read(8))
            tl = struct.unpack("<Q", f.read(8))[0]
            tr = np.frombuffer(f.read(tl*8), dtype="<u4").reshape(tl,2)
            tracks.append(tr[:,0].copy())
    return np.asarray(xyz), tracks

def load_jpeg_gray(path, cache={}):
    if path in cache: return cache[path]
    import subprocess, tempfile
    # 用 sips 转 8-bit 灰度 PNG 再手工解 —— 避免 PIL 依赖
    with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as tf:
        tmp = tf.name
    subprocess.run(["sips","-s","format","tiff","-s","formatOptions","none",
                    "-Z","1008", path,"--out",tmp],
                   capture_output=True)
    import struct as st
    data = open(tmp,"rb").read(); os.unlink(tmp)
    cache.clear()  # 只缓存一张,省内存
    arr = decode_tiff_gray(data)
    cache[path] = arr
    return arr

def decode_tiff_gray(d):
    bo = d[:2]
    en = "<" if bo == b"II" else ">"
    off = struct.unpack(en+"I", d[4:8])[0]
    n = struct.unpack(en+"H", d[off:off+2])[0]
    tags = {}
    for i in range(n):
        e = off+2+i*12
        tag, typ, cnt = struct.unpack(en+"HHI", d[e:e+8])
        val = struct.unpack(en+"I", d[e+8:e+12])[0]
        if typ == 3 and cnt == 1: val = struct.unpack(en+"H", d[e+8:e+10])[0]
        tags[tag] = (val, cnt, typ)
    W = tags[256][0]; H = tags[257][0]; spp = tags.get(277,(1,))[0]
    so = tags[273]; sc = tags[279]
    def arr_at(t):
        val, cnt, typ = t
        if cnt == 1: return [val]
        sz = 2 if typ == 3 else 4
        fmt = en + ("H" if typ==3 else "I")
        return [struct.unpack(fmt, d[val+i*sz:val+i*sz+sz])[0] for i in range(cnt)]
    offs, cnts = arr_at(so), arr_at(sc)
    buf = b"".join(d[o:o+c] for o,c in zip(offs,cnts))
    a = np.frombuffer(buf, np.uint8)
    a = a[:W*H*spp].reshape(H, W, spp)
    return a[:,:,:3].mean(2).astype(np.float32) if spp>=3 else a[:,:,0].astype(np.float32)

def main():
    cams, imgs = read_cams(f"{MODEL}/cameras.bin"), read_imgs(f"{MODEL}/images.bin")
    xyz, tracks = read_pts(f"{MODEL}/points3D.bin")
    idx = np.load(f"{HERE}/sample_idx.npy")
    print("sample:", len(idx), "points; images:", len(imgs))
    json.dump({"n": len(idx)}, open(f"{HERE}/holdout_meta.json","w"))

if __name__ == "__main__":
    main()
