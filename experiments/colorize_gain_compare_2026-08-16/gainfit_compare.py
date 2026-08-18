#!/usr/bin/env python3
"""帧增益估计的形式对照:Brown&Lowe(标准) vs log-中位(自研形式)。

判据 = held-out 的 TVG 几何内点约束(两种拟合都没用它做过训练的那一半)。
标准形式出处:OpenCV modules/stitching/src/exposure_compensate.cpp
(GainCompensator/ChannelsCompensator,实现 Brown & Lowe 2007):
  · 每个重叠对只用 重叠均值 Ī_ij / Ī_ji 与 重叠计数 N;
  · 线性域最小二乘,数据项权重 alpha*N*I²,先验项 beta*N*(1-g)²;
  · alpha=0.01, beta=100(= 论文 σ_N=10 灰阶, σ_g=0.1);
  · 每通道独立跑一遍 = ChannelsCompensator。
⚠️ /private/tmp 会被清空,本脚本与产物一律放 progecttwo。
"""
import collections, json, math, os, sqlite3, statistics, struct
from PIL import Image

BK = ('/Users/kaidongwang/Documents/progecttwo/.device_backups/'
      'PocketWorld_matcher_b_production_20260724T132905Z/container_before/'
      'Documents_copy/captures_official/cap_1784860918349292')
MODEL = '/Users/kaidongwang/Documents/progecttwo/.fixtures_12mp/cc_model'


def read_points3d(path):
    pts = []
    with open(path, 'rb') as f:
        (n,) = struct.unpack('<Q', f.read(8))
        for _ in range(n):
            pid, x, y, z, r, g, b, err = struct.unpack('<QdddBBBd', f.read(8+24+3+8))
            (tl,) = struct.unpack('<Q', f.read(8))
            track = [struct.unpack('<II', f.read(8)) for _ in range(tl)]
            pts.append((x, y, z, track))
    return pts


def srgb_to_linear(v):
    """sRGB 编码值(0-255)→ 线性光(0-1)。曝光只有在线性光里才是纯乘法;
    AliceVision 官方实现(PR #656)明写"exposure correction must be applied in
    Linear colorspace",我们此前两版都直接在 sRGB 值上拟合 = 色彩空间用错。"""
    c = v / 255.0
    lin = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return lin * 255.0  # 缩回 0-255 量级:Brown&Lowe 的 α/β 是按灰阶标定的
                        # (σ_N=10 灰阶),不缩放会让数据项小 4 个数量级、
                        # 先验把增益全钉在 1.0(第一版就是这么废掉的)。


def bilinear(px, W, H, x, y):
    fx, fy = x - 0.5, y - 0.5
    x0, y0 = math.floor(fx), math.floor(fy)
    x1, y1 = x0 + 1, y0 + 1
    if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H:
        return None
    dx, dy = fx - x0, fy - y0
    w00, w01, w10, w11 = (1-dx)*(1-dy), dx*(1-dy), (1-dx)*dy, dx*dy
    a, b, c, d = px[x0, y0], px[x1, y0], px[x0, y1], px[x1, y1]
    return [a[k]*w00 + b[k]*w01 + c[k]*w10 + d[k]*w11 for k in range(3)]


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
    for pi, (x, y, z, track) in enumerate(pts):
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
            if idx >= len(kp):
                continue
            c = bilinear(px, W, H, kp[idx][0]*sx, kp[idx][1]*sy)
            if c:
                samples[pi].append((iid, c[0], c[1], c[2]))
        im.close()
    print(f'点 {len(pts)},样本 {sum(len(s) for s in samples)}')

    frames = sorted(kps)
    idxf = {f: i for i, f in enumerate(frames)}
    NF = len(frames)

    # 帧对统计:共视点上的均值(标准口径)+ log 比中位(自研口径)
    st = collections.defaultdict(lambda: [[0.0]*3, [0.0]*3, 0, [[], [], []]])
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
                    e[0][c] += va[1+c]
                    e[1][c] += vb[1+c]
                    if va[1+c] > 12 and vb[1+c] > 12:
                        e[3][c].append(math.log(va[1+c]/vb[1+c]))
                e[2] += 1
    P = []
    for k, v in st.items():
        if v[2] < 30:
            continue
        P.append((k[0], k[1],
                  [v[0][c]/v[2] for c in range(3)],
                  [v[1][c]/v[2] for c in range(3)],
                  v[2],
                  [statistics.median(v[3][c]) if len(v[3][c]) >= 30 else None for c in range(3)]))
    print(f'共视帧对 {len(P)}')

    def brown_lowe(ch, alpha=0.01, beta=100.0, iters=500):
        g = [1.0]*NF
        for _ in range(iters):
            num = [0.0]*NF
            den = [0.0]*NF
            for i, j, Ii, Ij, N, _ in P:
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

    def logfit(ch, iters=400):
        g = [0.0]*NF
        E = [(i, j, lr[ch], N) for i, j, _a, _b, N, lr in P if lr[ch] is not None]
        for _ in range(iters):
            num = [0.0]*NF
            den = [0.0]*NF
            for i, j, lr, w in E:
                a, b = idxf[i], idxf[j]
                num[a] += w*(lr + g[b]); den[a] += w
                num[b] += w*(g[a] - lr); den[b] += w
            ng = [(num[k]/den[k] if den[k] else g[k]) for k in range(NF)]
            m = statistics.median(ng)
            g = [x - m for x in ng]
        return [math.exp(x) for x in g]

    # —— 线性光版:先把帧对统计换成线性光,再跑同样两种拟合 ——
    st_lin = collections.defaultdict(lambda: [[0.0]*3, [0.0]*3, 0, [[], [], []]])
    for s_ in samples:
        byf = {}
        for v in s_:
            byf.setdefault(v[0], v)
        fl_ = sorted(byf)
        for a in range(len(fl_)):
            for b in range(a+1, len(fl_)):
                i, j = fl_[a], fl_[b]
                va, vb = byf[i], byf[j]
                e = st_lin[(i, j)]
                for c in range(3):
                    la, lb = srgb_to_linear(va[1+c]), srgb_to_linear(vb[1+c])
                    e[0][c] += la; e[1][c] += lb
                    # 下限 = 编码值 12 换算到线性光(≈1.1/255 量级),
                    # 否则 log 被近黑噪声主导(第一版跨度 0.309~1.705 就是这么来的)
                    if la > 1.1 and lb > 1.1:
                        e[3][c].append(math.log(la/lb))
                e[2] += 1
    P_lin = [(k[0], k[1], [v[0][c]/v[2] for c in range(3)], [v[1][c]/v[2] for c in range(3)], v[2],
              [statistics.median(v[3][c]) if len(v[3][c]) >= 30 else None for c in range(3)])
             for k, v in st_lin.items() if v[2] >= 30]

    def fit_generic(PP, ch, mode, alpha=0.01, beta=100.0, iters=400):
        if mode == 'bl':
            g = [1.0]*NF
            for _ in range(iters):
                num = [0.0]*NF; den = [0.0]*NF
                for i, j, Ii, Ij, N, _ in PP:
                    a, b = idxf[i], idxf[j]; Ia, Ib = Ii[ch], Ij[ch]
                    num[a] += alpha*N*Ia*Ib*g[b] + beta*N; den[a] += alpha*N*Ia*Ia + beta*N
                    num[b] += alpha*N*Ib*Ia*g[a] + beta*N; den[b] += alpha*N*Ib*Ib + beta*N
                for f in range(NF):
                    if den[f] > 0: g[f] = num[f]/den[f]
            return g
        g = [0.0]*NF
        E = [(i, j, lr[ch], N) for i, j, _a, _b, N, lr in PP if lr[ch] is not None]
        for _ in range(iters):
            num = [0.0]*NF; den = [0.0]*NF
            for i, j, lr, w in E:
                a, b = idxf[i], idxf[j]
                num[a] += w*(lr + g[b]); den[a] += w
                num[b] += w*(g[a] - lr); den[b] += w
            ng = [(num[k]/den[k] if den[k] else g[k]) for k in range(NF)]
            m = statistics.median(ng); g = [x - m for x in ng]
        return [math.exp(x) for x in g]

    G_lin_bl = [fit_generic(P_lin, c, 'bl') for c in range(3)]
    G_lin_log = [fit_generic(P_lin, c, 'log') for c in range(3)]

    def ev_lin_space(G):
        """在**线性光**里评:共视帧对的相对亮度差(与域无关的中立判据)。"""
        r = []
        for i, j, Ii, Ij, N, _ in P_lin:
            for c in range(3):
                a = G[c][idxf[i]]*Ii[c]; b = G[c][idxf[j]]*Ij[c]
                m = (a+b)/2.0
                if m > 1.1: r.append(abs(a-b)/m)
        r.sort(); return r[len(r)//2], r[len(r)*9//10]

    one_ = [[1.0]*NF for _ in range(3)]
    print('\n=== 线性光空间(AliceVision 口径:先解码再校正)===')
    for name, G in (('不校正', one_), ('Brown&Lowe@线性光', G_lin_bl), ('log拟合@线性光', G_lin_log)):
        m, pp = ev_lin_space(G)
        fl2 = [G[c][i] for c in range(3) for i in range(NF)]
        print(f'  {name:22s} 线性光相对差 中位={m:.4f} p90={pp:.4f}  跨度 {min(fl2):.3f}~{max(fl2):.3f}')

    G_bl = [brown_lowe(c) for c in range(3)]
    # 先验强度扫描:σ_g=0.1(标准,beta=100)→ 放松到我们实测的 ±25% 量级
    G_bl_relax = {b: [brown_lowe(c, beta=b) for c in range(3)] for b in (16.0, 4.0, 1.0, 0.0)}
    G_log = [logfit(c) for c in range(3)]
    for name, G in (('Brown&Lowe(标准)', G_bl), ('log-中位(自研)', G_log)):
        fl = [G[c][i] for c in range(3) for i in range(NF)]
        print(f'  {name:20s} 增益跨度 {min(fl):.3f} ~ {max(fl):.3f}')

    # held-out:TVG 内点约束的奇数半份
    raw = []
    for pid, rows, cols, blob in db.execute(
            'select pair_id,rows,cols,data from two_view_geometries where rows>=30'):
        i1, i2 = pid//2147483647, pid % 2147483647
        a = struct.unpack(f'<{rows*cols}I', blob)
        raw.append((i1, i2, [(a[k*cols], a[k*cols+1]) for k in range(rows)]))
    need = collections.defaultdict(set)
    for i1, i2, ms in raw:
        for p, q in ms:
            need[i1].add(p); need[i2].add(q)
    kprgb = {}
    for iid in sorted(need):
        if iid not in fed or iid not in kps:
            continue
        fn, gw, gh = fed[iid]
        im = Image.open(f'{BK}/photos_highres/{fn}').convert('RGB')
        W, H = im.size
        px = im.load()
        sx, sy = W/gw, H/gh
        kp = kps[iid]
        d = {}
        for idx in need[iid]:
            if idx < len(kp):
                u, v = int(kp[idx][0]*sx), int(kp[idx][1]*sy)
                if 0 <= u < W and 0 <= v < H:
                    d[idx] = px[u, v]
        kprgb[iid] = d
        im.close()
    B = []
    for n_, (i1, i2, ms) in enumerate(raw):
        if n_ % 2 == 0 or i1 not in kprgb or i2 not in kprgb:
            continue
        acc = [[], [], []]
        for p, q in ms:
            va, vb = kprgb[i1].get(p), kprgb[i2].get(q)
            if not va or not vb:
                continue
            for c in range(3):
                if va[c] > 12 and vb[c] > 12:
                    acc[c].append(math.log(va[c]/vb[c]))
        if all(len(acc[c]) >= 30 for c in range(3)):
            B.append((i1, i2, [statistics.median(acc[c]) for c in range(3)]))

    def ev(G):
        r = []
        for i1, i2, lr in B:
            for c in range(3):
                r.append(abs(lr[c] - (math.log(G[c][idxf[i1]]) - math.log(G[c][idxf[i2]]))))
        r.sort()
        return r[len(r)//2], r[len(r)*9//10]

    # 线性域判据(= Brown&Lowe 自己的目标口径):|g_i·Ī_ij − g_j·Ī_ji| 相对亮度
    def ev_lin(G):
        r = []
        for i, j, Ii, Ij, N, _ in P:
            for c in range(3):
                a = G[c][idxf[i]]*Ii[c]
                b = G[c][idxf[j]]*Ij[c]
                m = (a + b) / 2.0
                if m > 12:
                    r.append(abs(a - b) / m)
        r.sort()
        return r[len(r)//2], r[len(r)*9//10]

    one = [[1.0]*NF for _ in range(3)]
    print(f'\nheld-out TVG 半份({len(B)} 条边)残差:')
    for name, G in (('不校正', one), ('Brown&Lowe(标准)', G_bl), ('log-中位(自研)', G_log)):
        m, p = ev(G)
        print(f'  {name:20s} 中位={m:.4f} p90={p:.4f}')
    print('\n先验放松扫描(σ_g=1/√beta;标准 beta=100 即 σ_g=0.1):')
    for b, G in G_bl_relax.items():
        fl = [G[c][i] for c in range(3) for i in range(NF)]
        m, pp = ev(G); lm, lp = ev_lin(G)
        sg = 'inf' if b == 0 else f'{1/math.sqrt(b):.2f}'
        print(f'  beta={b:6.1f} (σ_g={sg:>4}) 跨度 {min(fl):.3f}~{max(fl):.3f}  log域={m:.4f}  线性域={lm:.4f}')
    print('\n线性域判据(Brown&Lowe 自己的口径,共视帧对上的相对亮度差):')
    for name, G in (('不校正', one), ('Brown&Lowe(标准)', G_bl), ('log-中位(自研)', G_log)):
        m, p = ev_lin(G)
        print(f'  {name:20s} 中位={m:.4f} p90={p:.4f}')


if __name__ == '__main__':
    main()
