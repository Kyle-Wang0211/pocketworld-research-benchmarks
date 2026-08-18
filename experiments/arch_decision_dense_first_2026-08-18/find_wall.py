import numpy as np, glob, json
rng = np.random.default_rng(20260818)

DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
def load(p, stride=1):
    with open(p,"rb") as f:
        hdr=b""
        while True:
            l=f.readline(); hdr+=l
            if l.strip()==b"end_header": break
        n=int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1])
        off=len(hdr)
    m=np.memmap(p, dtype=DT, mode="r", offset=off, shape=(n,))
    d=np.array(m[::stride])
    return np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)

# 相机光心 (P16k gauge)
cams=[]
for f in sorted(glob.glob("/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/mvs_P16k/cams/*_cam.txt")):
    L=open(f).read().split()
    E=np.array(L[1:17],dtype=float).reshape(4,4)
    R=E[:3,:3]; t=E[:3,3]
    cams.append(-R.T@t)
cams=np.array(cams)
print("cams", cams.shape, "center", cams.mean(0).round(2))

xyz, rgb = load("/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/dense_P16k.ply", stride=20)
print("sampled", len(xyz))

def ransac_plane(pts, iters=600, tol=0.02, rng=rng):
    n=len(pts); best=(0,None)
    for _ in range(iters):
        i=rng.choice(n,3,replace=False)
        p0,p1,p2=pts[i]
        nv=np.cross(p1-p0,p2-p0); L=np.linalg.norm(nv)
        if L<1e-9: continue
        nv/=L; d=-nv@p0
        cnt=np.count_nonzero(np.abs(pts@nv+d)<tol)
        if cnt>best[0]: best=(cnt,(nv,d))
    return best

# 1) 地板 = 全云最大平面
cnt,(nfl,dfl) = ransac_plane(xyz[rng.choice(len(xyz),min(200000,len(xyz)),replace=False)])
# 让法向指向相机侧(向上)
if np.mean(cams@nfl+dfl)<0: nfl,dfl=-nfl,-dfl
print(f"floor plane inliers={cnt} n={nfl.round(3)} d={dfl:.3f}  cam_heights median={np.median(cams@nfl+dfl):.2f}")

# 2) 白色点
mx=rgb.max(1).astype(float); mn=rgb.min(1).astype(float)
sat=(mx-mn)/np.maximum(mx,1); val=mx/255.0
white = (val>0.55)&(sat<0.28)
h=xyz@nfl+dfl   # 离地高度
print("white frac", white.mean().round(3))
# 墙点应离地 >0.2m 且法向垂直: 先在白点里 RANSAC 找垂直大平面(多次,取前几名)
wp=xyz[white]; wh=h[white]
wp=wp[wh>0.15]; print("white above floor:", len(wp))
sub=wp[rng.choice(len(wp),min(150000,len(wp)),replace=False)]

found=[]
pts=sub.copy()
for round_ in range(6):
    if len(pts)<5000: break
    cnt,(nv,d)=ransac_plane(pts, iters=800, tol=0.02)
    vert=abs(nv@nfl)  # 0=垂直墙, 1=水平
    inl=np.abs(pts@nv+d)<0.02
    found.append((cnt,nv,d,vert,pts[inl]))
    pts=pts[~inl]
for cnt,nv,d,vert,ip in found:
    ext=ip.max(0)-ip.min(0)
    print(f"plane inl={cnt:6d} n={nv.round(3)} d={d:+.3f} |n·up|={vert:.3f} extent={ext.round(2)}")
np.save("/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall/floor.npy", np.r_[nfl,dfl])
