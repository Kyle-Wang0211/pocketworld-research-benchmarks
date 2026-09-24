import sys, numpy as np
P=sys.argv[1]
V=[];F=[]
for ln in open(P,errors="ignore"):
    if ln.startswith("v "): V.append(ln.split()[1:4])
    elif ln.startswith("f "):
        F.append([int(t.split("/")[0]) for t in ln.split()[1:4]])
V=np.asarray(V,dtype=np.float64); F=np.asarray(F,dtype=np.int64)-1
a=V[F[:,0]];b=V[F[:,1]];c=V[F[:,2]]
e=np.stack([np.linalg.norm(b-a,axis=1),np.linalg.norm(c-b,axis=1),np.linalg.norm(a-c,axis=1)],1)
emax=e.max(1)*1000.0
area=0.5*np.linalg.norm(np.cross(b-a,c-a),axis=1)
tot=area.sum()
print(f"{P}\n  {len(V):,} v  {len(F):,} f   total area {tot:.2f} m^2   mean tri {tot/len(F)*1e6:.2f} mm^2")
print(f"  最长边 mm  p50 {np.percentile(emax,50):.1f}  p90 {np.percentile(emax,90):.1f}  p99 {np.percentile(emax,99):.1f}  max {emax.max():.0f}")
print("  --- 按最长边分档: 该档三角占比 / 该档占总面积 ---")
bins=[0,2,5,10,20,50,100,1e9]; lbl=["<2mm","2-5","5-10","10-20","20-50","50-100",">100mm"]
for i in range(len(bins)-1):
    m=(emax>=bins[i])&(emax<bins[i+1])
    if m.sum(): print(f"   {lbl[i]:>8}  三角 {100*m.sum()/len(F):6.2f}%   面积 {100*area[m].sum()/tot:6.2f}%")
o=np.argsort(-area); cum=np.cumsum(area[o])/tot
for q in [0.25,0.5,0.75]:
    k=int(np.searchsorted(cum,q))+1
    print(f"  面积的 {int(q*100)}% 由最大的 {k:,} 个三角({100*k/len(F):.2f}%)贡献")
