#!/bin/bash
# 三个真实域 OLD -> NEW (直连 IP), 逐目录 rsync, 之后两边逐文件 md5 对账
set -u
LOG=/root/migrate_real.log; exec >> $LOG 2>&1
NEW="ssh -p 45434 -o StrictHostKeyChecking=no root@107.209.104.125"
R="rsync -a --partial --info=progress2 --no-inc-recursive -e \"ssh -p 45434 -o StrictHostKeyChecking=no\""
echo "=== [$(date +%m-%d\ %H:%M)] 开始 ==="
for d in tg_conv bmvs/data ta2/blendfmt; do
  echo "--- [$(date +%H:%M)] rsync $d ---"
  eval $R /root/$d/ root@107.209.104.125:/root/$d/ 2>&1 | tail -3
  echo "--- [$(date +%H:%M)] md5 对账 $d ---"
  (cd /root/$d && find . -type f -print0 | sort -z | xargs -0 -P 16 -n 200 md5sum | sort -k2) > /root/md5_old_${d//\//_}.txt
  $NEW "cd /root/$d && find . -type f -print0 | sort -z | xargs -0 -P 16 -n 200 md5sum | sort -k2" > /root/md5_new_${d//\//_}.txt
  NO=$(wc -l < /root/md5_old_${d//\//_}.txt); NN=$(wc -l < /root/md5_new_${d//\//_}.txt)
  if [ "$NO" = "$NN" ] && cmp -s /root/md5_old_${d//\//_}.txt /root/md5_new_${d//\//_}.txt; then echo "[md5 OK] $d $NO 文件全一致"; else echo "*** [md5 MISMATCH] $d old=$NO new=$NN"; diff /root/md5_old_${d//\//_}.txt /root/md5_new_${d//\//_}.txt | head -5; fi
done
echo "=== [$(date +%H:%M)] 三域搬运完成 ==="
