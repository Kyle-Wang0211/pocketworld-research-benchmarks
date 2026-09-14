import os, sys, glob, numpy as np, collections
sys.path.insert(0,"/root/diffmvs"); from datasets.data_io import read_pfm
ROOT="/root/monotrain"
bmvs=[d for d in sorted(os.listdir(ROOT)) if len(d)==24 and all(c in "0123456789abcdef" for c in d) and os.path.isdir(os.path.join(ROOT,d,"cams"))]
T=[]; nums=collections.Counter()
for s in bmvs[:80]:
    for c in sorted(glob.glob(os.path.join(ROOT,s,"cams","*_cam.txt")))[:8]:
        t=[l.rstrip() for l in open(c)][11].split()
        if len(t)!=4: continue
        dmin,iv,num,dmax=float(t[0]),float(t[1]),float(t[2]),float(t[3])
        nums[num]+=1; T.append((dmin,iv,num,dmax))
T=np.array(T); print("n=",len(T)); print("DEPTH_NUM 取值:",nums.most_common(5))
print()
for k,lab in [(1,"dmin + (num-1)*iv"),(0,"dmin + num*iv")]:
    pred=T[:,0]+(T[:,2]-k)*T[:,1]
    rel=np.abs(pred-T[:,3])/T[:,3]
    print("%-20s  rel_err 中位 %.3e  max %.3e" % (lab, np.median(rel), rel.max()))
print()
iv_pred=(T[:,3]-T[:,0])/(T[:,2]-1)
print("iv vs (dmax-dmin)/(num-1)   rel 中位 %.3e" % np.median(np.abs(iv_pred-T[:,1])/T[:,1]))
