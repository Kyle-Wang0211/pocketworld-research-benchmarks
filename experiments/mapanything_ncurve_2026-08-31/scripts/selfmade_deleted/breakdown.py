# [BREAKDOWN 2026-08-31] 拆开单次前向的耗时:编码器 O(N) vs 其余(跨视图注意力+预测头)。
# 为什么重要:分块只砍得动注意力的 O(N²),**砍不动编码器的 O(N)**。
# 若编码器占大头,分块调到天上也就那样,得从别处想办法。
# 用随机权重(耗时只取决于架构),带内存守卫(上次 N=64 把机器跑爆的教训)。
import json, os, time, threading, resource, torch
from mapanything.models import MapAnything
def guard(cap):
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > cap:
            print("🔴 内存守卫触发,自杀", flush=True); os._exit(9)
        time.sleep(0.5)
threading.Thread(target=guard, args=(10*2**30,), daemon=True).start()

cfg=json.load(open(os.environ.get("MA_CFG","ma_config.json")))
cfg["encoder_config"]["torch_hub_pretrained"]=False
dev="mps"; m=MapAnything(**cfg).to(dev).eval()
NORM=cfg["encoder_config"]["data_norm_type"]; H,W=392,518
os.environ["MAPANYTHING_STATIC_GEOM"]="1"

def mk(k):
    q=torch.randn(k,4,device=dev); q=q/q.norm(dim=-1,keepdim=True)
    return [{"img":torch.randn(1,3,H,W,device=dev),"data_norm_type":[NORM],
             "camera_pose_quats":q[i:i+1],"camera_pose_trans":torch.randn(1,3,device=dev),
             "is_metric_scale":torch.ones(1,1,dtype=torch.bool,device=dev)} for i in range(k)]

def timeit(fn, n=3):
    fn(); torch.mps.synchronize(); t=time.time()
    for _ in range(n): fn()
    torch.mps.synchronize(); return (time.time()-t)/n

from uniception.models.encoders import ViTEncoderInput
print(f"{'K':>3} {'编码器':>9} {'完整':>9} {'其余':>9} {'编码器占比':>10}", flush=True)
for K in (2,4,8,16):
    imgs=torch.randn(K,3,H,W,device=dev)
    def enc():
        with torch.inference_mode(), torch.autocast("mps", dtype=torch.float16):
            m.encoder(ViTEncoderInput(image=imgs, data_norm_type=NORM))
    v=mk(K)
    def full():
        with torch.inference_mode(), torch.autocast("mps", dtype=torch.float16):
            m(v, memory_efficient_inference=True, minibatch_size=1)
    try:
        te=timeit(enc); tf=timeit(full)
        print(f"{K:>3} {te:>8.3f}s {tf:>8.3f}s {tf-te:>8.3f}s {te/tf*100:>9.0f}%", flush=True)
    except Exception as e:
        print(f"{K:>3}  ❌ {type(e).__name__}: {str(e)[:120]}", flush=True); break
    torch.mps.empty_cache()
