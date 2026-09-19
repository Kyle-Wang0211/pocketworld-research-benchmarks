# [对比数据 2026-08-31] PLY → viewer 吃的 .pos/.col,并算 META。
# viewer 格式取自 .tmp/mapanything_mvconf_index.html:
#   <tag>.pos = float32 xyz 连续;  <tag>.col = uint8 rgb 连续
import numpy as np, json
from pathlib import Path
PLY=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
def load(p):
    with open(p,"rb") as f:
        while True:
            l=f.readline()
            if l.startswith(b"element vertex "): n=int(l.split()[-1])
            if l.strip()==b"end_header": break
        return np.frombuffer(f.read(n*PLY.itemsize),dtype=PLY,count=n)
def meta(xyz):
    lo,hi=xyz.min(0),xyz.max(0); med=np.median(xyz,0)
    return {"n":int(len(xyz)),"center":(lo+hi).tolist(),
            "ext":(hi-lo).tolist(),"med":med.tolist(),
            "radius":float(np.linalg.norm(np.percentile(xyz,90,axis=0)-med))}
def dump(tag,xyz,rgb,out=Path("compare/bin")):
    out.mkdir(parents=True,exist_ok=True)
    xyz.astype("<f4").tofile(out/f"{tag}.pos"); rgb.astype("u1").tofile(out/f"{tag}.col")
    m=meta(xyz); m["center"]=[float((a+b)/2) for a,b in zip(xyz.min(0),xyz.max(0))]
    m["ext"]=[float(v) for v in m["ext"]]; m["med"]=[float(v) for v in m["med"]]
    print(f"  {tag:12s} {len(xyz):>9,d} 点  pos {(out/f'{tag}.pos').stat().st_size/2**20:5.1f} MB")
    return m
TARGET=1_500_000
ARMS=[("k64","fixed_full64/cloud_k64_ov0.ply","K=64 重叠0 · 3块"),
      ("k8","fixed_k8/cloud_k8_ov2.ply","K=8 重叠2 · 22块"),
      ("k4","fixed_k4/cloud_k4_ov2.ply","K=4 重叠2 · 66块")]
META={}; RAW={}
rng=np.random.default_rng(0)
for tag,p,_ in ARMS:
    a=load(p); xyz=np.stack([a["x"],a["y"],a["z"]],1); rgb=np.stack([a["r"],a["g"],a["b"]],1)
    RAW[tag]=xyz            # 差异染色要用全量
    idx=rng.choice(len(xyz),min(TARGET,len(xyz)),replace=False); idx.sort()
    META[tag]=dump(tag,xyz[idx],rgb[idx]); META[tag]["full_n"]=int(len(xyz))
json.dump(META,open("compare/meta.json","w"))
np.save("compare/_raw_k64.npy",RAW["k64"]); np.save("compare/_raw_k8.npy",RAW["k8"])
print("✅ A 页数据完成")
