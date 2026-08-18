import numpy as np, json
from PIL import Image
S="/Users/kaidongwang/Documents/progecttwo/_artifacts/wall_forensics_20260818"
BASE="/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
def read_pfm(fp):
    with open(fp,"rb") as f:
        assert f.readline().strip()==b"Pf"
        w,h=map(int,f.readline().split()); scale=float(f.readline())
        data=np.frombuffer(f.read(w*h*4),dtype="<f4" if scale<0 else ">f4").reshape(h,w)
        return np.flipud(data).copy()
THR=[0.451643,0.534820,0.640708,0.780236,0.902385,0.952913,0.982928,0.997962]
tot=0; killed=np.zeros(len(THR),dtype=np.int64)
for fr in range(132):
    mk=np.array(Image.open(f"{BASE}/out_P16k/mask/{fr:08d}_final.png"))>0
    c=read_pfm(f"{BASE}/out_P16k/conf0/{fr:08d}.pfm")[mk]
    tot+=c.size
    for j,t in enumerate(THR): killed[j]+=int((c<t).sum())
out=[dict(thr=t,global_killed=int(k),global_pct=100*k/tot) for t,k in zip(THR,killed)]
print("total final points:",tot)
for o in out: print(f"conf0<{o['thr']:.4f}: 全局杀 {o['global_killed']:>9,} = {o['global_pct']:6.2f}%")
json.dump(dict(total=tot,rows=out),open(S+"/global_kill_20260818.json","w"),indent=1)
