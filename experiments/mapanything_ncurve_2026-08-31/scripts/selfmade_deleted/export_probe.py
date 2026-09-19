# [ONNX-PROBE 2026-08-31] 试探 MapAnything 能不能导出到 ONNX。
#
# 为什么现在做:这是「上端」三道关里唯一「不通就全盘皆输」的一关,
# 而且它**不需要真权重** —— 随机初始化的模型有完全相同的图与算子,
# 导出会不会炸在 scaled_dot_product_attention / 动态形状上,结论一模一样。
# (真权重还卡在学校 VPN 隧道上,4.7 GB 下不动。)
#
# 🔑 关键简化:因为我们要**分块**,K 是固定的(4)⇒ 静态形状导出,
#    自动绕开 pytorch#120075(MultiheadAttention + 动态形状导不出)。
#
# 🔑 用**同架构的小配置**试(dinov2 small + AAT 2 层):算子类型与大模型完全一致,
#    但内存只要几百 MB。上一轮把 18 GB 机器跑爆了,这次先小后大。
import argparse, json, os, resource, sys, threading, time
import torch, torch.nn as nn
from mapanything.models import MapAnything

ap = argparse.ArgumentParser()
ap.add_argument("--size", default="small", choices=["small","base","large","giant"])
ap.add_argument("--aat-depth", type=int, default=2)
ap.add_argument("--views", type=int, default=4, help="固定块大小 K")
ap.add_argument("--hw", type=int, nargs=2, default=[392,518])
ap.add_argument("--opset", type=int, default=17)
ap.add_argument("--mem-cap-gb", type=float, default=8.0, help="🔴 内存守卫:超过就自杀")
a = ap.parse_args()

# ── 内存守卫(上一轮教训:13.32 GB 上限我拿在手里却让它冲到 15.56) ──
def watchdog(cap_bytes):
    while True:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if rss > cap_bytes:
            print(f"\n🔴 内存守卫触发: RSS {rss/2**30:.1f} GiB > 上限 {cap_bytes/2**30:.1f} GiB,自杀",
                  flush=True)
            os._exit(9)
        time.sleep(0.5)
threading.Thread(target=watchdog, args=(a.mem_cap_gb*2**30,), daemon=True).start()

cfg = json.load(open("ma_config.json"))
cfg["encoder_config"]["torch_hub_pretrained"] = False
cfg["encoder_config"]["size"] = a.size
cfg["encoder_config"]["name"] = f"dinov2_{a.size}"
cfg["encoder_config"].pop("keep_first_n_layers", None)
DIM = {"small":384,"base":768,"large":1024,"giant":1536}[a.size]
ma = cfg["info_sharing_config"]["module_args"]
ma["depth"] = a.aat_depth
ma["dim"] = DIM; ma["input_embed_dim"] = DIM
ma["num_heads"] = max(1, DIM // 64)
# indices 是按原 depth=16 取的中间层([7,11]),缩 depth 时要按比例缩,否则越界
orig_depth = 16
ma["indices"] = sorted({max(0, min(a.aat_depth-1, round(i*a.aat_depth/orig_depth)))
                        for i in (7, 11)})
if len(ma["indices"]) < 2:            # DPT 头需要两个不同层级
    ma["indices"] = [0, max(1, a.aat_depth-1)][:2]
print(f"[cfg] AAT indices → {ma['indices']}", flush=True)
for k in ("cam_rot_encoder_config","cam_trans_encoder_config","depth_encoder_config",
          "ray_dirs_encoder_config","scale_encoder_config"):
    if k in cfg["geometric_input_config"]:
        cfg["geometric_input_config"][k]["enc_embed_dim"] = DIM

print(f"[cfg] encoder={a.size}(dim {DIM})  AAT depth={a.aat_depth}  K={a.views}  "
      f"HW={a.hw}  opset={a.opset}", flush=True)
model = MapAnything(**cfg).eval()
n = sum(p.numel() for p in model.parameters())
print(f"[cfg] 试探模型 {n/1e6:.1f} M 参数 ({n*4/2**20:.0f} MB)", flush=True)

NORM = cfg["encoder_config"]["data_norm_type"]
H, W = a.hw; K = a.views

class Wrap(nn.Module):
    """把 List[dict] 的接口包成纯张量进出,ONNX 才能追踪。"""
    def __init__(self, m): super().__init__(); self.m = m
    def forward(self, img, quats, trans, raydirs):
        views = [{"img": img[i:i+1], "data_norm_type": [NORM],
                  "camera_pose_quats": quats[i:i+1],
                  "camera_pose_trans": trans[i:i+1],
                  "ray_directions_cam": raydirs[i:i+1],
                  "is_metric_scale": torch.ones(1,1, dtype=torch.bool)} for i in range(K)]
        outs = self.m(views)
        return torch.cat([o["pts3d"] for o in outs], dim=0)

w = Wrap(model).eval()
img = torch.randn(K,3,H,W); quats = torch.randn(K,4); quats = quats/quats.norm(dim=-1,keepdim=True)
trans = torch.randn(K,3); raydirs = torch.randn(K,H,W,3)

print("[1/2] 先跑一次 eager 前向,确认包装正确 …", flush=True)
try:
    with torch.no_grad(): y = w(img, quats, trans, raydirs)
    print(f"      ✅ eager 通过,输出 {tuple(y.shape)}", flush=True)
except Exception as e:
    print(f"      ❌ eager 失败: {type(e).__name__}: {str(e)[:500]}", flush=True); sys.exit(1)

print(f"[2/2] torch.onnx.export (opset {a.opset},静态形状) …", flush=True)
t=time.time()
try:
    torch.onnx.export(w, (img,quats,trans,raydirs), f"probe_{a.size}_k{K}.onnx",
                      opset_version=a.opset, input_names=["img","quats","trans","raydirs"],
                      output_names=["pts3d"], dynamo=False)
    sz=os.path.getsize(f"probe_{a.size}_k{K}.onnx")/2**20
    print(f"      ✅ 导出成功 {time.time()-t:.1f}s  {sz:.1f} MB", flush=True)
except Exception as e:
    print(f"      ❌ 导出失败 ({time.time()-t:.1f}s): {type(e).__name__}", flush=True)
    print(f"      {str(e)[:1200]}", flush=True)
