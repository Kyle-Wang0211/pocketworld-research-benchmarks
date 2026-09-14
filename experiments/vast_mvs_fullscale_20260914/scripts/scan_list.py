#!/usr/bin/env python3
"""逐个拉验证集样本,找出 assert mask.sum()>0 会炸的那些 scan/帧。"""
import sys, os, collections
sys.path.insert(0,"/root/MonoMVSNet"); os.chdir("/root/MonoMVSNet")
from datasets.blendedmvs import MVSDataset
ds = MVSDataset("/root/monotrain", sys.argv[1], "val", 9)
print(f"验证集 {len(ds.metas)} 组", flush=True)
bad = collections.Counter(); badframe=[]
for i in range(len(ds.metas)):
    try:
        ds[i]
    except AssertionError:
        scan, ref, _ = ds.metas[i]; bad[scan]+=1; badframe.append((scan,ref))
    except Exception as e:
        scan, ref, _ = ds.metas[i]; bad[scan]+=1; badframe.append((scan,ref,type(e).__name__))
    if i and i%3000==0: print(f"  {i}/{len(ds.metas)}  已发现坏 {sum(bad.values())}", flush=True)
print(f"\n坏样本 {sum(bad.values())} 组, 涉及 {len(bad)} 个 scan:")
for s,c in bad.most_common(): print(f"   {s:44s} {c} 组")
open("/root/bad_val_exact_scans.txt","w").write("\n".join(bad)+"\n")
