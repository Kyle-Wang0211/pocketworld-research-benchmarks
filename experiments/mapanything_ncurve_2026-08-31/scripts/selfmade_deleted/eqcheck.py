import json, os, torch
from mapanything.models import MapAnything
def build():
    cfg=json.load(open("ma_config.json"))
    cfg["encoder_config"]["torch_hub_pretrained"]=False
    cfg["encoder_config"]["size"]="small"; cfg["encoder_config"]["name"]="dinov2_small"
    cfg["encoder_config"].pop("keep_first_n_layers",None)
    D=384; ma=cfg["info_sharing_config"]["module_args"]
    ma["depth"]=4; ma["dim"]=D; ma["input_embed_dim"]=D; ma["num_heads"]=6; ma["indices"]=[2,3]
    for k in ("cam_rot_encoder_config","cam_trans_encoder_config","depth_encoder_config",
              "ray_dirs_encoder_config","scale_encoder_config"):
        cfg["geometric_input_config"][k]["enc_embed_dim"]=D
    return cfg
torch.manual_seed(7)
cfg=build(); m=MapAnything(**cfg).eval()
NORM=cfg["encoder_config"]["data_norm_type"]; H,W,K=224,308,2
torch.manual_seed(11)
img=torch.randn(K,3,H,W); q=torch.randn(K,4); q=q/q.norm(dim=-1,keepdim=True)
t=torch.randn(K,3); rd=torch.randn(K,H,W,3)
def views():
    return [{"img":img[i:i+1],"data_norm_type":[NORM],"camera_pose_quats":q[i:i+1],
             "camera_pose_trans":t[i:i+1],"ray_directions_cam":rd[i:i+1],
             "is_metric_scale":torch.ones(1,1,dtype=torch.bool)} for i in range(K)]
import mapanything.models.mapanything.model as MM
outs={}
for flag in (False, True):
    MM.MAPANYTHING_STATIC_GEOM = flag
    with torch.no_grad(): o=m(views())
    outs[flag]=torch.cat([x["pts3d"] for x in o],0).clone()
a,b=outs[False],outs[True]
print(f"  开关关: {tuple(a.shape)}   开关开: {tuple(b.shape)}")
print(f"  逐元素完全相同: {torch.equal(a,b)}")
print(f"  最大绝对差    : {(a-b).abs().max().item():.6e}")
