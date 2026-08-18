"""把 hidden_init[1] 每一步中间量都做成输出,定位坏在哪个通道/像素,并查量级。"""
import sys, os
from types import SimpleNamespace
import numpy as np, torch, onnxruntime as ort
REPO=os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0,REPO)
from models import CasDiffMVS
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/66e3ee10-aa1b-493d-be5b-b2015f30ea11/scratchpad"
D=os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/casdiffmvs_blendmvg_scratch_2026-08-16")
a=SimpleNamespace(method="casdiffmvs",numdepth_initial=48,numdepth=384,scale=[0.,0.125,0.025],
 sampling_timesteps=[0,1,1],ddim_eta=[0,1,1],timesteps=[1000]*3,stage_iters=[1,3,3],
 cost_dim_stage=[4,4,4],CostNum=[0,4,4],hidden_dim=[0,32,20],context_dim=[32,32,16],
 unet_dim=[0,16,8],min_radius=0.125,max_radius=8)
m=CasDiffMVS(a,test=True)
st=torch.load(f"{D}/ckpts/casdiffmvs_C_long_ep31.ckpt",map_location="cpu")
m.load_state_dict(st.get("model",st),strict=False); m.eval()
hi=m.hidden_init[1]
ctx=torch.from_numpy(np.load(f"{S}/ctx3.npy"))

class Inner(torch.nn.Module):
    def __init__(s,hi): super().__init__(); s.hi=hi
    def forward(s,c):
        h,_=torch.split(c,[20,16],dim=1)
        L0,L1,L2=s.hi[0],s.hi[1],s.hi[2]
        c0=L0.conv(h);  b0=L0.bn(c0);  r0=torch.relu(b0)
        c1=L1.conv(r0); b1=L1.bn(c1);  r1=torch.relu(b1)
        c2=L2(r1) if not hasattr(L2,'conv') else L2.conv(r1)
        return h,c0,b0,r0,c1,b1,r1,c2,torch.tanh(c2)
NAMES=["h","conv0","bn0","relu0","conv1","bn1","relu1","conv2","tanh"]
mod=Inner(hi).eval()
with torch.no_grad(): ref=[t.numpy() for t in mod(ctx)]
p=f"{S}/inner.onnx"
torch.onnx.export(mod,(ctx,),p,input_names=["x"],output_names=NAMES,
                  opset_version=17,do_constant_folding=True,dynamo=False)
res={}
for tag,eps in (("CPU",["CPUExecutionProvider"]),("WGPU",["WebGpuExecutionProvider","CPUExecutionProvider"])):
    res[tag]=ort.InferenceSession(p,providers=eps).run(NAMES,{"x":ctx.numpy()})
FP16MAX=65504.0
print(f"{'张量':<8}{'形状':>20}{'PyTorch |max|':>15}{'WebGPU 非有限%':>15}{'最大差':>12}")
first=None
for i,n in enumerate(NAMES):
    r=ref[i]; w=res["WGPU"][i]
    nf=100*(~np.isfinite(w)).mean()
    d=np.nanmax(np.abs(np.where(np.isfinite(w),w,np.nan)-r)) if nf<100 else float('inf')
    if (nf>0 or d>1e-3) and first is None: first=n
    flag="🔴" if (nf>0 or d>1e-3) else "✅"
    over = " ⚠️超fp16" if np.abs(r).max()>FP16MAX else ""
    print(f"{n:<8}{str(r.shape):>20}{np.abs(r).max():15.4f}{nf:14.3f}%{d:12.2e} {flag}{over}")
print(f"\n⇒ 第一个坏的中间量:{first}   (fp16 上限 {FP16MAX:.0f},所有中间量都远低于)")
i=NAMES.index(first); w=res["WGPU"][i]; r=ref[i]
bad=~np.isfinite(w)
print(f"\n══ {first} 的坏点分布 ══")
print(f"  坏点 {bad.sum()} / {bad.size}  ({100*bad.mean():.3f}%)")
ch=np.where(bad.any(axis=(0,2,3)))[0]
print(f"  涉及通道 {len(ch)}/{w.shape[1]}: {ch.tolist()[:20]}")
per=bad.sum(axis=(0,2,3))
print(f"  每通道坏点数: {[int(x) for x in per]}")
yy,xx=np.where(bad[0].any(axis=0))
if len(yy): print(f"  像素行范围 [{yy.min()},{yy.max()}] / {w.shape[2]}   列范围 [{xx.min()},{xx.max()}] / {w.shape[3]}")
print(f"  这些位置 PyTorch 的值: |max| {np.abs(r[bad]).max():.4f}  中位 {np.median(np.abs(r[bad])):.4f}")
print(f"  全张量 PyTorch |max| {np.abs(r).max():.4f}")
