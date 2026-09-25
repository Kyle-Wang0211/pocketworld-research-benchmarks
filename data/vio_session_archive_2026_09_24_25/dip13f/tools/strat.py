import json,sys,numpy as np
T0=254666.645033333
I=np.loadtxt('/Users/kaidongwang/Developer/viobench-recordings/run-13f53d2f-5935-4b1a-a499-4dc8367ea935/imu.csv',delimiter=',',skiprows=1); ti=I[:,0]*1e-9; w=np.degrees(np.linalg.norm(I[:,1:4],axis=1))
S=np.load('stats/img13f5.npz'); st=S['t']
def rows(log,td):
    ev=[json.loads(l) for l in open(log) if '"ev":"loc"' in l or '"ev":"win"' in l]
    W={round(d['t'],4):d for d in ev if d['ev']=='win'}
    out=[]
    for d in ev:
        if d['ev']!='loc' or d['t']-T0<2.5: continue
        k=round(d['t'],4); wn=W.get(k)
        if not wn: continue
        tc=d['t']-td
        m=(ti>tc-0.1)&(ti<=tc); jj=np.where((st>tc-0.1)&(st<=tc+1e-4))[0]
        out.append((w[m].mean(),S['lapfull'][jj].mean(),d['in3']/max(d['n'],1),wn['rej_rpe']/max(wn['eval'],1),d['med_px']))
    return np.array(out)
q=[7.09,14.48]
for log,td in [(a.split(':')[0],float(a.split(':')[1])) for a in sys.argv[1:]]:
    A=rows(log,td); print('==',log,'td',td,'n',len(A))
    print('   median loc-inlier fraction (<3px)   gyro <20 | 20-35 | >35 deg/s')
    for lo,hi,lab in [(-1,q[0],'low-detail '),(q[0],q[1],'mid-detail '),(q[1],1e9,'high-detail')]:
        s='   '+lab
        for g0,g1 in [(0,20),(20,35),(35,999)]:
            m=(A[:,1]>lo)&(A[:,1]<=hi)&(A[:,0]>=g0)&(A[:,0]<g1)
            s+='   %.2f (%3d)'%(np.median(A[m,2]) if m.any() else np.nan,m.sum())
        print(s)
