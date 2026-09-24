import sys, os, numpy as np, glob
sys.path.insert(0,"/root/diffmvs_full"); os.chdir("/root/diffmvs_full")
from datasets.blend import MVSDataset
root="/root/ak_blend_v2"
hr=["ak_41048190","ak_47670195","ak_45261257","ak_47430094","ak_48018315"]
lo=["ak_47430657","ak_47333653","ak_44796396"]
for nm,sc in (("highres(FARO)",hr),("lowres(LiDAR)",lo)):
    sc=[s for s in sc if os.path.isdir(os.path.join(root,s))]
    if not sc: continue
    open("/tmp/l.txt","w").write("\n".join(sc)+"\n")
    ds=MVSDataset(root,"/tmp/l.txt",mode="train",nviews=5,ndepths=384)
    idx=range(0,len(ds),max(1,len(ds)//80))
    v={k:[] for k in ("stage1","stage2","stage3","stage4")}
    for i in idx:
        m=ds[i]["mask"]
        for k in v: v[k].append(float(m[k].mean()))
    print("%s  %d 场景 / %d metas  抽 %d 个样本"%(nm,len(sc),len(ds),len(list(idx))))
    for k in ("stage1","stage2","stage3","stage4"):
        a=np.array(v[k]); print("   %s mask 有效比例 中位 %.4f  p10 %.4f"%(k,np.median(a),np.percentile(a,10)))
