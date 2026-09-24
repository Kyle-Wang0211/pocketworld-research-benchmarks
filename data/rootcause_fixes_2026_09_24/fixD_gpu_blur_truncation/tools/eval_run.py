#!/usr/bin/python3
"""Evaluate a replay run: Umeyama Sim3 (recon centres -> ARKit device centres, iterative 3x-median rejection),
per-frame centre residual; verified pairs of a chosen frame from the run's session.db (a run-local file)."""
import json, sqlite3, sys, os
import numpy as np
def q2R(w,x,y,z):
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],[2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],[2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])
def umeyama(A,B):
    ma,mb=A.mean(0),B.mean(0); a,b=A-ma,B-mb
    U,S,Vt=np.linalg.svd(b.T@a/len(A)); D=np.eye(3); D[2,2]=np.sign(np.linalg.det(U@Vt))
    R=U@D@Vt; s=np.trace(np.diag(S)@D)/a.var(0).sum(); t=mb-s*R@ma; return s,R,t
run, feed = sys.argv[1], sys.argv[2]; focus=int(sys.argv[3]) if len(sys.argv)>3 else 5
dev={}
for i,l in enumerate(open(feed)):
    j=json.loads(l); R=q2R(*j['arkitCamFromWorldQwxyz']); dev[j['frameIndex']]=-R.T@np.array(j['arkitCamFromWorldTxyz'])
rec={}; reg={}
for l in open(run+'/delivered_poses.txt'):
    p=l.split(); fid=int(p[1]); reg[fid]=int(p[2])
    if int(p[2]): R=q2R(*map(float,p[3:7])); rec[fid]=-R.T@np.array(list(map(float,p[7:10])))
ids=sorted(rec); A=np.array([rec[i] for i in ids]); B=np.array([dev[i] for i in ids]); keep=np.ones(len(ids),bool)
for _ in range(3):
    s,R,t=umeyama(A[keep],B[keep]); res=np.linalg.norm((s*(R@A.T)).T+t-B,axis=1)
    keep=res<=max(3*np.median(res[keep]),0.005)
out={'n_reg':int(sum(reg.values())),'n':len(reg),'scale':round(float(s),5),'median_mm':round(1e3*float(np.median(res)),1),'max_mm':round(1e3*float(res.max()),1),
     f'f{focus}_mm':round(1e3*float(res[ids.index(focus)]),1) if focus in ids else 'UNREGISTERED','outliers_>3xmed':[ids[i] for i in np.where(~keep)[0]]}
db=run+'/session.db'
if os.path.exists(db):
    con=sqlite3.connect(f'file:{db}?immutable=1',uri=True)
    name2id={n:i for i,n in con.execute('select image_id,name from images')}
    iid=name2id.get('frame_%06d.jpg'%focus)
    M=2147483647; pairs=[]
    for pid,rows in con.execute('select pair_id,rows from two_view_geometries'):
        i2=pid%M; i1=(pid-i2)//M
        if iid in (i1,i2) and rows: pairs.append(rows)
    out[f'f{focus}_verified_pairs(>=15)']=sum(r>=15 for r in pairs); out[f'f{focus}_max_inliers']=max(pairs) if pairs else 0
print(json.dumps(out))
