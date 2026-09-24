import re, numpy as np, pandas as pd
m=pd.read_csv("/root/arkit_raw/raw/metadata.csv")
ups=set(int(v) for v in m[m["is_in_upsampling"]==True]["video_id"])
tot_kf=0; ups_kf=0; ups_n=0; non_kf=0; non_n=0
for l in open("/root/arkit_all.log"):
    g=re.match(r"\s+ak_(\d+): 图 (\d+) \| 有位姿 (\d+) \| 关键帧 (\d+)", l)
    if not g: continue
    v=int(g.group(1)); k=int(g.group(4)); tot_kf+=k
    if v in ups: ups_kf+=k; ups_n+=1
    else: non_kf+=k; non_n+=1
print("v1 关键帧: 全域 %d"%tot_kf)
print("  有 highres 的 %d 个视频: %d 关键帧 (%.1f%%), 约 %.2f TiB"%(ups_n,ups_kf,100.*ups_kf/tot_kf,ups_kf*1.78/2**20))
print("  无 highres 的 %d 个视频: %d 关键帧 (%.1f%%), 约 %.2f TiB"%(non_n,non_kf,100.*non_kf/tot_kf,non_kf*1.78/2**20))
