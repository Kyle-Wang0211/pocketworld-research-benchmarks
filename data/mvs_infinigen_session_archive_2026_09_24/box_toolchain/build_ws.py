#!/usr/bin/env python3
"""把 AliceVision 的 filt 深度图 + 官方 SfM 转成 COLMAP 稠密工作区(AFSR 探针用)。
格式来源(逐字照抄,不猜):
  fused.ply       : colmap/util/ply.cc ReadPly()  binary_little_endian, property float x/y/z (+ uchar red/green/blue)
  fused.ply.vis   : colmap/mvs/fusion.cc:561 WritePointsVisibility()
                    uint64 num_points; per point: uint32 count, count x uint32 image_idx
                    image_idx = RegImageIds() 顺序里的 0 基序号
                    (colmap/mvs/advancing_front_meshing.cc:306-323 注释 + ReadCameraPositions)
  sparse/         : 只有 image.ProjectionCenter() 被 AFSR 用到(advancing_front_meshing.cc:320)
                    => 旋转写单位四元数, 平移写 -C, ProjectionCenter = -R^T t = C 精确成立
                    (colmap/scene/image.cc:119 -> geometry/rigid3.h:110 TgtOriginInSrc)
  反投影         : 逐字照抄 /root/unproject_filt.py (EXR 头 iCamArr/CArr, 深度=欧氏射线距离)
用法: build_ws.py <target_points> <outdir>
"""
import sys, os, json, glob, struct, time, numpy as np, OpenEXR

TARGET = int(sys.argv[1]); OUT = sys.argv[2]
FILT = '/root/av_ep0_off/filt'; SFM = '/root/av_ep0_off/scene_dense.sfm'
os.makedirs(OUT + '/sparse', exist_ok=True)

def load_depth(p):
    with OpenEXR.File(p) as f:
        h = dict(f.header())
        Z = np.array(np.asarray(f.channels()['Y'].pixels, dtype=np.float32))
    return Z, h

def unproject(Z, h):
    iC = np.asarray(h['AliceVision:iCamArr'], dtype=np.float64).reshape(3, 3)
    C  = np.asarray(h['AliceVision:CArr'],   dtype=np.float64).reshape(3)
    hh, ww = Z.shape
    ok = Z > 0
    if not ok.any(): return None, C
    u, v = np.meshgrid(np.arange(ww, dtype=np.float64), np.arange(hh, dtype=np.float64))
    uu, vv = u[ok], v[ok]
    d = np.stack([uu, vv, np.ones_like(uu)], 1) @ iC.T
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    X = C + d * Z[ok][:, None].astype(np.float64)
    return X, C

maps = sorted(glob.glob(f'{FILT}/*_depthMap.exr'))
print(f'{len(maps)} depth maps', flush=True)

# pass 1: valid counts (for a global proportional keep-fraction)
counts = []
for p in maps:
    Z, _ = load_depth(p); counts.append(int((Z > 0).sum()))
counts = np.array(counts); total = counts.sum()
frac = 1.0 if TARGET <= 0 or TARGET >= total else TARGET / total
print(f'valid total {total:,}  keep frac {frac:.6f}  -> ~{int(total*frac):,}', flush=True)

t0 = time.time(); Ps = []; Is = []; centers = []
for k, p in enumerate(maps):
    Z, h = load_depth(p)
    X, C = unproject(Z, h)
    centers.append(C)
    if X is None: continue
    if frac < 1.0:
        rng = np.random.default_rng(1000 + k)
        m = rng.random(len(X)) < frac
        X = X[m]
    Ps.append(X.astype(np.float32))
    Is.append(np.full(len(X), k, dtype=np.uint32))
    if (k + 1) % 30 == 0:
        print(f'  {k+1}/{len(maps)}  {sum(len(x) for x in Ps):,} pts ({time.time()-t0:.0f}s)', flush=True)
P = np.concatenate(Ps); IDX = np.concatenate(Is); del Ps, Is
N = len(P)
print(f'points {N:,}  bbox {P.min(0).round(3).tolist()} .. {P.max(0).round(3).tolist()}', flush=True)

# --- fused.ply (binary_little_endian, x y z + gray rgb) ---
rec = np.empty(N, dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('red','u1'),('green','u1'),('blue','u1')])
rec['x'], rec['y'], rec['z'] = P[:,0], P[:,1], P[:,2]
rec['red'] = rec['green'] = rec['blue'] = 128
with open(f'{OUT}/fused.ply', 'wb') as f:
    f.write(b'ply\nformat binary_little_endian 1.0\nelement vertex %d\n' % N)
    f.write(b'property float x\nproperty float y\nproperty float z\n')
    f.write(b'property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
    rec.tofile(f)

# --- fused.ply.vis (one image per point = the depth map it came from) ---
with open(f'{OUT}/fused.ply.vis', 'wb') as f:
    f.write(struct.pack('<Q', N))
    blob = np.empty(N * 2, dtype='<u4')
    blob[0::2] = 1
    blob[1::2] = IDX
    blob.tofile(f)

# --- sparse/ ---
d = json.load(open(SFM)); I = d['intrinsics'][0]
W = int(I['width']); H = int(I['height'])
fpx = float(I['focalLength']) / float(I['sensorWidth']) * W
pp = [float(x) for x in I['principalPoint']]
with open(f'{OUT}/sparse/cameras.txt', 'w') as f:
    f.write('# CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n')
    f.write(f'1 SIMPLE_PINHOLE {W} {H} {fpx:.8f} {W/2+pp[0]:.8f} {H/2+pp[1]:.8f}\n')
with open(f'{OUT}/sparse/images.txt', 'w') as f:
    f.write('# IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n')
    for k, (p, C) in enumerate(zip(maps, centers)):
        name = os.path.basename(p).replace('_depthMap.exr', '.jpg')
        f.write(f'{k+1} 1 0 0 0 {-C[0]:.17g} {-C[1]:.17g} {-C[2]:.17g} 1 {name}\n\n')
with open(f'{OUT}/sparse/points3D.txt', 'w') as f:
    f.write('# POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]\n')
np.save(f'{OUT}/centers.npy', np.array(centers))
np.save(f'{OUT}/imgidx.npy', IDX)
print(f'wrote {OUT}  ({time.time()-t0:.0f}s)  ply={os.path.getsize(OUT+"/fused.ply"):,}B vis={os.path.getsize(OUT+"/fused.ply.vis"):,}B', flush=True)
