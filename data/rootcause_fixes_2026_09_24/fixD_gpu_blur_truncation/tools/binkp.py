import numpy as np
def read(p):
    b=open(p,'rb').read(); n=int(np.frombuffer(b[:4],np.int32)[0])
    r=np.frombuffer(b[4:4+16*n],np.float32).reshape(n,4)
    d=np.frombuffer(b[4+16*n:4+16*n+128*n],np.uint8).reshape(n,128)
    return r,d
def summ(tag,xy,s,W=4032,H=3024):
    g,_,_=np.histogram2d(xy[:,1],xy[:,0],bins=[3,4],range=[[0,H],[0,W]])
    return f"{tag:28s} n={len(s):6d} s p10/med/p90={np.percentile(s,10):.2f}/{np.median(s):.2f}/{np.percentile(s,90):.2f} <3px={np.mean(s<3):.2f} xmed={np.median(xy[:,0]):.0f} ymed={np.median(xy[:,1]):.0f} cols={g.sum(0).astype(int).tolist()} rows={g.sum(1).astype(int).tolist()}"
