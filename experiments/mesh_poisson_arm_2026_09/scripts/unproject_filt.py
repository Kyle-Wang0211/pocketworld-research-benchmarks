#!/usr/bin/env python3
"""把 AliceVision DepthMapFilter 的输出反投影成带色点云(官方 SfM 帧)。
不猜坐标约定: 直接用 AliceVision 自己写进 EXR 头的 iCamArr / CArr
(与 mvsUtils::get3DPointForPixelAndDepthFromRC 同式: dir = normalize(iCamArr @ [x,y,1]); X = C + depth*dir),
深度是欧氏射线距离、无效 <= 0, 见 /root/av_ep0/write_av_depthmaps_ds.py。
  unproject_filt.py <filt_dir> <prep_dir> <sfm> <out.ply> [target_points] [--selftest]"""
import sys, os, json, glob, time, numpy as np, OpenEXR
from plyfile import PlyData, PlyElement
FILT, PREP, SFM, OUT = sys.argv[1:5]
TARGET = int(sys.argv[5]) if len(sys.argv) > 5 and not sys.argv[5].startswith('--') else 0
SELFTEST = '--selftest' in sys.argv
def load(p, ch='Y'):
    with OpenEXR.File(p) as f:
        hdr = dict(f.header()); c = f.channels()
        if ch == 'RGB':
            if 'RGBA' in c:   img = np.asarray(c['RGBA'].pixels, dtype=np.float32)[..., :3]
            elif 'RGB' in c:  img = np.asarray(c['RGB'].pixels, dtype=np.float32)
            else:             img = np.stack([np.asarray(c[k].pixels, dtype=np.float32) for k in ('R','G','B')], -1)
        else:
            img = np.asarray(c[ch].pixels, dtype=np.float32)
        return np.array(img), {k: (np.array(v) if isinstance(v, np.ndarray) else v) for k, v in hdr.items()}
def unproject(dp):
    Z, h = load(dp)
    iC = np.asarray(h['AliceVision:iCamArr'], dtype=np.float64).reshape(3, 3)
    C = np.asarray(h['AliceVision:CArr'], dtype=np.float64).reshape(3)
    ds = int(h['AliceVision:downscale'])
    hh, ww = Z.shape
    ok = Z > 0
    if not ok.any(): return None, None, None, ds
    u, v = np.meshgrid(np.arange(ww, dtype=np.float64), np.arange(hh, dtype=np.float64))
    uu, vv = u[ok], v[ok]
    d = np.stack([uu, vv, np.ones_like(uu)], 1) @ iC.T
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    X = C + d * Z[ok][:, None].astype(np.float64)
    return X, (uu, vv), ok, ds
maps = sorted(glob.glob(f'{FILT}/*_depthMap.exr'))
if SELFTEST:
    ref = np.array([-0.112, 2.285, -0.916])
    acc = []
    for p in maps[:5]:
        X, _, _, ds = unproject(p)
        if X is not None: acc.append(X)
    A = np.concatenate(acc)
    print(f'  5 视图 {len(A):,} 点  中位 {np.round(np.median(A,0),3).tolist()}  离 A_filt 网格中位 {np.linalg.norm(np.median(A,0)-ref):.3f} m  downscale={ds}')
    print(f'  bbox {np.round(A.min(0),2).tolist()} .. {np.round(A.max(0),2).tolist()}   (A_filt ext 约 [1.96,3.44,1.36])')
    raise SystemExit
t0 = time.time(); P = []; CO = []
for k, dp in enumerate(maps):
    vid = os.path.basename(dp).split('_')[0]
    X, uv, ok, ds = unproject(dp)
    if X is None: continue
    im, _ = load(f'{PREP}/{vid}.exr', 'RGB')
    yy = np.clip((uv[1]*ds).astype(np.int32), 0, im.shape[0]-1); xx = np.clip((uv[0]*ds).astype(np.int32), 0, im.shape[1]-1)
    c = np.clip(im[yy, xx], 0, None)
    c = np.where(c <= 0.0031308, c*12.92, 1.055*c**(1/2.4) - 0.055)
    P.append(X.astype(np.float32)); CO.append((np.clip(c,0,1)*255+0.5).astype(np.uint8))
    if (k+1) % 30 == 0: print(f'  {k+1}/{len(maps)} 累计 {sum(len(x) for x in P):,} 点 ({time.time()-t0:.0f}s)', flush=True)
P = np.concatenate(P); CO = np.concatenate(CO)
print(f'反投影完成 {len(P):,} 点 ({time.time()-t0:.0f}s)')
if TARGET and len(P) > TARGET:
    idx = np.random.default_rng(0).choice(len(P), TARGET, replace=False)
    P, CO = P[idx], CO[idx]; print(f'均匀抽样到 {len(P):,} 点')
print(f'中位 {np.round(np.median(P,0),3).tolist()}  bbox {np.round(P.min(0),2).tolist()} .. {np.round(P.max(0),2).tolist()}')
el = np.empty(len(P), dtype=[('x','f4'),('y','f4'),('z','f4'),('red','u1'),('green','u1'),('blue','u1')])
el['x'],el['y'],el['z']=P[:,0],P[:,1],P[:,2]; el['red'],el['green'],el['blue']=CO[:,0],CO[:,1],CO[:,2]
PlyData([PlyElement.describe(el,'vertex')], text=False).write(OUT)
print(f'写出 {OUT} ({time.time()-t0:.0f}s)')
