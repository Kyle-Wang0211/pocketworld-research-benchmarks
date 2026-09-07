#!/usr/bin/env bash
# Official CasDiffMVS inference + official fusion on the 132-image scene, byte-for-byte the 09-03 recipe
# (run_1536.sh with the 768x576 default size), parameterised only by checkpoint / output dir / size.
#   bash run_official_ckpt.sh <ckpt> <outdir> [max_h max_w]
set -euo pipefail
CKPT=${1:?ckpt}; OUT=${2:?outdir}; MH=${3:-576}; MW=${4:-768}
mkdir -p "$OUT"
cd /root/casdiffmvs_official_20260903/diffmvs_upstream
git rev-parse HEAD > "$OUT/upstream_commit.txt"; sha256sum "$CKPT" > "$OUT/ckpt.sha256"
/usr/bin/time -v /root/venv-diffmvs/bin/python test.py --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
  --testpath=/root/casdiffmvs_official_20260903/mvs_P16k --outdir="$OUT" --loadckpt="$CKPT" \
  --numdepth_initial=48 --numdepth=384 --max_h="$MH" --max_w="$MW" \
  --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
  --min_radius 0.125 --max_radius 8 \
  --photo_thres 0.3 0.5 0.5 --geo_mask_thres 3 --geo_pixel_thres 1.0 --geo_depth_thres 0.01
ls -la "$OUT/pc.ply" && sha256sum "$OUT/pc.ply" > "$OUT/pc.ply.sha256"
echo RUN_DONE
