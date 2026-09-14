#!/bin/bash
set -x
/venv/main/bin/python -m venv --system-site-packages /root/venv_mvsa
/root/venv_mvsa/bin/pip install -q --upgrade pip
/root/venv_mvsa/bin/pip install -q kornia timm antialiased-cnns efficientnet_pytorch trimesh transforms3d einops lightning moviepy pypng scipy tqdm matplotlib
cd /root/mvsanywhere && /root/venv_mvsa/bin/pip install -q --no-deps -e .
mkdir -p /root/mvsanywhere/weights
cd /root/mvsanywhere/weights && curl -L -o mvsanywhere_hero.ckpt https://storage.googleapis.com/niantic-lon-static/research/mvsanywhere/mvsanywhere_hero.ckpt
ls -la /root/mvsanywhere/weights/
# arrange our data in the layout the README's "Custom data" section expects
mkdir -p /root/mvsa_data/scene0/colmap/sparse/0
ln -sfn /root/community/dense/images /root/mvsa_data/scene0/images
cp /root/community/dense/sparse/* /root/mvsa_data/scene0/colmap/sparse/0/
ls /root/mvsa_data/scene0/ /root/mvsa_data/scene0/colmap/sparse/0/
/root/venv_mvsa/bin/python -c "import mvsanywhere, torch; print('MVSA_IMPORT_OK', torch.__version__)"
echo MVSA_SETUP_DONE
