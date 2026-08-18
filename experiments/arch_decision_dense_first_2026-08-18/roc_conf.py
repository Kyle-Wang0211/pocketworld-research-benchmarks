# 第0刀: 官方 confidence 三通道 ROC — 偏移层(blob) vs 真墙(idx_A) 像素级可分性
# 标签: blob_idx.npy (r∈(-0.55,-0.08) gauge 偏移层点), idx_A.npy (白墙面 |r|<0.06)
# 映射: dense_P16k.ply 按帧拼块(offs.npy), 块内=final mask 行主序 → (y,x) → conf pfm 同分辨率
import numpy as np, json
from PIL import Image
S="/Users/kaidongwang/Documents/progecttwo/_artifacts/wall_forensics_20260818"
BASE="/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
def read_pfm(fp):
    with open(fp,"rb") as f:
        assert f.readline().strip()==b"Pf"
        w,h=map(int,f.readline().split())
        scale=float(f.readline())
        data=np.frombuffer(f.read(w*h*4),dtype="<f4" if scale<0 else ">f4").reshape(h,w)
        return np.flipud(data).copy()
offs=np.load(S+"/offs.npy")
BL=np.load(S+"/blob_idx.npy")
IA=np.load("/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall/idx_A.npy")
FRAMES=[78,79,80,81,82,83,85,86,87,100,103,107,125]

def auc_blob_lower(cb,cw):
    # AUC = P(conf_blob < conf_wall) + 0.5 P(=) ; >0.5 => 偏移层conf更低(可用作杀点信号)
    from scipy.stats import mannwhitneyu
    if len(cb)==0 or len(cw)==0: return None
    U=mannwhitneyu(cw,cb,alternative="two-sided").statistic  # U of cw>cb
    return float(U/(len(cb)*len(cw)))

per=[]; pool={0:([],[]),1:([],[]),2:([],[])}
for fr in FRAMES:
    mk=np.array(Image.open(f"{BASE}/out_P16k/mask/{fr:08d}_final.png"))>0
    yy,xx=np.nonzero(mk)
    mb=(BL>=offs[fr])&(BL<offs[fr+1]); lb=BL[mb]-offs[fr]
    ma=(IA>=offs[fr])&(IA<offs[fr+1]); la=IA[ma]-offs[fr]
    by,bx=yy[lb],xx[lb]; wy,wx=yy[la],xx[la]
    row=dict(frame=fr,n_blob=int(len(bx)),n_wall=int(len(wx)))
    for i in range(3):
        c=read_pfm(f"{BASE}/out_P16k/conf{i}/{fr:08d}.pfm")
        cb=c[by,bx]; cw=c[wy,wx]
        pool[i][0].append(cb); pool[i][1].append(cw)
        row[f"auc{i}"]=auc_blob_lower(cb,cw)
        if i==0:
            row["conf0_blob_med"]=float(np.median(cb)) if len(cb) else None
            row["conf0_wall_med"]=float(np.median(cw)) if len(cw) else None
    per.append(row)
    print(fr,{k:round(v,3) if isinstance(v,float) else v for k,v in row.items()})

out=dict(per_frame=per)
for i in range(3):
    cb=np.concatenate(pool[i][0]); cw=np.concatenate(pool[i][1])
    out[f"pooled_auc{i}"]=auc_blob_lower(cb,cw)
    aucs=[r[f"auc{i}"] for r in per if r[f"auc{i}"] is not None]
    out[f"auc{i}_median"]=float(np.median(aucs)); out[f"auc{i}_min"]=float(np.min(aucs)); out[f"auc{i}_max"]=float(np.max(aucs))
    print(f"conf{i}: pooled AUC={out[f'pooled_auc{i}']:.3f}  逐帧中位={out[f'auc{i}_median']:.3f} 范围[{out[f'auc{i}_min']:.3f},{out[f'auc{i}_max']:.3f}]")

# 工作点表: conf0 全局阈值扫描 (在13帧 pooled blob/wall 上)
cb0=np.concatenate(pool[0][0]); cw0=np.concatenate(pool[0][1])
qs=np.quantile(np.concatenate([cb0,cw0]),[0.001,0.005,0.01,0.02,0.05,0.10,0.20,0.5])
wp=[]
for t in qs:
    det=float((cb0<t).mean()); fk=float((cw0<t).mean())
    wp.append(dict(thr=float(t),blob_kill=det,wall_kill=fk))
out["conf0_workpoints"]=wp
for w in wp: print(f"thr<{w['thr']:.6f}: 截偏移层 {100*w['blob_kill']:5.1f}%  误杀真墙 {100*w['wall_kill']:5.1f}%")
json.dump(out,open(S+"/roc_conf_20260818.json","w"),indent=1)
