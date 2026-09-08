#!/bin/bash
set -x
/root/venv_murre/bin/pip install -q "numpy==1.26.4" "opencv-python" tqdm "trimesh==4.0.2" pillow matplotlib \
  "scikit-learn" "diffusers==0.27.2" "transformers==4.39.1" "scipy" "huggingface_hub==0.25.0" open3d gdown
/root/venv_murre/bin/python -c "import torch,diffusers,transformers;print(\"MURRE_ENV_OK\",torch.__version__,torch.cuda.is_available(),diffusers.__version__,transformers.__version__)"
mkdir -p /root/regionmerge/ckpt
/root/venv_murre/bin/gdown --fuzzy "https://drive.google.com/file/d/1gcThkgOQRmjAxhGJRV7SwzwXKBWP1cDa/view?usp=sharing" -O /root/regionmerge/ckpt/murre_ckpt.zip
ls -la /root/regionmerge/ckpt/
echo MURRE_SETUP_DONE
