import numpy as np, glob
rng=np.random.default_rng(7)
DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
def load(p, stride=1):
    with open(p,"rb") as f:
        hdr=b""
        while True:
            l=f.readline(); hdr+=l
            if l.strip()==b"end_header": break
        n=int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1])
        off=len(hdr)
    m=np.memmap(p,dtype=DT,mode="r",offset=off,shape=(n,))
    d=np.array(m[::stride])
    return np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)

nfl_d=np.load("/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall/floor.npy")
up=nfl_d[:3]; dfl=nfl_d[3]

xyz,rgb=load("/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/dense_P16k.ply",stride=20)
mx=rgb.max(1).astype(float); mn=rgb.min(1).astype(float)
white=(mx/255>0.55)&((mx-mn)/np.maximum(mx,1)<0.28)
h=xyz@up+dfl

nw=np.array([0.46,-0.679,-0.572]); nw/=np.linalg.norm(nw)
for dw,tag in [(4.734,"A(d=4.73)"),(4.327,"B(d=4.33)")]:
    m=white&(h>0.15)&(np.abs(xyz@nw+dw)<0.05)
    pts=xyz[m]
    # 体素连通域 (0.08 voxel)
    vox=np.floor(pts/0.08).astype(np.int64)
    key=vox[:,0]*73856093^vox[:,1]*19349663^vox[:,2]*83492791
    uk,inv,cnts=np.unique(key,return_inverse=True,return_counts=True)
    # 简单 BFS 连通域太慢用 hash;改用 in-plane 2D 网格连通域
    u=np.cross(up,nw); u/=np.linalg.norm(u); v=np.cross(nw,u)
    pu=pts@u; pv=pts@v
    gs=0.10
    gi=np.floor(pu/gs).astype(int); gj=np.floor(pv/gs).astype(int)
    from collections import defaultdict
    cells=defaultdict(int)
    for a,b in zip(gi,gj): cells[(a,b)]+=1
    occ={c for c,n_ in cells.items() if n_>=3}
    # BFS
    seen=set(); comps=[]
    for c in occ:
        if c in seen: continue
        stack=[c]; seen.add(c); comp=[]
        while stack:
            cur=stack.pop(); comp.append(cur)
            for dx in(-1,0,1):
                for dy in(-1,0,1):
                    nb=(cur[0]+dx,cur[1]+dy)
                    if nb in occ and nb not in seen:
                        seen.add(nb); stack.append(nb)
        comps.append(comp)
    comps.sort(key=lambda c:-len(c))
    big=set(comps[0])
    inb=np.array([(a,b) in big for a,b in zip(gi,gj)])
    P=pts[inb]
    print(f"{tag}: slab点 {len(pts)}, 最大连通片 {len(P)} 点, u范围[{pu[inb].min():.2f},{pu[inb].max():.2f}] v范围[{pv[inb].min():.2f},{pv[inb].max():.2f}] 离地[{(P@up+dfl).min():.2f},{(P@up+dfl).max():.2f}]")
    np.save(f"/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall/patch_{tag[0]}.npy",P)
