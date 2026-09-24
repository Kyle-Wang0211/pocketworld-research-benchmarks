#!/bin/bash
# TartanGround 批量:每条轨迹 下载→解压→转换→删原始,峰值磁盘 = 单条轨迹
# 用法: tg_batch.sh <plan.tsv>   每行: Env<TAB>Data_ver<TAB>Pnnnn
set -u
PLAN=$1
OUT=/root/tg_conv_v2
WD=/root/tg_work_v2
mkdir -p "$OUT" "$WD"
BASE="https://huggingface.co/datasets/theairlabcmu/TartanGround/resolve/main"
OK=0; FAIL=0
while IFS=$'\t' read -r ENV VER TRAJ; do
  [ -z "${ENV:-}" ] && continue
  SCAN="tg_${ENV}_${VER#Data_}_${TRAJ}"
  if [ -d "$OUT/$SCAN/cams" ] && [ -f "$OUT/$SCAN/cams/pair.txt" ]; then
    echo "[SKIP] $SCAN 已存在"; OK=$((OK+1)); continue
  fi
  D="$WD/$SCAN"; rm -rf "$D"; mkdir -p "$D"
  FETCH_OK=1
  for M in image_lcam_front depth_lcam_front metadata; do
    curl -sL --fail -o "$D/$M.zip" "$BASE/$ENV/$VER/$TRAJ/$M.zip" || { FETCH_OK=0; break; }
    unzip -oq "$D/$M.zip" -d "$D" || { FETCH_OK=0; break; }
    rm -f "$D/$M.zip"
  done
  if [ "$FETCH_OK" != "1" ]; then echo "[FAIL-FETCH] $SCAN"; rm -rf "$D"; FAIL=$((FAIL+1)); continue; fi
  DIFFMVS_DIR=/root/diffmvs /venv/main/bin/python /root/tartanground2mvsnet.py \
    --image_dir "$D/image_lcam_front" --depth_dir "$D/depth_lcam_front" \
    --pose_file "$D/pose_lcam_front.txt" --out_root "$OUT" --scan_name "$SCAN" \
    --keyframe_dist 0.1 --max_frames 0 --pair_rule dvmvs --num_src 10 --out_w 768 --out_h 576 \
    >> /root/tg_batch_conv_v2.log 2>&1
  RC=$?
  rm -rf "$D"
  if [ "$RC" = "0" ]; then echo "[OK] $SCAN  $(ls $OUT/$SCAN/blended_images 2>/dev/null | wc -l) 帧  剩余磁盘 $(df -h /root|tail -1|awk '{print $4}')"; OK=$((OK+1));
  else echo "[FAIL-CONV] $SCAN rc=$RC"; rm -rf "$OUT/$SCAN"; FAIL=$((FAIL+1)); fi
done < "$PLAN"
echo "BATCH_DONE ok=$OK fail=$FAIL"
