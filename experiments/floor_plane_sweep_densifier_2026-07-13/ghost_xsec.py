import numpy as np, struct, fr_common as fc
def load_ply(p):
    f=open(p,'rb'); hdr=b''
    while b'end_header\n' not in hdr: hdr+=f.read(1)
    L=hdr.decode().splitlines(); n=next(int(l.split()[-1]) for l in L if l.startswith('element vertex'))
    isasc='ascii' in [l for l in L if l.startswith('format')][0]
    props=[l for l in L if l.startswith('property')]
    if isasc:
        rows=[f.readline().split() for _ in range(n)]
        xyz=np.array([[float(r[0]),float(r[1]),float(r[2])] for r in rows])
        rgb=np.array([[int(float(r[3])),int(float(r[4])),int(float(r[5]))] for r in rows],np.uint8) if len(props)>=6 and 'red' in ''.join(props) else None
        return xyz,rgb
    else:
        rec=15 if any('red' in x for x in props) and len(props)==6 else 12+ (3 if any('red' in x for x in props) else 0)
        # assume xyz float + rgb uchar
        rec=15; buf=f.read(n*rec); xyz=np.zeros((n,3)); rgb=np.zeros((n,3),np.uint8)
        for i in range(n):
            xyz[i]=struct.unpack_from('<fff',buf,i*rec); rgb[i]=struct.unpack_from('<BBB',buf,i*rec+12)
        return xyz,rgb
# full production cloud
prod,_=load_ply(fc.SP+'/cap50_pull/sfm_sparse.ply')
ps,_=load_ply('floor_planesweep.ply')
# floor region bbox (u,v) from production_floor band
sift,_=load_ply('production_floor.ply')
n=fc.PLANE_N; a=np.array([1.,0,0])
if abs(n@a)>.9:a=np.array([0,0,1.])
u=a-(a@n)*n;u/=np.linalg.norm(u);v=np.cross(n,u)
suv=np.stack([sift@u,sift@v],1); umin,vmin=suv.min(0)-0.1; umax,vmax=suv.max(0)+0.1
def in_floor_region(P):
    pu=P@u; pv=P@v; return (pu>=umin)&(pu<=umax)&(pv>=vmin)&(pv<=vmax)
# floor_dist (mm) for production points inside floor footprint
pm=in_floor_region(prod); pfd=fc.floor_dist(prod[pm])*1000
psfd=fc.floor_dist(ps)*1000
print("=== 地板足迹内 production 点的 floor_dist 分布(mm,负=地板下)===")
for lo,hi in [(-60,-45),(-45,-35),(-35,-25),(-25,-15),(-15,-5),(-5,5),(5,15),(15,25),(25,45)]:
    c=((pfd>=lo)&(pfd<hi)).sum()
    bar='#'*int(c/max(1,len(pfd))*200)
    print(f"  [{lo:+3d},{hi:+3d})mm: {c:5d} {bar}")
sub=(pfd<-15)&(pfd>-50)   # 地板下鬼层带
print(f"\nproduction 地板下鬼层带(-50~-15mm)= {sub.sum()} 点 ({sub.mean()*100:.1f}% of 足迹内点)")
print(f"production 足迹内总点={len(pfd)}, 中位floor_dist={np.median(pfd):.1f}mm, std={pfd.std():.1f}mm")
print(f"\n=== plane-sweep floor_dist 分布 ===")
print(f"plane-sweep 点={len(psfd)}, 中位={np.median(psfd):.2f}mm, std={psfd.std():.2f}mm, 范围[{psfd.min():.1f},{psfd.max():.1f}]mm")
print(f"plane-sweep 在鬼层带(-50~-15mm)= {((psfd<-15)&(psfd>-50)).sum()} 点  ← 关键:有没有鬼")
np.savez('xsec_data.npz', prod_u=(prod[pm]@u), prod_fd=pfd, ps_u=(ps@u), ps_fd=psfd, sift_u=(sift@u), sift_fd=fc.floor_dist(sift)*1000)
