#!/bin/bash
# 重建 val -> 只扫新进来的 scan -> 有坏就拉黑重来,直到 delta 全干净。
set -e
L=/root/MonoMVSNet/lists/ours
for round in 1 2 3 4 5 6; do
  cp $L/val_exact.txt /root/val_prev.txt
  /venv/main/bin/python /root/mk_val_exact.py > /root/mk_val_r$round.log 2>&1
  comm -13 <(sort /root/val_prev.txt) <(sort $L/val_exact.txt) > $L/_delta.txt
  D=$(wc -l < $L/_delta.txt)
  echo "[R$round] 新进来 $D 个 scan"
  if [ "$D" -eq 0 ]; then echo "[R$round] 收敛:无新 scan"; break; fi
  /venv/main/bin/python /root/scan_list.py lists/ours/_delta.txt > /root/scan_r$round.log 2>&1
  BAD=$(sed -n 's/^坏样本 \([0-9]*\) 组.*/\1/p' /root/scan_r$round.log)
  echo "[R$round] delta 坏样本 ${BAD:-0} 组"
  if [ "${BAD:-0}" = "0" ]; then echo "[R$round] ✅ delta 干净,val 定稿"; break; fi
  cat /root/bad_val_exact_scans.txt >> /root/bad_val_scans.txt
  sort -u /root/bad_val_scans.txt -o /root/bad_val_scans.txt
  echo "[R$round] 拉黑后黑名单 $(wc -l < /root/bad_val_scans.txt) 个"
done
echo "=== 最终 val ==="
tail -6 /root/mk_val_r*.log | tail -12
