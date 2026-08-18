#!/usr/bin/env python3
"""渲染 E 臂:线性光 + Brown&Lowe(业内标准形态),与 A(现状)、B(sRGB log 拟合)并排。

标准形态三步(AliceVision PR #656 + OpenCV GainCompensator):
  ① sRGB 解码 → 线性光;② 线性光里估每帧每通道增益(α=0.01/β=100,按 0-255
  量级标定);③ 线性光里乘增益 → 重新编码回 sRGB → 再做代表色选择。
"""
import collections, json, math, os, sqlite3, statistics, struct
from PIL import Image

BK = ('/Users/kaidongwang/Documents/progecttwo/.device_backups/'
      'PocketWorld_matcher_b_production_20260724T132905Z/container_before/'
      'Documents_copy/captures_official/cap_1784860918349292')
MODEL = '/Users/kaidongwang/Documents/progecttwo/.fixtures_12mp/cc_model'
OUT = '/Users/kaidongwang/Documents/progecttwo/_artifacts/colorize_cc_compare'


def s2l(v):
    c = v / 255.0
    lin = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return lin * 255.0


def l2s(v):
    c = max(0.0, v) / 255.0
    e = c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1/2.4)) - 0.055
    return e * 255.0


def read_points3d(path):
    pts = []
    with open(path, 'rb') as f:
        (n,) = struct.unpack('<Q', f.read(8))
        for _ in range(n):
            _pid, x, y, z, _r, _g, _b, _e = struct.unpack('<QdddBBBd', f.read(43))
            (tl,) = struct.unpack('<Q', f.read(8))
            track = [struct.unpack('<II', f.read(8)) for _ in range(tl)]
            pts.append((x, y, z, track))
    return pts


def bilinear(px, W, H, x, y):
    fx, fy = x - 0.5, y - 0.5
    x0, y0 = math.floor(fx), math.floor(fy)
    x1, y1 = x0 + 1, y0 + 1
    if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H:
        return None
    dx, dy = fx - x0, fy - y0
    w = ((1-dx)*(1-dy), dx*(1-dy), (1-dx)*dy, dx*dy)
    a, b, c, d = px[x0, y0], px[x1, y0], px[x0, y1], px[x1, y1]
    return [a[k]*w[0] + b[k]*w[1] + c[k]*w[2] + d[k]*w[3] for k in range(3)]


def main():
    pts = read_points3d(f'{MODEL}/points3D.bin')
    db = sqlite3.connect(f'{BK}/official_sfm_live.db')
    kps = {}
    for iid, rows, cols, blob in db.execute('select image_id,rows,cols,data from keypoints'):
        a = struct.unpack(f'<{rows*cols}f', blob)
        kps[iid] = [(a[i*cols], a[i*cols+1]) for i in range(rows)]
    fed = {}
    for l in open(f'{BK}/official_sfm_fed_frames.jsonl'):
        d = json.loads(l)
        fed[d['frameId'] + 1] = (os.path.basename(d['jpegPath']), d['grayW'], d['grayH'])

    byframe = collections.defaultdict(list)
    for pi, (_x, _y, _z, track) in enumerate(pts):
        for (tid, idx) in track:
            byframe[tid].append((pi, idx))
    samples = [[] for _ in pts]
    for iid in sorted(byframe):
        if iid not in fed or iid not in kps:
            continue
        fn, gw, gh = fed[iid]
        im = Image.open(f'{BK}/photos_highres/{fn}').convert('RGB')
        W, H = im.size
        px = im.load()
        sx, sy = W/gw, H/gh
        kp = kps[iid]
        for (pi, idx) in byframe[iid]:
            if idx < len(kp):
                c = bilinear(px, W, H, kp[idx][0]*sx, kp[idx][1]*sy)
                if c:
                    samples[pi].append((iid, c[0], c[1], c[2]))
        im.close()
    frames = sorted(kps)
    idxf = {f: i for i, f in enumerate(frames)}
    NF = len(frames)
    print(f'点 {len(pts)},样本 {sum(len(s) for s in samples)},帧 {NF}')

    # 帧对统计(线性光均值)
    st = collections.defaultdict(lambda: [[0.0]*3, [0.0]*3, 0])
    for s in samples:
        byf = {}
        for v in s:
            byf.setdefault(v[0], v)
        fl = sorted(byf)
        for a in range(len(fl)):
            for b in range(a+1, len(fl)):
                i, j = fl[a], fl[b]
                va, vb = byf[i], byf[j]
                e = st[(i, j)]
                for c in range(3):
                    e[0][c] += s2l(va[1+c])
                    e[1][c] += s2l(vb[1+c])
                e[2] += 1
    P = [(k[0], k[1], [v[0][c]/v[2] for c in range(3)], [v[1][c]/v[2] for c in range(3)], v[2])
         for k, v in st.items() if v[2] >= 30]

    def brown_lowe(ch, alpha=0.01, beta=100.0, iters=500):
        g = [1.0]*NF
        for _ in range(iters):
            num = [0.0]*NF
            den = [0.0]*NF
            for i, j, Ii, Ij, N in P:
                a, b = idxf[i], idxf[j]
                Ia, Ib = Ii[ch], Ij[ch]
                num[a] += alpha*N*Ia*Ib*g[b] + beta*N
                den[a] += alpha*N*Ia*Ia + beta*N
                num[b] += alpha*N*Ib*Ia*g[a] + beta*N
                den[b] += alpha*N*Ib*Ib + beta*N
            for f in range(NF):
                if den[f] > 0:
                    g[f] = num[f]/den[f]
        return g

    G = [brown_lowe(c) for c in range(3)]
    fl = [G[c][i] for c in range(3) for i in range(NF)]
    print(f'线性光 Brown&Lowe 增益跨度 {min(fl):.3f} ~ {max(fl):.3f}')

    # 归约:线性光乘增益 → 回 sRGB → 代表色选择(规则同产品)
    cols = []
    for s in samples:
        if not s:
            cols.append((185, 185, 190))
            continue
        corr = []
        for v in s:
            gi = idxf[v[0]]
            corr.append([l2s(s2l(v[1+c]) * G[c][gi]) for c in range(3)])
        lums = [0.299*c[0] + 0.587*c[1] + 0.114*c[2] for c in corr]
        sl = sorted(lums)
        med = sl[(len(sl)-1)//2]
        best, bd = 0, float('inf')
        for k, L in enumerate(lums):
            d = abs(L - med)
            if d < bd or (d == bd and L < lums[best]):
                best, bd = k, d
        cols.append(tuple(max(0, min(255, int(round(x)))) for x in corr[best]))

    path = f'{OUT}/E_线性光BL.ply'
    with open(path, 'wb') as f:
        f.write(b'ply\nformat binary_little_endian 1.0\n')
        f.write(f'element vertex {len(pts)}\n'.encode())
        f.write(b'property float x\nproperty float y\nproperty float z\n')
        f.write(b'property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
        for (x, y, z, _), c in zip(pts, cols):
            f.write(struct.pack('<fffBBB', x, y, z, *c))
    print(f'写出 {path}')

    # 与现状比:逐点色差
    def read_rgb(p):
        f = open(p, 'rb')
        hdr = b''
        while b'end_header' not in hdr:
            hdr += f.read(1)
        f.read(1)
        n = int([l for l in hdr.decode().split('\n') if 'element vertex' in l][0].split()[-1])
        d = f.read(n*15)
        return [(d[i*15+12], d[i*15+13], d[i*15+14]) for i in range(n)]
    base = read_rgb(f'{OUT}/A_现状.ply')
    dd = sorted(max(abs(a[0]-b[0]), abs(a[1]-b[1]), abs(a[2]-b[2])) for a, b in zip(base, cols))
    n = len(dd)
    print(f'相对现状逐点色差 中位={dd[n//2]} p90={dd[n*9//10]} >16级={sum(1 for v in dd if v>16)/n*100:.1f}%')


if __name__ == '__main__':
    main()
