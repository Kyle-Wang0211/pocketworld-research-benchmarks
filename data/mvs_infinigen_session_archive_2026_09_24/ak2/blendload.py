import sys, os, numpy as np
sys.path.insert(0,"/root/diffmvs_full")
os.chdir("/root/diffmvs_full")
from datasets.blend import MVSDataset
root="/root/ak_blend_v2"
lst="/tmp/v2list.txt"
open(lst,"w").write("\n".join(sorted(d for d in os.listdir(root) if d.startswith("ak_")))+"\n")
ds=MVSDataset(root,lst,mode="train",nviews=5,ndepths=384)
print("metas",len(ds))
for i in (0, len(ds)//3, len(ds)//2, len(ds)-1):
    s=ds[i]
    m=s["mask"]; d=s["depth"]
    print(" item %6d imgs %s  depth stage4 %s  mask stage4 有效 %d (%.1f%%)  depth_values %s  范围 %.3f-%.3f"%(
        i, np.asarray(s["imgs"]).shape, d["stage4"].shape, int(m["stage4"].sum()),
        100.*m["stage4"].mean(), s["depth_values"].shape,
        float(d["stage4"][m["stage4"]>0].min()), float(d["stage4"][m["stage4"]>0].max())))
    for k in ("stage1","stage2","stage3","stage4"):
        assert np.isfinite(d[k]).all(), k
print("全部 finite, blend.py 原样能读 ✓")
