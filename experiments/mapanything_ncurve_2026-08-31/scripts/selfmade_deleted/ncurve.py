# [N-CURVE 2026-08-31] 量 MapAnything 的峰值显存与耗时随视图数 N 的变化。
#
# 目的:分离两条曲线
#   编码器  O(N)   —— 分块砍不动,这是手机上的地板
#   跨视图注意力 O(N²) —— 分块能砍
# 拟合 T(N) = a + b·N + c·N²,看 b(线性)与 c(二次)的相对大小。
#
# 输入用冻结场景 B28 的 132 张 PGM 转的 RGB JPEG(2000×1500)。
# ⚠️ 灰度转 RGB ⇒ **产物质量无意义**,但峰值显存与耗时只取决于分辨率与帧数,
#    与像素内容无关 ⇒ 性能曲线有效。
#
# 调用参数与 08-26 生产实验逐字一致:
#   memory_efficient_inference=True, minibatch_size=1, use_amp=True, amp_dtype="bf16"
import json, os, sys, threading, time
from pathlib import Path
import torch
from mapanything.models import MapAnything
from mapanything.utils.image import load_images

MODEL = os.environ.get("MA_MODEL", "facebook/map-anything-apache")
NS = [int(x) for x in os.environ.get("MA_NS", "1,2,4,8,12,16,24,32,48,64").split(",")]
dev = "mps" if torch.backends.mps.is_available() else "cpu"

print(f"[setup] device={dev}  model={MODEL}", flush=True)
print(f"[setup] mps recommended_max = {torch.mps.recommended_max_memory()/2**30:.2f} GB", flush=True)

# [绕过下载 2026-08-31] 学校 VPN 把全部流量绕道纽约,4.7 GB 权重下不动。
# 但**显存与耗时只取决于架构,不取决于权重数值** ⇒ 随机初始化给出的曲线
# 与加载真权重完全一致(官方剖析脚本 profile_memory_runtime.py:344 本身
# 就用 torch.rand 造输入,同一个道理)。
# torch_hub_pretrained=False 关掉 DINOv2 的预训练下载,只要架构。
# ⚠️ 因此本轮**只测性能,不看产物质量**。
import json as _json
t0 = time.time()
_cfg = _json.load(open(os.environ.get("MA_CFG","ma_config.json")))
_cfg["encoder_config"]["torch_hub_pretrained"] = False
model = MapAnything(**_cfg).to(dev).eval()
load_s = time.time() - t0
nparam = sum(p.numel() for p in model.parameters())
print(f"[setup] 加载 {load_s:.1f}s  参数量 {nparam/1e6:.0f} M "
      f"({nparam*4/2**20:.0f} MB @fp32)", flush=True)

all_views = load_images("images")
print(f"[setup] 载入 {len(all_views)} 视图；预处理后 shape="
      f"{tuple(all_views[0]['img'].shape)}", flush=True)

class Peak(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.stop=False; self.peak=0
    def run(self):
        while not self.stop:
            self.peak = max(self.peak, torch.mps.driver_allocated_memory())
            time.sleep(0.02)

results = []
for n in NS:
    if n > len(all_views): continue
    torch.mps.empty_cache()
    time.sleep(1.0)
    base = torch.mps.driver_allocated_memory()
    views = all_views[:n]
    p = Peak(); p.start()
    t = time.time(); err = None
    try:
        with torch.inference_mode():
            model.infer(views, memory_efficient_inference=True, minibatch_size=1,
                        use_amp=True, amp_dtype="bf16",
                        apply_mask=True, mask_edges=True)
        torch.mps.synchronize()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:200]
    dt = time.time() - t
    p.stop = True; p.join()
    row = {"N": n, "seconds": round(dt,3),
           "peak_gib": round(p.peak/2**30,3),
           "base_gib": round(base/2**30,3),
           "delta_gib": round((p.peak-base)/2**30,3), "error": err}
    results.append(row)
    print(f"[N={n:3d}] {dt:8.2f}s  峰值 {p.peak/2**30:6.2f} GiB  "
          f"(增量 {(p.peak-base)/2**30:5.2f})  {err or '✓'}", flush=True)
    if err: break

out = {"model": MODEL, "device": dev, "params_millions": round(nparam/1e6,1),
       "model_load_seconds": round(load_s,1),
       "image_shape": list(all_views[0]["img"].shape),
       "mps_recommended_max_gib": round(torch.mps.recommended_max_memory()/2**30,2),
       "torch": torch.__version__, "results": results}
Path("ncurve_result.json").write_text(json.dumps(out, indent=2))
print("\n=== 拟合 ===", flush=True)
ok = [r for r in results if not r["error"]]
if len(ok) >= 3:
    import itertools
    xs=[r["N"] for r in ok]; ts=[r["seconds"] for r in ok]; ms=[r["peak_gib"] for r in ok]
    # 最小二乘 T = a + b N + c N^2
    import numpy as np
    A=np.vstack([np.ones(len(xs)), xs, np.square(xs)]).T
    for name, ys in (("耗时(s)", ts), ("峰值(GiB)", ms)):
        c=np.linalg.lstsq(A, np.array(ys), rcond=None)[0]
        print(f"  {name:12s} = {c[0]:8.3f} + {c[1]:8.4f}·N + {c[2]:9.5f}·N²")
