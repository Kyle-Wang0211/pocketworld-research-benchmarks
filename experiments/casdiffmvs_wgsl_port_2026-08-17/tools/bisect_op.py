"""切到算子级:stage3 第一次迭代内部 GetCost→encoder→unet 的进出。"""
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

CAP={}
def cap(k,t):
    if k not in CAP: CAP[k]=t
    return t

IN3=[False]
class SpyGetCost(torch.nn.Module):
    """🔴 不靠数调用次数(我数错过):由 stage3 的 update_block 打开标志位,
       GetCost 只在标志位为真时抓第一次。"""
    def __init__(s,inner): super().__init__(); s.inner=inner
    def forward(s,*a,**k):
        r=s.inner(*a,**k)
        if IN3[0]: cap("cost",r[0]); cap("idsamp",r[1])
        return r
class SpyBlock(torch.nn.Module):
    def __init__(s,inner): super().__init__(); s.inner=inner
    def forward(s,*a,**k):
        IN3[0]=True
        try: return s.inner(*a,**k)
        finally: IN3[0]=False
class SpyEnc(torch.nn.Module):
    def __init__(s,inner): super().__init__(); s.inner=inner; s.n=0
    def forward(s,*a,**k):
        r=s.inner(*a,**k); s.n+=1
        if s.n==1: cap("encout",r)
        return r
class SpyUnet(torch.nn.Module):
    def __init__(s,inner): super().__init__(); s.inner=inner; s.n=0
    def forward(s,x,h,t):
        s.n+=1
        if s.n==1: cap("unet_in_x",x); cap("unet_in_h",h)
        r=s.inner(x,h,t)
        if s.n==1: cap("unet_hidden",r[0]); cap("unet_update",r[1]); cap("unet_conf",r[2])
        return r

class Flat(torch.nn.Module):
    def __init__(s,c,n): super().__init__(); s.core=c; s.n=n
    def forward(s,imgs,pm1,pm2,pm3,dv,n2,n3):
        # 🔴 CAP 清了但 spy 的计数器不清 ⇒ 第二次 forward(导出时)n 已越过 1,
        #    再也抓不到,而 CAP 是空的 → KeyError。计数器必须一起复位。
        CAP.clear()
        for _sp in (s.core.update_block[1].inner.encoder,
                    s.core.update_block[1].inner.unet):
            _sp.n = 0
        il=[imgs[:,i] for i in range(s.n)]
        s.core(il,{"stage1":pm1,"stage2":pm2,"stage3":pm3,"stage4":pm3},dv,ext_noise=[n2,n3])
        return tuple(CAP[k] for k in KEYS)

KEYS=["cost","idsamp","encout","unet_in_x","unet_in_h","unet_hidden","unet_update","unet_conf"]
a=SimpleNamespace(method="casdiffmvs",numdepth_initial=48,numdepth=384,scale=[0.,0.125,0.025],
 sampling_timesteps=[0,1,1],ddim_eta=[0,1,1],timesteps=[1000]*3,stage_iters=[1,3,3],
 cost_dim_stage=[4,4,4],CostNum=[0,4,4],hidden_dim=[0,32,20],context_dim=[32,32,16],
 unet_dim=[0,16,8],min_radius=0.125,max_radius=8)
m=CasDiffMVS(a,test=True)
st=torch.load(f"{D}/ckpts/casdiffmvs_C_long_ep31.ckpt",map_location="cpu")
m.load_state_dict(st.get("model",st),strict=False); m.eval(); convert_(m)
m.GetCost=SpyGetCost(m.GetCost)
ub=m.update_block[1]                       # stage3
ub.encoder=SpyEnc(ub.encoder); ub.unet=SpyUnet(ub.unet)
m.update_block[1]=SpyBlock(ub)

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
dv=torch.from_numpy(np.linspace(1/float(CM[f,25]),1/float(CM[f,24]),384,dtype=np.float32)[None])
nz=np.load(f"{P}/bench_baseline/EXTNF/noise/{f:04d}.npz")
n2=torch.from_numpy(nz["n2"].astype(np.float32)); n3=torch.from_numpy(nz["n3"].astype(np.float32))
flat=Flat(m,NIMG).eval()
with torch.no_grad(): ref=flat(imgs,*pms,dv,n2,n3)
op=f"{S}/bisect_op.onnx"
torch.onnx.export(flat,(imgs,*pms,dv,n2,n3),op,input_names=["imgs","pm1","pm2","pm3","dv","n2","n3"],
  output_names=KEYS,opset_version=17,do_constant_folding=True,dynamo=False)
import onnxruntime as ort
feed={"imgs":imgs.numpy(),"pm1":pms[0].numpy(),"pm2":pms[1].numpy(),"pm3":pms[2].numpy(),
      "dv":dv.numpy(),"n2":n2.numpy(),"n3":n3.numpy()}
res={}
for tag,eps in (("CPU",["CPUExecutionProvider"]),("WGPU",["WebGpuExecutionProvider","CPUExecutionProvider"])):
    s=ort.InferenceSession(op,providers=eps); want={i.name for i in s.get_inputs()}
    res[tag]=s.run(KEYS,{kk:v for kk,v in feed.items() if kk in want})
print(f"{'张量':<12}{'形状':>20}{'PyTorch p50':>13}{'WebGPU p50':>13}{'NaN%':>8}  判读")
bad=None
for i,k in enumerate(KEYS):
    r=ref[i].numpy(); w=res["WGPU"][i]
    nan=100*np.isnan(w).mean()
    wm=np.nanmedian(w) if not np.all(np.isnan(w)) else float('nan')
    ok=(nan==0 and np.allclose(r,w,rtol=3e-2,atol=1e-3))
    if not ok and bad is None: bad=k
    print(f"{k:<12}{str(tuple(r.shape)):>20}{np.median(r):13.5f}{wm:13.5f}{nan:7.1f}%  {'✅' if ok else ('🔴 首个坏' if bad==k else '🔴')}")
print(f"\n⇒ 第一个坏掉的张量:{bad}")
