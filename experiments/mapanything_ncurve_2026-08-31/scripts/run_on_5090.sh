#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 在 5090 上跑 MapAnything 官方原版,产出「完全版」参照
# 用法:  bash run_on_5090.sh <132张图的目录>
# ─────────────────────────────────────────────────────────────
set -euo pipefail
IMGS="${1:?用法: bash run_on_5090.sh <图片目录>}"
OUT="${2:-mapanything_ref_$(date +%Y%m%d_%H%M)}"
mkdir -p "$OUT"

echo "== 环境 =="
python -c "import torch;print(f'torch {torch.__version__} cuda {torch.version.cuda} {torch.cuda.get_device_name(0)}')"
ls "$IMGS" | wc -l | xargs echo "输入图数:"

# ① 官方原版脚本,零修改。--apache 用 Apache-2.0 可商用权重(giant)
echo "== ① 官方 demo(网格 GLB) =="
python scripts/demo_images_only_inference.py \
    --image_folder "$IMGS" --apache --save_glb \
    --output_path "$OUT/official_mesh.glb"

# ② 同时导出可对照的中间量(体积小,便于回传比对)
echo "== ② 导出中间量供对照 =="
python - "$IMGS" "$OUT" <<'PY'
import sys, json, time, numpy as np, torch
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.geometry import depthmap_to_world_frame
imgs, out = sys.argv[1], sys.argv[2]
m = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda").eval()
views = load_images(imgs)
torch.cuda.reset_peak_memory_stats(); t = time.time()
with torch.inference_mode():                      # 与官方 demo 完全一致的参数
    outs = m.infer(views, memory_efficient_inference=True, minibatch_size=1,
                   use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)
torch.cuda.synchronize()
rec = {"views": len(views), "img_shape": list(views[0]["img"].shape),
       "inference_s": round(time.time()-t, 2),
       "peak_gib": round(torch.cuda.max_memory_allocated()/2**30, 2),
       "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0), "per_view": []}
D=[]; P=[]
for i, p in enumerate(outs):
    d = p["depth_z"][0].squeeze(-1)
    pts, valid = depthmap_to_world_frame(d, p["intrinsics"][0], p["camera_poses"][0])
    mk = p["mask"][0].squeeze(-1).bool() & valid.bool() & torch.isfinite(pts).all(-1)
    D.append(d.float().cpu().numpy()); P.append(pts[mk].float().cpu().numpy())
    if i < 5:
        rec["per_view"].append({"i": i, "depth_med": float(d.median()),
            "depth_p5": float(d.float().quantile(.05)), "depth_p95": float(d.float().quantile(.95)),
            "kept": int(mk.sum()), "K": p["intrinsics"][0].cpu().numpy().round(3).tolist(),
            "pose_t": p["camera_poses"][0][:3,3].cpu().numpy().round(4).tolist()})
X = np.concatenate(P)
lo, hi = np.percentile(X,5,axis=0), np.percentile(X,95,axis=0)
diag = float(np.linalg.norm(hi-lo)); Xn = X/diag
l2,h2 = np.percentile(Xn,5,axis=0), np.percentile(Xn,95,axis=0)
inb = ((Xn>=l2)&(Xn<=h2)).all(1)
rec["total_points"]  = int(len(X))
rec["p5p95_diag"]    = round(diag, 4)
rec["norm_density_M"]= round(float(inb.sum()/np.prod(h2-l2)/1e6), 2)   # 🔑 尺度归一,可跨机比
rec["depth_med_all"] = round(float(np.median(np.stack(D))), 4)
json.dump(rec, open(f"{out}/metrics.json","w"), indent=2, ensure_ascii=False)
np.save(f"{out}/depth_all.npy", np.stack(D).astype(np.float16))        # ~54MB,可回传
print(json.dumps({k:v for k,v in rec.items() if k!="per_view"}, indent=2))
PY

echo "== 产物 =="
ls -la "$OUT"
echo
echo "回传优先级: ① metrics.json(几KB,先传这个) ② depth_all.npy(~54MB) ③ official_mesh.glb(~900MB)"
