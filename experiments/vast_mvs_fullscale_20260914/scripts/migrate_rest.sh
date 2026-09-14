#!/bin/bash
# 旧机剩余素材 -> 新机: monotrain 里的 sp_scene_*(实目录)+符号链接、gso_mvs、AB ckpt; 传完逐文件 md5 对账
set -u
LOG=/root/migrate_rest.log; exec >> $LOG 2>&1
NEW="ssh -p 45434 -o StrictHostKeyChecking=no root@107.209.104.125"
E="ssh -p 45434 -o StrictHostKeyChecking=no"
echo "=== [$(date +%m-%d\ %H:%M)] 开始 ==="
echo "--- monotrain (sp_scene_* 实目录 + 符号链接) ---"
rsync -a --partial --info=progress2 --no-inc-recursive -e "$E" /root/monotrain/ root@107.209.104.125:/root/monotrain/ 2>&1 | tail -2
echo "--- [$(date +%H:%M)] md5 对账 monotrain (只对旧机有的文件) ---"
(cd /root/monotrain && find . -type f -print0 | sort -z | xargs -0 -P 16 -n 200 md5sum | sort -k2) > /root/md5_old_monotrain.txt
awk "{print \$2}" /root/md5_old_monotrain.txt > /root/md5_monotrain_files.txt
$NEW "cd /root/monotrain && xargs -P 16 -n 200 md5sum | sort -k2" < /root/md5_monotrain_files.txt > /root/md5_new_monotrain.txt
if cmp -s /root/md5_old_monotrain.txt /root/md5_new_monotrain.txt; then echo "[md5 OK] monotrain $(wc -l < /root/md5_old_monotrain.txt) 文件全一致"; else echo "*** [md5 MISMATCH] monotrain"; diff /root/md5_old_monotrain.txt /root/md5_new_monotrain.txt | head -5; fi
echo "--- [$(date +%H:%M)] gso_mvs ---"
rsync -a --partial --info=progress2 --no-inc-recursive -e "$E" /root/gso_mvs/ root@107.209.104.125:/root/gso_mvs/ 2>&1 | tail -2
(cd /root/gso_mvs && find . -type f -print0 | sort -z | xargs -0 -P 16 -n 200 md5sum | sort -k2) > /root/md5_old_gso.txt
$NEW "cd /root/gso_mvs && find . -type f -print0 | sort -z | xargs -0 -P 16 -n 200 md5sum | sort -k2" > /root/md5_new_gso.txt
if cmp -s /root/md5_old_gso.txt /root/md5_new_gso.txt; then echo "[md5 OK] gso_mvs $(wc -l < /root/md5_old_gso.txt) 文件全一致"; else echo "*** [md5 MISMATCH] gso_mvs"; fi
echo "--- AB ckpt + 日志 ---"
rsync -a -e "$E" /root/diffmvs/checkpoints/casdiff_AB/ root@107.209.104.125:/root/diffmvs/checkpoints/casdiff_AB/ && echo "AB ckpt ok"
echo "=== [$(date +%H:%M)] 全部搬完 ==="
