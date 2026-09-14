#!/bin/bash
set -x
cd /root/lf_probe/dep_graphics && /root/venv_nf/bin/pip install -e . 2>&1 | tail -5
/root/venv_nf/bin/python - <<'PY'
import torch, pytorch_lightning as pl
from graphics import Voxelgrid
from graphics.voxelgrid import FeatureGrid
print("NF_ENV_OK", "torch", torch.__version__, "pl", pl.__version__, "cuda", torch.cuda.is_available())
PY
cd /root/lf_probe/NeuralFusion && /root/venv_nf/bin/python - <<'PY'
import sys; sys.path.insert(0, "/root/lf_probe/NeuralFusion")
from training.pipeline import NeuralFusionPipeline
print("PIPELINE_IMPORT_OK")
PY
echo NF_SETUP2_DONE
