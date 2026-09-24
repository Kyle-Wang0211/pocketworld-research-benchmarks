# -*- coding: utf-8 -*-
"""箱上 GPU 离线渲染:两臂【全量·零裁剪·零抽稀】同机位对照。

为什么要这么做(实测,不是推断):
  箱子上行带宽实测 —— ssh 隧道 0.42/0.93 MB/s(200MB 单流 reset 过一次),
  公网口直连 0.194 MB/s,6 路并行【不叠加】仍只有 0.33 MB/s 聚合。
  两臂 bins 合计 3.73 GB ⇒ 不管是浏览器现拉还是下载到本地,都要 2.7 小时以上。
  ⇒ 搬像素不搬点。渲染发生在箱上,212,755,389 个点【一个不少】全部参与光栅化。

相机数学:逐字转写自我们自己的 /root/build_page_cli.py 模板
  lookAt / persp / mul —— 按 JS 的【扁平 16 元素】语义原样实现, 不做任何「等价化简」,
  以保证渲出来的视角与用户一直在页面里看的那套【同一套】。
  眼位/fov/近远平面/up 也逐字照抄 (build_page_cli.py:136-141):
      ce  = [tx+dist*cos(el)*sin(az), ty+dist*sin(el), tz+dist*cos(el)*cos(az)]
      mvp = persp(1.0, w/h, radius*0.005, radius*40) x lookAt(ce, [tx,ty,tz], [0,1,0])

唯一新增的是【深度测试】(WebGL 里由固定功能管线做, 离线要自己做):
  标准 packed-key 技巧 —— key = (深度量化成 uint32) << 32 | 点下标, 对每个像素取 amin,
  一次 scatter_reduce 同时拿到「最近的那个点」和「它是谁」。没有自研算法。

🔴 我自己定的只有三项, 都标出来: 渲染分辨率、点大小(2x2 splat, 对应页面 PS=1.3 x dp=2)、
   轨迹(两段整圈, el=0.35 = 页面默认 / el=0.05 = 掠射, 掠射角才看得见分层)。
"""
import os, sys, math, json
import numpy as np, torch

DEV = "cuda"

# ---- 逐字转写自 build_page_cli.py 的三个扁平矩阵函数 ----
def sub(a, b): return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]
def crs(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def nrm(a):
    l = math.hypot(*a) or 1.0
    return [a[0]/l, a[1]/l, a[2]/l]
def dot3(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def lookAt(e, c, u):
    f = nrm(sub(c, e)); s = nrm(crs(f, u)); v = crs(s, f)
    return [s[0], v[0], -f[0], 0, s[1], v[1], -f[1], 0, s[2], v[2], -f[2], 0,
            -dot3(s, e), -dot3(v, e), dot3(f, e), 1]

def persp(fy, a, zn, zf):
    t = 1.0/math.tan(fy/2)
    return [t/a, 0, 0, 0, 0, t, 0, 0, 0, 0, (zf+zn)/(zn-zf), -1, 0, 0, 2*zf*zn/(zn-zf), 0]

def mul(A, B):
    O = [0.0]*16
    for r in range(4):
        for c in range(4):
            for k in range(4):
                O[c*4+r] += A[k*4+r]*B[c*4+k]
    return O

def mvp_matrix(cam, V, w, h):
    ce = [cam["tx"]+cam["dist"]*math.cos(cam["el"])*math.sin(cam["az"]),
          cam["ty"]+cam["dist"]*math.sin(cam["el"]),
          cam["tz"]+cam["dist"]*math.cos(cam["el"])*math.cos(cam["az"])]
    return mul(persp(1.0, w/h, V["radius"]*0.005, V["radius"]*40),
               lookAt(ce, [cam["tx"], cam["ty"], cam["tz"]], [0, 1, 0]))

# JS 的 gl_Position = mvp * vec4(p,1) 用列主序 mat4 ⇒ clip[r] = sum_c M[r][c]*p[c],
# 而扁平数组 flat[c*4+r] = M[r][c]。把 flat 按【行主序】reshape 成 A 时 A[c,r]=M[r][c] = A = M^T,
# 于是行向量写法 clip_row = p_row @ A —— 不需要任何转置。
def flat_to_A(flat):
    return torch.tensor(flat, dtype=torch.float32, device=DEV).reshape(4, 4)

CHUNK = 24_000_000
SPLAT = 2                      # 🔴 我定的: 2x2, 对应页面 PS=1.3 x devicePixelRatio 2

class Arm:
    def __init__(self, tag, d):
        p = os.path.join(d, tag + ".pos"); c = os.path.join(d, tag + ".col")
        self.n = os.path.getsize(p)//12
        assert os.path.getsize(c) == self.n*3, tag + " 颜色字节数与位置不匹配"
        self.tag = tag
        self.pos = torch.from_numpy(np.fromfile(p, dtype="<f4").reshape(-1, 3)).to(DEV)
        self.col = torch.from_numpy(np.fromfile(c, dtype=np.uint8).reshape(-1, 3)).to(DEV)
        print("  %-12s %s 点  显存 %.2f GB" % (tag, format(self.n, ","),
              (self.pos.numel()*4+self.col.numel())/1e9), flush=True)

    def render(self, flat, W, H):
        A = flat_to_A(flat)
        INIT = torch.iinfo(torch.int64).max
        buf = torch.full((H*W,), INIT, dtype=torch.int64, device=DEV)
        for off in range(0, self.n, CHUNK):
            p = self.pos[off:off+CHUNK]
            m = p.shape[0]
            clip = p @ A[:3] + A[3]                      # (m,4) 行向量 x A
            w = clip[:, 3]
            ok = w > 1e-6
            inv = torch.where(ok, 1.0/w, torch.ones_like(w))
            ndc = clip[:, :3]*inv[:, None]
            x = ((ndc[:, 0]*0.5+0.5)*W)
            y = ((1.0-(ndc[:, 1]*0.5+0.5))*H)
            ok &= (ndc[:, 2] > -1) & (ndc[:, 2] < 1)
            zq = ((ndc[:, 2]*0.5+0.5).clamp(0, 1)*2147483647.0).to(torch.int64)
            gidx = torch.arange(off, off+m, device=DEV, dtype=torch.int64)
            key = (zq << 32) | gidx
            for dy in range(SPLAT):
                for dx in range(SPLAT):
                    xi = (x+dx).to(torch.int64); yi = (y+dy).to(torch.int64)
                    v = ok & (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
                    if not bool(v.any()):
                        continue
                    buf.scatter_reduce_(0, (yi[v]*W+xi[v]), key[v], reduce="amin")
            del clip, ndc, x, y, zq, gidx, key
        hit = buf != INIT
        img = torch.zeros((H*W, 3), dtype=torch.uint8, device=DEV)
        img[hit] = self.col[(buf[hit] & 0xFFFFFFFF)]
        return img.reshape(H, W, 3).cpu().numpy(), int(hit.sum())


# ---------------------------------------------------------------- 驱动
from PIL import Image, ImageDraw, ImageFont

def label(im, text, sub):
    d = ImageDraw.Draw(im)
    try:
        f1 = ImageFont.load_default(size=30); f2 = ImageFont.load_default(size=21)
    except TypeError:
        f1 = f2 = ImageFont.load_default()
    d.text((14, 10), text, fill=(255, 255, 255), font=f1,
           stroke_width=3, stroke_fill=(0, 0, 0))
    d.text((14, 48), sub, fill=(185, 185, 185), font=f2,
           stroke_width=3, stroke_fill=(0, 0, 0))
    return im


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["stills", "video"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--w", type=int, default=1400)
    ap.add_argument("--h", type=int, default=1050)
    ap.add_argument("--frames", type=int, default=120)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    V0 = json.load(open("/root/bins_full/meta.json"))["full_ep0"]   # 相机基准 = 用户一直在看的那臂
    V = {"radius": V0["radius"]}
    base = {"tx": V0["med"][0], "ty": V0["med"][1], "tz": V0["med"][2],
            "dist": V0["radius"]*2.4}
    print("相机基准 full_ep0: med=%s radius=%.3f dist=%.3f"
          % ([round(x, 3) for x in V0["med"]], V0["radius"], base["dist"]), flush=True)

    print("载入两臂(全量):", flush=True)
    arms = [("A  768 x 576   (current)",   Arm("full_ep0",  "/root/bins_full")),
            ("B  4032 x 3008  (native 12MP)", Arm("ep0_12mp",  "/root/bins_12mp"))]

    def shoot(az, el, idx):
        cam = dict(base, az=az, el=el)
        flat = mvp_matrix(cam, V, a.w, a.h)
        tiles = []
        for name, arm in arms:
            rgb, hit = arm.render(flat, a.w, a.h)
            im = Image.fromarray(rgb)
            tiles.append(label(im, name, "%s pts  |  %.1f%% of pixels covered"
                               % (format(arm.n, ","), 100.0*hit/(a.w*a.h))))
        canvas = Image.new("RGB", (a.w*2+4, a.h), (34, 34, 34))
        canvas.paste(tiles[0], (0, 0)); canvas.paste(tiles[1], (a.w+4, 0))
        p = os.path.join(a.out, "f%05d.png" % idx)
        canvas.save(p, compress_level=3)
        return p

    if a.mode == "stills":
        for i, (az, el) in enumerate([(0.6, 0.35), (2.2, 0.05), (3.9, 0.35), (5.2, 0.05)]):
            import time; t = time.time()
            p = shoot(az, el, i)
            print("  %s  az=%.2f el=%.2f  %.1fs" % (p, az, el, time.time()-t), flush=True)
    else:
        import time
        n = a.frames; t0 = time.time()
        for i in range(n):
            u = i/n
            if i < n//2:
                az, el = 0.6 + 2*math.pi*(i/(n//2)), 0.35
            else:
                az, el = 0.6 + 2*math.pi*((i-n//2)/(n-n//2)), 0.05
            shoot(az, el, i)
            if i % 10 == 0:
                el_s = time.time()-t0
                print("  %3d/%d  已 %.0fs  预计总 %.0fs" % (i, n, el_s, el_s/max(i, 1)*n), flush=True)
        print("渲染完成 %.0fs" % (time.time()-t0), flush=True)


if __name__ == "__main__":
    main()
