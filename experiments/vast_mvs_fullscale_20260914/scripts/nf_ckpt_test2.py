import sys, numpy as np, functools
for n, t in (("int", int), ("float", float), ("bool", bool)):
    if not hasattr(np, n): setattr(np, n, t)
sys.path.insert(0, "/root/lf_probe/NeuralFusion")
import torch, os
_orig = torch.load
torch.load = functools.partial(_orig, weights_only=False)   # authors' own released .ckpt
from training.pipeline import NeuralFusionPipeline
from utils.loading import load_config_from_json

root = "/root/lf_probe/NeuralFusion/pretrained_models"
for exp in ["modelnet_outliers_99", "modelnet_outliers_95", "modelnet_outliers_9", "shapenet_noise_005"]:
    ep = os.path.join(root, exp, "version_0")
    ck = os.path.join(ep, "checkpoints", "best.ckpt")
    try:
        cfg = load_config_from_json(ep)
        pipe = NeuralFusionPipeline(cfg)
        sd = torch.load(ck, map_location="cpu")["state_dict"]
        missing, unexpected = pipe.load_state_dict(sd, strict=False)
        n = sum(p.numel() for p in pipe.parameters())
        print(f"{exp}: LOADED params {n/1e6:.3f}M  missing {len(missing)} unexpected {len(unexpected)}")
        if len(missing): print("   missing[:5]", missing[:5])
        if len(unexpected): print("   unexpected[:5]", unexpected[:5])
        print("   children", [k for k, _ in pipe.named_children()])
        print("   DATA.grid_resolution", cfg.DATA.get("grid_resolution"), "resx/resy", cfg.DATA.get("resx"), cfg.DATA.get("resy"))
    except Exception as e:
        import traceback; print(f"{exp}: FAILED {type(e).__name__}: {str(e)[:300]}")
