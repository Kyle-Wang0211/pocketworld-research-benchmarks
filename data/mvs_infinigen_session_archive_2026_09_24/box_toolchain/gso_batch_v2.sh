#!/bin/bash
# GSO 批量:每模型 下载→修贴图→渲染(bpy/OptiX,两道自证)→转MVSNet格式→删原始
# 断点续跑:已有 pair.txt 的直接跳过
set -u
LIST=$1
OUT=/root/gso_mvs_v2
WD=/root/gso_work_v2
NV=${GSO_NV:-49}
SAMPLES=${GSO_SAMPLES:-128}
mkdir -p "$OUT" "$WD"
OK=0; FAIL=0
while read -r M; do
  [ -z "${M:-}" ] && continue
  SCAN="gso_${M}"
  [ -f "$OUT/$SCAN/cams/pair.txt" ] && { OK=$((OK+1)); continue; }
  mkdir "$WD/lock_$M" 2>/dev/null || continue     # 原子认领, 别的工人正在做就跳过
  D="$WD/$M"; rm -rf "$D"; mkdir -p "$D"
  U="https://fuel.gazebosim.org/1.0/GoogleResearch/models/$M/1/$M.zip"
  curl -sL --fail --max-time 240 -o "$D/m.zip" "$U" || { echo "[FAIL-DL] $M"; rm -rf "$D"; FAIL=$((FAIL+1)); continue; }
  unzip -oq "$D/m.zip" -d "$D/model" 2>/dev/null || { echo "[FAIL-UNZIP] $M"; rm -rf "$D"; FAIL=$((FAIL+1)); continue; }
  rm -f "$D/m.zip"
  [ -f "$D/model/meshes/model.obj" ] || { echo "[FAIL-NOOBJ] $M"; rm -rf "$D"; FAIL=$((FAIL+1)); continue; }
  if ! /root/ig_venv/bin/python /root/gso_stage1_v2.py "$D/model" "$OUT" "$SCAN" "$NV" "$SAMPLES" >> /root/gso_conv_v2.log 2>&1; then
    echo "[FAIL-RENDER] $M"; rm -rf "$D" "$OUT/$SCAN"; FAIL=$((FAIL+1)); continue; fi
  if ! /venv/main/bin/python /root/gso_stage2_v2.py "$OUT" "$SCAN" >> /root/gso_conv_v2.log 2>&1; then
    echo "[FAIL-CONV] $M"; rm -rf "$D" "$OUT/$SCAN"; FAIL=$((FAIL+1)); continue; fi
  rm -rf "$D"; OK=$((OK+1))
  echo "[OK] $SCAN $(ls $OUT/$SCAN/blended_images 2>/dev/null|wc -l)视角 磁盘$(df -h /root|tail -1|awk '{print $4}')"
done < "$LIST"
echo "GSO_BATCH_DONE ok=$OK fail=$FAIL"
