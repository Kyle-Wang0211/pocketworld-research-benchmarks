"""A3 门2:逐 stage 二分定位 WebGPU 的 NaN 从哪一级开始。

把 depth_predictions / photometric_confidence 的**每一项**都做成图输出,
在 CPU 与 WebGPU 上各跑一次,找第一个发散的输出。
"""
import sys, os, json
from types import SimpleNamespace
import numpy as np, torch
REPO=os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0,REPO)
from models import CasDiffMVS
from models.conv3d_as_2d import convert_
P=os.path.expanduser("~/Documents/progecttwo/_host_experiments/phone_cap_20260811")
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/66e3ee10-aa1b-493d-be5b-b2015f30ea11/scratchpad"
ND=384

class FlatAll(torch.nn.Module):
    def __init__(s,c,n): super().__init__(); s.core=c; s.n=n
    def forward(s,imgs,pm1,pm2,pm3,dv,n2,n3):
        il=[imgs[:,i] for i in range(s.n)]
        pm={"stage1":pm1,"stage2":pm2,"stage3":pm3,"stage4":pm3}
        o=s.core(il,pm,dv,ext_noise=[n2,n3])
        return tuple(o["depth"])+tuple(o["photometric_confidence"])

a=SimpleNamespace(method="casdiffmvs",numdepth_initial=48,numdepth=ND,scale=[0.,0.125,0.025],
 sampling_timesteps=[0,1,1],ddim_eta=[0,1,1],timesteps=[1000]*3,stage_iters=[1,3,3],
 cost_dim_stage=[4,4,4],CostNum=[0,4,4],hidden_dim=[0,32,20],context_dim=[32,32,16],
 unet_dim=[0,16,8],min_radius=0.125,max_radius=8)
m=CasDiffMVS(a,test=True)
D=os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/casdiffmvs_blendmvg_scratch_2026-08-16")
st=torch.load(f"{D}/ckpts/casdiffmvs_C_long_ep31.ckpt",map_location="cpu")
m.load_state_dict(st.get("model",st),strict=False); m.eval(); convert_(m)

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

flat=FlatAll(m,NIMG).eval()
with torch.no_grad(): ref=flat(imgs,*pms,dv,n2,n3)
names=[f"depth{i}" for i in range(len(ref)-3)]+["conf0","conf1","conf2"]
print(f"图输出 {len(ref)} 路: {names}")
onnx_p=f"{S}/bisect.onnx"
torch.onnx.export(flat,(imgs,*pms,dv,n2,n3),onnx_p,
    input_names=["imgs","pm1","pm2","pm3","dv","n2","n3"],output_names=names,
    opset_version=17,do_constant_folding=True,dynamo=False)
print(f"导出 OK {os.path.getsize(onnx_p)/1e6:.1f} MB\n")

import onnxruntime as ort
feed={"imgs":imgs.numpy(),"pm1":pms[0].numpy(),"pm2":pms[1].numpy(),"pm3":pms[2].numpy(),
      "dv":dv.numpy(),"n2":n2.numpy(),"n3":n3.numpy()}
res={}
for tag,eps in (("CPU",["CPUExecutionProvider"]),("WebGpu",["WebGpuExecutionProvider","CPUExecutionProvider"])):
    s=ort.InferenceSession(onnx_p,providers=eps)
    want={i.name for i in s.get_inputs()}
    res[tag]=s.run(names,{k:v for k,v in feed.items() if k in want})
print(f"{'输出':<9}{'形状':>18}{'PyTorch p50':>13}{'CPU p50':>11}{'WebGPU p50':>13}{'WebGPU NaN%':>13}  判读")
first_bad=None
for i,nm in enumerate(names):
    r=ref[i].numpy(); c=res["CPU"][i]; w=res["WebGpu"][i]
    nan=100*np.isnan(w).mean()
    okc=np.allclose(r,c,rtol=1e-3,atol=1e-5)
    okw=(not np.isnan(w).any()) and np.allclose(r,w,rtol=1e-2,atol=1e-4)
    v="✅" if okw else ("🔴 首个发散" if first_bad is None else "🔴")
    if not okw and first_bad is None: first_bad=nm
    print(f"{nm:<9}{str(tuple(r.shape)):>18}{np.median(r):13.4f}{np.median(c):11.4f}"
          f"{np.nanmedian(w) if not np.all(np.isnan(w)) else float('nan'):13.4f}{nan:12.1f}%  {v}{'' if okc else ' (CPU也不对!)'}")
print(f"\n⇒ 第一个发散的输出:{first_bad}")
