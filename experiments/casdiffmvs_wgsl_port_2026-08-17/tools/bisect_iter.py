"""切进 stage3:把 3 次 GRU 迭代的每一步中间量做成图输出,找 NaN 从哪一步开始。"""
import sys, os, json
from types import SimpleNamespace
import numpy as np, torch
REPO=os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0,REPO)
from models import CasDiffMVS
from models.conv3d_as_2d import convert_
P=os.path.expanduser("~/Documents/progecttwo/_host_experiments/phone_cap_20260811")
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/66e3ee10-aa1b-493d-be5b-b2015f30ea11/scratchpad"
D=os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/casdiffmvs_blendmvg_scratch_2026-08-16")
ND=384

class Spy(torch.nn.Module):
    """包住 stage3 的 update_block,把它内部返回的完整序列留下来。"""
    def __init__(s,inner): super().__init__(); s.inner=inner; s.saved=None
    def forward(s,*a,**k):
        r=s.inner(*a,**k)
        s.saved=(list(r[2]),list(r[3]))      # inv_depth_seqs, conf_seqs
        return r

class FlatDbg(torch.nn.Module):
    def __init__(s,c,n,spy): super().__init__(); s.core=c; s.n=n; s.spy=spy
    def forward(s,imgs,pm1,pm2,pm3,dv,n2,n3):
        il=[imgs[:,i] for i in range(s.n)]
        o=s.core(il,{"stage1":pm1,"stage2":pm2,"stage3":pm3,"stage4":pm3},dv,ext_noise=[n2,n3])
        ivs,cfs=s.spy.saved
        return tuple(ivs)+tuple(cfs)

a=SimpleNamespace(method="casdiffmvs",numdepth_initial=48,numdepth=ND,scale=[0.,0.125,0.025],
 sampling_timesteps=[0,1,1],ddim_eta=[0,1,1],timesteps=[1000]*3,stage_iters=[1,3,3],
 cost_dim_stage=[4,4,4],CostNum=[0,4,4],hidden_dim=[0,32,20],context_dim=[32,32,16],
 unet_dim=[0,16,8],min_radius=0.125,max_radius=8)
m=CasDiffMVS(a,test=True)
st=torch.load(f"{D}/ckpts/casdiffmvs_C_long_ep31.ckpt",map_location="cpu")
m.load_state_dict(st.get("model",st),strict=False); m.eval(); convert_(m)
spy=Spy(m.update_block[1]); m.update_block[1]=spy      # index 1 = stage3

meta=json.load(open(f"{P}/fx_official/frames.json")); NF,W,H=meta["count"],meta["width"],meta["height"]; NIMG=meta["num_src"]+1
IM=np.fromfile(f"{P}/fx_official/images.f16",np.float16).reshape(NF,H,W)
CM=np.fromfile(f"{P}/fx_official/cams.f32",np.float32).reshape(NF,36)
NB=np.fromfile(f"{P}/fx_official/neighbors.i32",np.int32).reshape(NF,meta["num_src"])
f=0; view=[f]+list(NB[f])
imgs=torch.from_numpy(np.stack([np.repeat(IM[v].astype(np.float32)[None],3,0) for v in view])[None])
Ks=np.stack([CM[v,0:9].reshape(3,3) for v in view])
wc=np.stack([np.vstack([np.hstack([CM[v,9:18].reshape(3,3),CM[v,18:21][:,None]]),[0,0,0,1]]).astype(np.float32) for v in view])
base=np.zeros((NIMG,2,4,4),np.float32); base[:,0]=wc; base[:,1,:3,:3]=Ks
pms=[]
for dv_ in (8.,4.,2.):
    mm=base.copy(); mm[:,1,:2,:]=base[:,1,:2,:]/dv_; pms.append(torch.from_numpy(mm[None]))
dv=torch.from_numpy(np.linspace(1/float(CM[f,25]),1/float(CM[f,24]),ND,dtype=np.float32)[None])
nz=np.load(f"{P}/bench_baseline/EXTNF/noise/{f:04d}.npz")
n2=torch.from_numpy(nz["n2"].astype(np.float32)); n3=torch.from_numpy(nz["n3"].astype(np.float32))

flat=FlatDbg(m,NIMG,spy).eval()
with torch.no_grad(): ref=flat(imgs,*pms,dv,n2,n3)
k=len(ref)//2
names=[f"iv{i}" for i in range(k)]+[f"cf{i}" for i in range(k)]
print(f"stage3 内部 {k} 次迭代,输出 {len(ref)} 路\n")
op=f"{S}/bisect_iter.onnx"
torch.onnx.export(flat,(imgs,*pms,dv,n2,n3),op,
  input_names=["imgs","pm1","pm2","pm3","dv","n2","n3"],output_names=names,
  opset_version=17,do_constant_folding=True,dynamo=False)

import onnxruntime as ort
feed={"imgs":imgs.numpy(),"pm1":pms[0].numpy(),"pm2":pms[1].numpy(),"pm3":pms[2].numpy(),
      "dv":dv.numpy(),"n2":n2.numpy(),"n3":n3.numpy()}
res={}
for tag,eps in (("CPU",["CPUExecutionProvider"]),("WGPU",["WebGpuExecutionProvider","CPUExecutionProvider"])):
    s=ort.InferenceSession(op,providers=eps); want={i.name for i in s.get_inputs()}
    res[tag]=s.run(names,{kk:v for kk,v in feed.items() if kk in want})
print(f"{'输出':<6}{'PyTorch p50':>13}{'CPU p50':>11}{'WebGPU p50':>13}{'NaN%':>8}{'Inf%':>8}  判读")
bad=None
for i,nm in enumerate(names):
    r=ref[i].numpy(); c=res["CPU"][i]; w=res["WGPU"][i]
    nan=100*np.isnan(w).mean(); inf=100*np.isinf(w).mean()
    wm=np.nanmedian(w) if not np.all(np.isnan(w)) else float('nan')
    ok=(nan==0 and inf==0 and np.allclose(r,w,rtol=2e-2,atol=1e-3))
    if not ok and bad is None: bad=nm
    print(f"{nm:<6}{np.median(r):13.5f}{np.median(c):11.5f}{wm:13.5f}{nan:7.1f}%{inf:7.1f}%  {'✅' if ok else ('🔴 首个坏' if bad==nm else '🔴')}")
print(f"\n⇒ stage3 内第一个坏掉的:{bad}")
