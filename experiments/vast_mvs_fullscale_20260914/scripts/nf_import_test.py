import sys, numpy as np
# 2021-era code on numpy 2: restore the aliases removed in numpy 1.24/2.0
for name, target in (("int", int), ("float", float), ("bool", bool), ("object", object), ("str", str)):
    if not hasattr(np, name): setattr(np, name, target)
sys.path.insert(0, "/root/lf_probe/NeuralFusion")
from training.pipeline import NeuralFusionPipeline
import torch
print("PIPELINE_IMPORT_OK torch", torch.__version__, "cuda", torch.cuda.is_available())
