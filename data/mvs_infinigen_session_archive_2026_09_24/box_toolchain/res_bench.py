# -*- coding: utf-8 -*-
"""Cost of raising TRAINING input resolution. Builds the real CasDiffMVS exactly as train.py:323-332,
feeds real monotrain samples upsampled to the target size, runs fwd+bwd+step. READ-ONLY on data."""
import os, sys, time, argparse, json
sys.path.insert(0, "/root/diffmvs_full")
os.chdir("/root/diffmvs_full")
import torch, torch.nn.functional as F
import torch.optim as optim
from torch.utils.data._utils.collate import default_collate
from models import *
from datasets import find_dataset_def

class A: pass
a=A()
a.numdepth=384; a.numdepth_initial=48; a.stage_iters=[1,3,3]; a.cost_dim_stage=[4,4,4]
a.CostNum=[0,4,4]; a.min_radius=0.125; a.max_radius=8; a.scale=[0.0,0.25,0.05]
a.conf_weight=0.05; a.hidden_dim=[0,32,20]; a.context_dim=[32,32,16]; a.unet_dim=[0,16,8]
a.ddim_eta=[0.01,0.01,0.01]; a.sampling_timesteps=[1,1,1]; a.timestep=[1,1,1]
# pull any remaining defaults straight from train.py's parser so we cannot silently diverge
import importlib.util
spec=importlib.util.spec_from_file_location("tp","/root/diffmvs_full/train.py")
src=open("/root/diffmvs_full/train.py").read().split("if __name__")[0]
ns={}
exec(compile(src,"train.py","exec"),ns)
defaults=vars(ns["parser"].parse_args([]))
for k,v in defaults.items():
    if not hasattr(a,k): setattr(a,k,v)
a.numdepth=384; a.numdepth_initial=48; a.stage_iters=[1,3,3]; a.cost_dim_stage=[4,4,4]
a.CostNum=[0,4,4]; a.min_radius=0.125; a.max_radius=8; a.scale=[0.0,0.25,0.05]
a.conf_weight=0.05; a.hidden_dim=[0,32,20]; a.context_dim=[32,32,16]; a.unet_dim=[0,16,8]

B=4; NV=8
MVSDataset=find_dataset_def("blend")
ds=MVSDataset("/root/monotrain","lists/full_v3/val.txt","train",NV,a.numdepth)
base=default_collate([ds[i] for i in range(B)])
print("base shapes: imgs", len(base["imgs"]), base["imgs"][0].shape, "depth s4", base["depth"]["stage4"].shape)

def scaled(sample, s):
    out={}
    out["imgs"]=[F.interpolate(t, scale_factor=s, mode="bilinear", align_corners=False) for t in sample["imgs"]]
    out["depth"]={k: F.interpolate(v.unsqueeze(1), scale_factor=s, mode="nearest").squeeze(1) for k,v in sample["depth"].items()}
    out["mask"] ={k: F.interpolate(v.unsqueeze(1), scale_factor=s, mode="nearest").squeeze(1) for k,v in sample["mask"].items()}
    out["depth_values"]=sample["depth_values"]
    pm={}
    for k,v in sample["proj_matrices"].items():
        v=v.clone(); v[:,:,1,:2,:]*=s; pm[k]=v
    out["proj_matrices"]=pm
    return out

def tocuda(x):
    if isinstance(x,dict): return {k:tocuda(v) for k,v in x.items()}
    if isinstance(x,list): return [tocuda(v) for v in x]
    return x.cuda()

model=CasDiffMVS(a).cuda()
opt=optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3, eps=1e-8)
model.train()
print("params", sum(p.data.nelement() for p in model.parameters()))

rows=[]
for s in [1.0, 1.25, 1.5, 2.0]:
    sm=tocuda(scaled(base,s))
    H,W=sm["imgs"][0].shape[-2:]
    torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()
    ts=[]
    try:
        for it in range(7):
            t0=time.time()
            opt.zero_grad()
            o=model(sm["imgs"], sm["proj_matrices"], sm["depth_values"], sm["depth"])
            loss,_=compute_inverse_loss(a,o["depth"],o["conf"],sm["depth"],sm["mask"],
                                        sm["depth_values"],loss_rate=0.9,iters=a.stage_iters)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),2.0)
            opt.step()
            torch.cuda.synchronize()
            if it>=2: ts.append(time.time()-t0)
        ts.sort()
        peak=torch.cuda.max_memory_allocated()/2**30
        rsv=torch.cuda.max_memory_reserved()/2**30
        rows.append((s,W,H,ts[len(ts)//2],peak,rsv,"ok"))
        print("scale %.2f  %dx%d  med step %.3f s  peak alloc %.2f GiB  reserved %.2f GiB"%(s,W,H,ts[len(ts)//2],peak,rsv))
    except RuntimeError as e:
        rows.append((s,W,H,None,None,None,str(e)[:120]))
        print("scale %.2f  %dx%d  FAILED: %s"%(s,W,H,str(e)[:160]))
        torch.cuda.empty_cache()
    del sm
    torch.cuda.empty_cache()
print()
base_t=rows[0][3]; base_m=rows[0][4]
print("%-8s %-12s %-10s %-10s %-10s %-10s"%("scale","res","step s","x time","peak GiB","x mem"))
for s,W,H,t,m,r,st in rows:
    if t is None: print("%-8.2f %-12s %-10s %-10s %-10s %s"%(s,"%dx%d"%(W,H),"-","-","-",st)); continue
    print("%-8.2f %-12s %-10.3f %-10.2f %-10.2f %-10.2f"%(s,"%dx%d"%(W,H),t,t/base_t,m,m/base_m))
