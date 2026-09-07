#!/usr/bin/env bash
# Arm B per RENTED_MACHINE_RUNBOOK.md §6.5/§7: waits for BlendedMVG extraction (POST_DONE) and for the TG upload
# to be complete, applies the depth-range retighten (decision #1 = yes, recorded), builds the 10/20/40% mixed lists,
# runs the 200-step calibration under a timeout, then the real 4-epoch fine-tune (TG 20%). No predecode cache:
# 62 GB RAM cannot hold the full BlendedMVG cache, so the official blend loader with NUM_WORKERS=24 is used.
set -uo pipefail
export PATH=/root/venv-diffmvs/bin:$PATH
P=/data/finetune_pack; PY=/venv/main/bin/python
echo "[$(date)] waiting for POST_DONE"
until grep -q POST_DONE /data/post_download.log 2>/dev/null; do grep -q -E "ARCHIVES_INCOMPLETE|MERGE_FAILED|UNZIP_FAILED" /data/post_download.log 2>/dev/null && { echo "download stage failed"; exit 1; }; sleep 120; done
echo "[$(date)] waiting for TG upload (1776 jpg / 1776 pfm / 23 meta, no rsync temp files)"
while :; do
  J=$(ls $P/tg_mvs/*/blended_images/*.jpg 2>/dev/null | wc -l); D=$(ls $P/tg_mvs/*/rendered_depth_maps/*.pfm 2>/dev/null | wc -l)
  M=$(ls $P/tg_mvs/*/conversion_meta.json 2>/dev/null | wc -l); T=$(find $P/tg_mvs -name ".*" -type f | wc -l)
  [ "$J" = 1776 ] && [ "$D" = 1776 ] && [ "$M" = 23 ] && [ "$T" = 0 ] && break
  sleep 120
done
echo "[$(date)] TG complete: jpg=$J pfm=$D meta=$M"
echo "[$(date)] decision #1: retighten TG depth range to p95 (runbook §6.5, applied to the only trained arm)"
$PY $P/retighten_depth_range.py --root $P/tg_mvs --hi 95 2>&1 | tail -5
[ -f /data/lists/train.txt ] || { echo "no /data/lists/train.txt"; exit 1; }
for r in 0.1 0.2 0.4; do
  $PY $P/make_mixed_list.py --mvg_root /data/BlendedMVG --mvg_list /data/lists/train.txt --mvg_val /data/lists/val.txt \
     --tg_root $P/tg_mvs --tg_list $P/tg_mvs/lists_all_scans.txt --ratio $r --trainviews 9 \
     --out_root /data/mixed --out_lists /data/mixed_lists 2>&1 | tail -3
done
ls /data/mixed_lists; cat /data/mixed_lists/mix_tg20.json 2>/dev/null
echo "[$(date)] calib (200 steps, timeout 480 s)"
cd $P
DIFFMVS_DIR=/root/diffmvs MIX_ROOT=/data/mixed TRAINLIST=/data/mixed_lists/train_tg20.txt VALLIST=/data/mixed_lists/val.txt \
LOADCKPT=/data/casdiffmvs_mvgZeroDTU.ckpt OUT_ROOT=/data/runs_tgmix NUM_WORKERS=24 EPOCHS=4 \
  timeout 480 bash $P/finetune_tgmix.sh calib > /data/calib_console.log 2>&1
grep -h "metas:" /data/runs_tgmix/calib_*/calib.log | head -2
grep -h "time=" /data/runs_tgmix/calib_*/calib.log | tail -3
nvidia-smi --query-gpu=memory.used --format=csv,noheader
sleep 10
echo "[$(date)] ARM B run: TG 20%, 4 epochs"
DIFFMVS_DIR=/root/diffmvs MIX_ROOT=/data/mixed TRAINLIST=/data/mixed_lists/train_tg20.txt VALLIST=/data/mixed_lists/val.txt \
LOADCKPT=/data/casdiffmvs_mvgZeroDTU.ckpt OUT_ROOT=/data/runs_tgmix NUM_WORKERS=24 EPOCHS=4 \
  bash $P/finetune_tgmix.sh run > /data/armB_console.log 2>&1
echo "[$(date)] ARM_B_DONE rc=$?"; ls -la /data/runs_tgmix/train_tg20/*.ckpt 2>/dev/null
