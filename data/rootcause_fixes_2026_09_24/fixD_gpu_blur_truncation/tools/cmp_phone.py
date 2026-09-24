import sys; sys.path.insert(0,'tools')
from binkp import read, summ
from kpstats import load, scale_orient
import numpy as np
from scipy.spatial import cKDTree
def cmp(db, iid, binp, tag=''):
    con, imgs, kps, descs, tvg = load(db)
    a=kps[iid]; s,_=scale_orient(a); pd=descs[iid]
    r,d=read(binp)
    dist,idx=cKDTree(r[:,:2]).query(a[:,:2])
    m=dist<0.05
    dd=np.abs(pd[m].astype(int)-d[idx[m]].astype(int)).max(1) if m.any() else np.array([-1])
    # reverse: fraction of ref kps matched by phone
    dist2,_=cKDTree(a[:,:2]).query(r[:,:2])
    print(f'{tag:28s} ref_n={len(r):6d} phone->ref match@0.05px={m.mean():.3f} ref->phone={np.mean(dist2<0.05):.3f} desc maxdiff med={np.median(dd):.0f} | ' + summ('ref',r[:,:2],r[:,2])[29:])
if __name__=='__main__':
    cmp(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4] if len(sys.argv)>4 else '')
