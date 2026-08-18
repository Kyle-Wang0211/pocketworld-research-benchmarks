#!/usr/bin/env python3
"""前端天花板:匹配率 vs 视角差的衰减曲线。

要回答:97% 的点几何上被 20+ 台相机看到,却平均只有 3.3 台进轨迹 —— 是
"配对没做够"(提高 K 就能捞回来)还是"描述子在大视角差下本就失效"
(物理上限,只能换前端或缩小拍摄步长)?

做法:对**已经尝试过的帧对**(DB 里有 matches 行的),算
  · 视角差 = 两相机光心到共视点集中心的夹角(度)
  · 几何共视点数 = 两帧都能投影到像面内的点数
  · 实际匹配内点数 = two_view_geometries.rows
  · 回收率 = 内点 / 几何共视
按视角差分档看回收率。若回收率随角度陡降 ⇒ 描述子上限;若各档都高但配对数
少 ⇒ 配对没做够。
"""
import collections, math, sqlite3, struct

MODEL = '/Users/kaidongwang/Documents/progecttwo/.fixtures_12mp/cc_model'
DB = MODEL + '/session.db'


def read_cameras(path):
    cams = {}
    with open(path, 'rb') as f:
        (n,) = struct.unpack('<Q', f.read(8))
        for _ in range(n):
            cid, model_id, w, h = struct.unpack('<iiQQ', f.read(24))
            npar = {0: 3, 1: 4, 2: 4, 3: 5}.get(model_id, 4)
            par = struct.unpack(f'<{npar}d', f.read(8 * npar))
            cams[cid] = (w, h, par)
    return cams


def read_images(path):
    imgs = {}
    with open(path, 'rb') as f:
        (n,) = struct.unpack('<Q', f.read(8))
        for _ in range(n):
            iid, qw, qx, qy, qz, tx, ty, tz, cam = struct.unpack('<Idddddddi', f.read(64))
            name = b''
            while True:
                ch = f.read(1)
                if ch == b'\x00':
                    break
                name += ch
            (np2,) = struct.unpack('<Q', f.read(8))
            f.read(np2 * 24)
            imgs[iid] = ((qw, qx, qy, qz), (tx, ty, tz), cam)
    return imgs


def read_points3d(path):
    pts = []
    with open(path, 'rb') as f:
        (n,) = struct.unpack('<Q', f.read(8))
        for _ in range(n):
            _p, x, y, z, _r, _g, _b, _e = struct.unpack('<QdddBBBd', f.read(43))
            (tl,) = struct.unpack('<Q', f.read(8))
            f.read(tl * 8)
            pts.append((x, y, z))
    return pts


def qrot(q, v):
    w, x, y, z = q
    t = (2*(y*v[2] - z*v[1]), 2*(z*v[0] - x*v[2]), 2*(x*v[1] - y*v[0]))
    return (v[0] + w*t[0] + (y*t[2] - z*t[1]),
            v[1] + w*t[1] + (z*t[0] - x*t[2]),
            v[2] + w*t[2] + (x*t[1] - y*t[0]))


def cam_center(q, t):
    # C = -R^T t;R^T v 用共轭四元数旋转
    qc = (q[0], -q[1], -q[2], -q[3])
    r = qrot(qc, t)
    return (-r[0], -r[1], -r[2])


def main():
    cams = read_cameras(f'{MODEL}/cameras.bin')
    imgs = read_images(f'{MODEL}/images.bin')
    pts = read_points3d(f'{MODEL}/points3D.bin')
    print(f'影像 {len(imgs)},点 {len(pts)}')

    # 每帧可见点集(几何,含遮挡上界)+ 可见点质心
    vis = {}
    centroid = {}
    for iid, (q, t, cid) in imgs.items():
        w, h, par = cams[cid]
        fx, fy, cx, cy = par[0], par[1], par[2], par[3]
        s = set()
        sx = sy = sz = 0.0
        for pi, X in enumerate(pts):
            p = qrot(q, X)
            p = (p[0] + t[0], p[1] + t[1], p[2] + t[2])
            if p[2] <= 1e-6:
                continue
            u = fx * p[0] / p[2] + cx
            v = fy * p[1] / p[2] + cy
            if 0 <= u < w and 0 <= v < h:
                s.add(pi)
                sx += X[0]; sy += X[1]; sz += X[2]
        vis[iid] = s
        if s:
            centroid[iid] = (sx/len(s), sy/len(s), sz/len(s))
    centers = {iid: cam_center(q, t) for iid, (q, t, _c) in imgs.items()}

    db = sqlite3.connect(DB)
    tvg = {}
    for pid, rows in db.execute('select pair_id,rows from two_view_geometries'):
        tvg[pid] = rows
    attempted = set()
    for (pid,) in db.execute('select pair_id from matches'):
        attempted.add(pid)

    buckets = collections.defaultdict(lambda: [0, 0, 0])  # 角度档 → [对数, Σ共视, Σ内点]
    for pid in attempted:
        i1, i2 = pid // 2147483647, pid % 2147483647
        if i1 not in vis or i2 not in vis:
            continue
        shared = vis[i1] & vis[i2]
        if len(shared) < 50:
            continue
        c = centroid.get(i1)
        if not c:
            continue
        a = centers[i1]; b = centers[i2]
        va = (a[0]-c[0], a[1]-c[1], a[2]-c[2])
        vb = (b[0]-c[0], b[1]-c[1], b[2]-c[2])
        na = math.sqrt(sum(x*x for x in va)) or 1e-9
        nb = math.sqrt(sum(x*x for x in vb)) or 1e-9
        cosang = sum(va[k]*vb[k] for k in range(3))/(na*nb)
        ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
        k = min(int(ang // 10), 9)
        e = buckets[k]
        e[0] += 1
        e[1] += len(shared)
        e[2] += tvg.get(pid, 0)

    print(f"\n{'视角差':>10}{'配对数':>8}{'平均几何共视':>14}{'平均TVG内点':>13}{'回收率':>9}")
    for k in range(10):
        if k not in buckets:
            continue
        n, sh, inl = buckets[k]
        print(f'{k*10:>4}-{k*10+10:<5}{n:>8}{sh/n:>14.0f}{inl/n:>13.0f}{inl/sh*100:>8.1f}%')


if __name__ == '__main__':
    main()
