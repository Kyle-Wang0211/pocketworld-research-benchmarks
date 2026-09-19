# [等价性 2026-08-31] 编码缓存开/关必须逐位相同。
# 依据:编码器输入只有 (image, data_norm_type),与位姿、与块内其它视图无关
#      ⇒ 同一视图在任何块里的编码输出逐位相同。这是结构性等价,不是近似。
import json, os, time, threading, resource, torch
os.environ["MAPANYTHING_STATIC_GEOM"]="1"
from mapanything.models import MapAnything
from chunked_stream import CachingEncoder
def guard(cap):
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>cap:
            print("🔴 内存守卫,自杀",flush=True); os._exit(9)
        time.sleep(0.5)
threading.Thread(target=guard,args=(10*2**30,),daemon=True).start()

cfg=json.load(open("ma_config.json")); cfg["encoder_config"]["torch_hub_pretrained"]=False
cfg["encoder_config"]["size"]="small"; cfg["encoder_config"]["name"]="dinov2_small"
cfg["encoder_config"].pop("keep_first_n_layers",None)
D=384; ma=cfg["info_sharing_config"]["module_args"]
ma["depth"]=4; ma["dim"]=D; ma["input_embed_dim"]=D; ma["num_heads"]=6; ma["indices"]=[2,3]
for k in ("cam_rot_encoder_config","cam_trans_encoder_config","depth_encoder_config",
          "ray_dirs_encoder_config","scale_encoder_config"):
    cfg["geometric_input_config"][k]["enc_embed_dim"]=D
torch.manual_seed(3)
m=MapAnything(**cfg).eval()
NORM=cfg["encoder_config"]["data_norm_type"]; H,W=224,308
torch.manual_seed(5)
N=6
IMG=torch.randn(N,3,H,W); Q=torch.randn(N,4); Q=Q/Q.norm(dim=-1,keepdim=True); T=torch.randn(N,3)
def views(idxs):
    return [{"img":IMG[i:i+1],"data_norm_type":[NORM],"camera_pose_quats":Q[i:i+1],
             "camera_pose_trans":T[i:i+1],
             "is_metric_scale":torch.ones(1,1,dtype=torch.bool)} for i in idxs]
# 块划分:K=4 overlap=2 ⇒ [0,1,2,3] [2,3,4,5] —— 视图 2,3 重复出现
CH=[[0,1,2,3],[2,3,4,5]]
def run(use_cache):
    enc0=m.encoder
    ce=None
    if use_cache:
        ce=CachingEncoder(enc0).eval(); m.encoder=ce
    outs=[]
    for c in CH:
        if ce is not None: ce.keys=list(c)
        with torch.inference_mode():
            o=m(views(c), memory_efficient_inference=True, minibatch_size=1)
        outs.append(torch.cat([x["pts3d"] for x in o],0).clone())
    m.encoder=enc0
    return outs, (ce.hits if ce else 0, ce.misses if ce else 0)
a,_    = run(False)
b,(h,ms)= run(True)
print(f"  块划分 {CH}  (视图 2,3 出现在两个块里)")
print(f"  缓存统计: 命中 {h} / 未命中 {ms}   ⇒ 省下 {h}/{h+ms} 次视图编码")
ok=all(torch.equal(x,y) for x,y in zip(a,b))
print(f"  逐位完全相同: {ok}")
for i,(x,y) in enumerate(zip(a,b)):
    print(f"    块{i} 最大绝对差 {(x-y).abs().max().item():.3e}")
