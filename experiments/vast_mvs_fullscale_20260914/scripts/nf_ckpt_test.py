import sys, numpy as np
for n, t in (("int", int), ("float", float), ("bool", bool)):
    if not hasattr(np, n): setattr(np, n, t)
sys.path.insert(0, "/root/lf_probe/NeuralFusion")
import torch, os, functools
# torch>=2.6 defaults weights_only=True; these are the authors' own released .ckpt files
_orig_load = torch.load
torch.load = functools.partial(_orig_load, weights_only=False)
from training.pipeline import NeuralFusionPipeline

root = "/root/lf_probe/NeuralFusion/pretrained_models"
for exp in ["modelnet_outliers_99", "modelnet_outliers_95", "modelnet_outliers_9", "shapenet_noise_005"]:
    ep = os.path.join(root, exp, "version_0")
    ck = os.path.join(ep, "checkpoints", "best.ckpt")
    hp = os.path.join(ep, "hparams.yaml")
    if not os.path.isfile(ck):
        print(f"{exp}: MISSING {ck}"); continue
    try:
        pipe = NeuralFusionPipeline.load_from_checkpoint(checkpoint_path=ck, hparams_file=hp, strict=True)
        n = sum(p.numel() for p in pipe.parameters())
        print(f"{exp}: LOADED  params {n/1e6:.2f}M  modules {[k for k,_ in pipe.named_children()]}")
    except Exception as e:
        print(f"{exp}: FAILED {type(e).__name__}: {str(e)[:300]}")
