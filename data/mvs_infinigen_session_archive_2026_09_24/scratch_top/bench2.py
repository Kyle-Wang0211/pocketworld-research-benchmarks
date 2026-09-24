# -*- coding: utf-8 -*-
import os, sys, time
sys.path.insert(0,"/root/diffmvs_full"); os.chdir("/root/diffmvs_full")
import torch, torch.nn.functional as F, torch.optim as optim
from torch.utils.data._utils.collate import default_collate
from models import *
from datasets import find_dataset_def
class A: pass
a=A()
src=open("/root/diffmvs_full/train.py").read().split("if __name__")[0]
ns={}; exec(compile(src,"train.py","exec"),ns)
for k,v in vars(ns["parser"].parse_args([])).items(): setattr(a,k,v)
a.numdepth=384; a.numdepth_initial=48; a.stage_iters=[1,3,3]; a.cost_dim_stage=[4,4,4]
a.CostNum=[0,4,4]; a.min_radius=0.125; a.max_radius=8; a.scale=[0.0,0.25,0.05]
a.conf_weight=0.05; a.hidden_dim=[0,32,20]; a.context_dim=[32,32,16]; a.unet_dim=[0,16,8]
NV=8
MVSDataset=find_dataset_def("blend")
ds=MVSDataset("/root/monotrain","lists/full_v3/val.txt","train",NV,a.numdepth)
def mk(B): return default_collate([ds[i] for i in range(B)])
def resz(sample,W,H):
    out={}
    out["imgs"]=[F.interpolate(t,size=(H,W),mode="bilinear",align_corners=False) for t in sample["imgs"]]
    sy=H/sample["depth"]["stage4"].shape[-2]; sx=W/sample["depth"]["stage4"].shape[-1]
    out["depth"]={k:F.interpolate(v.unsqueeze(1),size=(int(round(v.shape[-2]*sy)),int(round(v.shape[-1]*sx))),mode="nearest").squeeze(1) for k,v in sample["depth"].items()}
    out["mask"] ={k:F.interpolate(v.unsqueeze(1),size=(int(round(v.shape[-2]*sy)),int(round(v.shape[-1]*sx))),mode="nearest").squeeze(1) for k,v in sample["mask"].items()}
    out["depth_values"]=sample["depth_values"]
    pm={}
    for k,v in sample["proj_matrices"].items():
        v=v.clone(); v[:,:,1,0,:]*=sx; v[:,:,1,1,:]*=sy; pm[k]=v
    out["proj_matrices"]=pm; return out
def cu(x):
    if isinstance(x,dict): return {k:cu(v) for k,v in x.items()}
    if isinstance(x,list): return [cu(v) for v in x]
    return x.cuda()
model=CasDiffMVS(a).cuda(); opt=optim.AdamW(model.parameters(),lr=1e-3,weight_decay=1e-3,eps=1e-8); model.train()
print("%-6s %-12s %-10s %-12s %-10s %-10s"%("B","res","Mpix","step s","peak GiB","GiB/sample"))
base=None
for B,W,H in [(1,768,576),(1,1024,768),(1,1152,864),(1,1536,1152),(1,2048,1536),(2,768,576),(4,768,576)]:
    try:
        sm=cu(resz(mk(B),W,H))
        torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()
        ts=[]
        for it in range(6):
            t0=time.time(); opt.zero_grad()
            o=model(sm["imgs"],sm["proj_matrices"],sm["depth_values"],sm["depth"])
            loss,_=compute_inverse_loss(a,o["depth"],o["conf"],sm["depth"],sm["mask"],sm["depth_values"],loss_rate=0.9,iters=a.stage_iters)
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),2.0); opt.step()
            torch.cuda.synchronize()
            if it>=2: ts.append(time.time()-t0)
        ts.sort(); pk=torch.cuda.max_memory_allocated()/2**30
        print("%-6d %-12s %-10.3f %-12.3f %-10.2f %-10.2f"%(B,"%dx%d"%(W,H),W*H/1e6,ts[len(ts)//2],pk,pk/B))
        del sm; torch.cuda.empty_cache()
    except RuntimeError as e:
        print("%-6d %-12s %-10.3f FAILED %s"%(B,"%dx%d"%(W,H),W*H/1e6,str(e)[:90]))
        try: del sm
        except: pass
        torch.cuda.empty_cache()
