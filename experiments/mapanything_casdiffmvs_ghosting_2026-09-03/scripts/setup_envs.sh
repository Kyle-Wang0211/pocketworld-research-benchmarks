#!/bin/bash
set -x
cd /root/regionmerge

# ---------- Arm A: Murre (oracle only, ZJU non-commercial licence) ----------
/venv/main/bin/python -m venv /root/venv_murre
/root/venv_murre/bin/pip install -q --upgrade pip
/root/venv_murre/bin/pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu128
/root/venv_murre/bin/pip install -q "numpy==1.26.4" "opencv-python==4.8.0.76" tqdm "trimesh==4.0.2" \
    pillow matplotlib "scikit-learn==1.4.1.post1" "diffusers==0.27.2" "transformers==4.39.1" \
    "scipy==1.11.2" "huggingface_hub==0.25.0" "open3d==0.18.0" gdown
/root/venv_murre/bin/python -c "import torch,diffusers;print(\"MURRE_ENV_OK\",torch.__version__,torch.cuda.is_available(),diffusers.__version__)"

# Murre checkpoint from the official Google Drive link in README
mkdir -p /root/regionmerge/ckpt
/root/venv_murre/bin/gdown --fuzzy "https://drive.google.com/file/d/1gcThkgOQRmjAxhGJRV7SwzwXKBWP1cDa/view?usp=sharing" -O /root/regionmerge/ckpt/murre_ckpt.zip
ls -la /root/regionmerge/ckpt/

# ---------- Arm B: Prior-Depth-Anything (Apache-2.0, shippable) ----------
/venv/main/bin/python -m venv /root/venv_pda
/root/venv_pda/bin/pip install -q --upgrade pip
/root/venv_pda/bin/pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu128
/root/venv_pda/bin/pip install -q "numpy<2" einops pillow opencv-python safetensors matplotlib "huggingface_hub" transformers
TORCH_V=$(/root/venv_pda/bin/python -c "import torch;print(torch.__version__.split(\"+\")[0])")
/root/venv_pda/bin/pip install -q torch_cluster -f https://data.pyg.org/whl/torch-${TORCH_V}+cu128.html || /root/venv_pda/bin/pip install torch_cluster
/root/venv_pda/bin/python -c "import torch,torch_cluster;print(\"PDA_ENV_OK\",torch.__version__,torch.cuda.is_available())"
echo SETUP_DONE
