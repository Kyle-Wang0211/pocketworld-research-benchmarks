"""2×2 隔离:{真权重,随机权重} × {真输入,随机输入},定位是权重还是数据触发。"""
import sys, os, json
from types import SimpleNamespace
import numpy as np, torch, onnxruntime as ort
REPO=os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0,REPO)
from models import CasDiffMVS
P=os.path.expanduser("~/Documents/progecttwo/_host_experiments/phone_cap_20260811")
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/66e3ee10-aa1b-493d-be5b-b2015f30ea11/scratchpad"
D=os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/casdiffmvs_blendmvg_scratch_2026-08-16")
a=SimpleNamespace(method="casdiffmvs",numdepth_initial=48,numdepth=384,scale=[0.,0.125,0.025],
 sampling_timesteps=[0,1,1],ddim_eta=[0,1,1],timesteps=[1000]*3,stage_iters=[1,3,3],
 cost_dim_stage=[4,4,4],CostNum=[0,4,4],hidden_dim=[0,32,20],context_dim=[32,32,16],
 unet_dim=[0,16,8],min_radius=0.125,max_radius=8)
m=CasDiffMVS(a,test=True)
st=torch.load(f"{D}/ckpts/casdiffmvs_C_long_ep31.ckpt",map_location="cpu")
m.load_state_dict(st.get("model",st),strict=False); m.eval()
real_hi=m.hidden_init[1]
m2=CasDiffMVS(a,test=True); m2.eval(); rand_hi=m2.hidden_init[1]   # 未加载权重=随机初始化

ctx=torch.from_numpy(np.load(f"{S}/ctx3.npy")) if os.path.exists(f"{S}/ctx3.npy") else None
if ctx is None:
    CAP={}
    class Spy(torch.nn.Module):
        def __init__(s,i): super().__init__(); s.i=i
        def forward(s,x):
            r=s.i(x); CAP["c"]=r["stage3"].detach().clone(); return r
    m.context=Spy(m.context)
    meta=json.load(open(f"{P}/fx_official/frames.json")); NF,W,H=meta["count"],meta["width"],meta["height"]; NIMG=meta["num_src"]+1
    IM=np.fromfile(f"{P}/fx_official/images.f16",np.float16).reshape(NF,H,W)
    CM=np.fromfile(f"{P}/fx_official/cams.f32",np.float32).reshape(NF,36)
    NB=np.fromfile(f"{P}/fx_official/neighbors.i32",np.int32).reshape(NF,meta["num_src"])
    f=0; view=[f]+list(NB[f])
    imgs=[torch.from_numpy(np.repeat(IM[v].astype(np.float32)[None],3,0)[None]) for v in view]
    Ks=np.stack([CM[v,0:9].reshape(3,3) for v in view])
    wc=np.stack([np.vstack([np.hstack([CM[v,9:18].reshape(3,3),CM[v,18:21][:,None]]),[0,0,0,1]]).astype(np.float32) for v in view])
    base=np.zeros((NIMG,2,4,4),np.float32); base[:,0]=wc; base[:,1,:3,:3]=Ks
    pm={}
    for s_,dv_ in (("stage1",8.),("stage2",4.),("stage3",2.),("stage4",1.)):
        mm=base.copy(); mm[:,1,:2,:]=base[:,1,:2,:]/dv_; pm[s_]=torch.from_numpy(mm[None])
    dv=torch.from_numpy(np.linspace(1/float(CM[f,25]),1/float(CM[f,24]),384,dtype=np.float32)[None])
    nz=np.load(f"{P}/bench_baseline/EXTNF/noise/{f:04d}.npz")
    with torch.no_grad():
        m(imgs,pm,dv,ext_noise=[torch.from_numpy(nz["n2"].astype(np.float32)),
                                torch.from_numpy(nz["n3"].astype(np.float32))])
    ctx=CAP["c"]; np.save(f"{S}/ctx3.npy",ctx.numpy())
print(f"真实输入 ctx3 {tuple(ctx.shape)}: |max| {ctx.abs().max():.4f}  std {ctx.std():.4f}  "
      f"零元素 {100*(ctx==0).float().mean():.1f}%")
torch.manual_seed(0); rand_ctx=torch.randn_like(ctx)
print(f"随机输入      : |max| {rand_ctx.abs().max():.4f}  std {rand_ctx.std():.4f}\n")

class Mini(torch.nn.Module):
    def __init__(s,hi): super().__init__(); s.hi=hi
    def forward(s,c):
        h,_=torch.split(c,[20,16],dim=1); return torch.tanh(s.hi(h))
print(f"{'权重':<8}{'输入':<8}{'WebGPU 非有限%':>16}{'与PyTorch最大差':>16}")
for wn,hi in (("真实",real_hi),("随机",rand_hi)):
    for xn,x in (("真实",ctx),("随机",rand_ctx)):
        mod=Mini(hi).eval()
        with torch.no_grad(): r=mod(x).numpy()
        p=f"{S}/rc22.onnx"
        torch.onnx.export(mod,(x,),p,input_names=["x"],output_names=["y"],
                          opset_version=17,do_constant_folding=True,dynamo=False)
        w=ort.InferenceSession(p,providers=["WebGpuExecutionProvider","CPUExecutionProvider"]).run(["y"],{"x":x.numpy()})[0]
        nan=100*(~np.isfinite(w)).mean()
        d=np.nanmax(np.abs(w-r)) if nan<100 else float('inf')
        print(f"{wn:<8}{xn:<8}{nan:15.2f}%{d:16.3e}  {'🔴' if (nan>0 or d>1e-3) else '✅'}")
