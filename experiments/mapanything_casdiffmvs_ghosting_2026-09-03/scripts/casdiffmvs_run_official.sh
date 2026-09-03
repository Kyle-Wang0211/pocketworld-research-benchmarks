#!/usr/bin/env bash
# Official CasDiffMVS (cvg/diffmvs upstream cd10d5c) on the 132-frame room, production COLMAP cameras,
# user-signed OFFICIAL real-scene config: 768x576, num_view=10, numdepth 48/384, scale 0/0.125/0.025,
# stage_iters 1 3 3, fusion photo [0.3,0.5,0.5], geo_mask>=3, geo_pixel 1.0, geo_depth 0.01, depth averaging (filter.py).
set -euo pipefail
CKPT_TAG="$1"          # blendmvg | dtu
ROOT=/root/casdiffmvs_official_20260903
OUT=$ROOT/out_${CKPT_TAG}_768x576_nv10
mkdir -p "$OUT"
cd $ROOT/diffmvs_upstream
git rev-parse HEAD > "$OUT/upstream_commit.txt"
sha256sum $ROOT/casdiffmvs_${CKPT_TAG}.ckpt > "$OUT/ckpt.sha256"
( cd $ROOT/mvs_P16k && find images cams pair.txt -type f -print0 | sort -z | xargs -0 sha256sum ) > "$OUT/input.sha256"
/usr/bin/time -v /root/venv-diffmvs/bin/python test.py --dataset=general --batch_size=1 --num_view=10 --method=casdiffmvs --save_depth \
  --testpath=$ROOT/mvs_P16k --outdir="$OUT" --loadckpt=$ROOT/casdiffmvs_${CKPT_TAG}.ckpt \
  --numdepth_initial=48 --numdepth=384 --max_h=576 --max_w=768 \
  --scale 0.0 0.125 0.025 --sampling_timesteps 0 1 1 --ddim_eta 0 1 1 \
  --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
  --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
  --min_radius 0.125 --max_radius 8 \
  --photo_thres 0.3 0.5 0.5 --geo_mask_thres 3 --geo_pixel_thres 1.0 --geo_depth_thres 0.01
ls -la "$OUT"/pc.ply && sha256sum "$OUT"/pc.ply > "$OUT/pc.ply.sha256"
echo RUN_DONE
