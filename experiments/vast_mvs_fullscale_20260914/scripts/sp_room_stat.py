# 可证伪预测: add_room.py:48  flag = rng.rand() < 0.5  且房间包住全部相机(51-70行)
# => 有房间的场景必无背景哨兵(d>=1e3) => 背景~0 的场景应占 50%
import os, sys, glob, numpy as np
sys.path.insert(0,"/root/diffmvs"); from datasets.data_io import read_pfm
ROOT="/root/monotrain"
scans=sorted([d for d in os.listdir(ROOT) if d.startswith("sp_scene_")], key=lambda s:int(s.split("_")[-1]))
rooms=[]; noroom=[]
for sc in scans:
    fr=[]
    for fid in range(8):
        p="%s/%s/rendered_depth_maps/%08d.pfm"%(ROOT,sc,fid)
        if not os.path.exists(p): break
        d=np.array(read_pfm(p)[0],dtype=np.float32); fr.append(float((d>=1e3).mean()))
    if len(fr)<8: continue
    (rooms if max(fr)<1e-4 else noroom).append(sc)
n=len(rooms)+len(noroom)
print("样本场景数 %d" % n)
print("  无背景哨兵(=有房间) %4d   占比 %.4f    <-- 源码预测 0.50" % (len(rooms), len(rooms)/n))
print("  有背景哨兵(=无房间) %4d   占比 %.4f" % (len(noroom), len(noroom)/n))
se=(0.5*0.5/n)**0.5
print("  二项分布 1 sigma = %.4f ;  实测偏离 = %.4f sigma" % (se, abs(len(rooms)/n-0.5)/se))
open("/root/sp_rooms.txt","w").write("\n".join(rooms)+"\n")
print("  有房间场景清单 -> /root/sp_rooms.txt")
