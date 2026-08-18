#!/usr/bin/env python3
"""观测数诊断:轨迹里的观测数 vs 几何上能看到的相机数,以及相邻帧重叠率。

要回答的问题:61% 的点只有 2 个观测,是"本来就只有 2 台相机看得到"(拍摄
覆盖不足 ⇒ 抄 RS 的 70% 重叠引导),还是"其实 8 台看得到但只有 2 台进了
轨迹"(匹配/轨迹构建在丢观测 ⇒ 改重建)。这两种治法相反,不能猜。

⚠️ 几何可见 = 在相机前方且落在像面内,**不考虑遮挡**,所以是上界。
"""
import collections, math, struct

MODEL = '/Users/kaidongwang/Documents/progecttwo/.fixtures_12mp/cc_model'


def read_cameras(path):
    cams = {}
    with open(path, 'rb') as f:
        (n,) = struct.unpack('<Q', f.read(8))
        for _ in range(n):
            cid, model_id, w, h = struct.unpack('<iiQQ', f.read(24))
            # PINHOLE(model_id=1)= fx, fy, cx, cy
            nparams = {0: 3, 1: 4, 2: 4, 3: 5}.get(model_id, 4)
            params = struct.unpack(f'<{nparams}d', f.read(8 * nparams))
            cams[cid] = (model_id, w, h, params)
    return cams


def read_images(path):
    imgs = []
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
            f.read(np2 * 24)  # 跳过 points2D(x,y,point3D_id)
            imgs.append((iid, (qw, qx, qy, qz), (tx, ty, tz), cam))
    return imgs


def read_points3d(path):
    pts = []
    with open(path, 'rb') as f:
        (n,) = struct.unpack('<Q', f.read(8))
        for _ in range(n):
            _pid, x, y, z, _r, _g, _b, _e = struct.unpack('<QdddBBBd', f.read(43))
            (tl,) = struct.unpack('<Q', f.read(8))
            track = [struct.unpack('<II', f.read(8)) for _ in range(tl)]
            pts.append(((x, y, z), track))
    return pts


def qrot(q, v):
    w, x, y, z = q
    # R·v(单位四元数)
    t = (2*(y*v[2] - z*v[1]), 2*(z*v[0] - x*v[2]), 2*(x*v[1] - y*v[0]))
    return (v[0] + w*t[0] + (y*t[2] - z*t[1]),
            v[1] + w*t[1] + (z*t[0] - x*t[2]),
            v[2] + w*t[2] + (x*t[1] - y*t[0]))


def main():
    cams = read_cameras(f'{MODEL}/cameras.bin')
    imgs = read_images(f'{MODEL}/images.bin')
    pts = read_points3d(f'{MODEL}/points3D.bin')
    print(f'相机 {len(cams)} 台,影像 {len(imgs)},点 {len(pts)}')

    track_len = collections.Counter()
    vis_len = collections.Counter()
    pairs = []
    ratios = []
    for (X, track) in pts:
        tl = len(track)
        vis = 0
        for (iid, q, t, cid) in imgs:
            p = qrot(q, X)
            p = (p[0] + t[0], p[1] + t[1], p[2] + t[2])
            if p[2] <= 1e-6:
                continue
            _m, w, h, par = cams[cid]
            fx, fy, cx, cy = par[0], par[1], par[2], par[3]
            u = fx * p[0] / p[2] + cx
            v = fy * p[1] / p[2] + cy
            if 0 <= u < w and 0 <= v < h:
                vis += 1
        track_len[min(tl, 20)] += 1
        vis_len[min(vis, 20)] += 1
        if vis > 0:
            ratios.append(tl / vis)
        pairs.append((tl, vis))

    n = len(pts)
    at = sum(tl for tl, _ in pairs) / n
    av = sum(v for _, v in pairs) / n
    ratios.sort()
    print(f'\n每点平均:轨迹观测 {at:.2f} 台  vs  几何可见 {av:.2f} 台(不含遮挡,是上界)')
    print(f'轨迹/可见 比值:中位 {ratios[len(ratios)//2]:.3f}  p10 {ratios[len(ratios)//10]:.3f}'
          f'  p90 {ratios[len(ratios)*9//10]:.3f}')
    print('\n分布(桶=观测/可见台数,20+ 归并):')
    print(f"{'台数':>4}{'轨迹点数':>10}{'几何可见点数':>14}")
    for k in range(2, 13):
        print(f'{k:>4}{track_len.get(k,0):>10}{vis_len.get(k,0):>14}')
    print(f"{'20+':>4}{track_len.get(20,0):>10}{vis_len.get(20,0):>14}")

    # 相邻帧重叠率(RS 建议 70%)
    seen = collections.defaultdict(set)
    for pi, (_X, track) in enumerate(pts):
        for (iid, _idx) in track:
            seen[iid].add(pi)
    ids = sorted(seen)
    ov = []
    for a, b in zip(ids, ids[1:]):
        sa, sb = seen[a], seen[b]
        if sa and sb:
            ov.append(len(sa & sb) / min(len(sa), len(sb)))
    ov.sort()
    if ov:
        print(f'\n相邻帧共视点重叠率:中位 {ov[len(ov)//2]*100:.1f}%  '
              f'p10 {ov[len(ov)//10]*100:.1f}%  p90 {ov[len(ov)*9//10]*100:.1f}%'
              f'   (RS 建议 ~70%)')


if __name__ == '__main__':
    main()
