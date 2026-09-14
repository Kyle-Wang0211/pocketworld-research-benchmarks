#!/bin/bash
# 旧机剩余小件 -> 新机 /root/old_box_archive/ (逐目录 rsync + md5 对账); 不含已单独搬的大目录和可再生的 arm_*/arkit_pilot/sp_raw
set -u
LOG=/root/archive_rest.log; exec >> $LOG 2>&1
E="ssh -p 45434 -o StrictHostKeyChecking=no"; NEW="root@107.209.104.125"
DIRS="bins_B ckpt_park mvsanywhere mvsa_fork simpleproc_src colmap ig_venv blender arkit_blend out_official bins_sweep bins_fc bins_ma mvsa_nomono mvsa_out2 off_ens mvs_scene da3venv bins_nf bins_community bins_colmapdense ma_av cd_av hf lf_probe omni3d"
echo "=== [$(date +%m-%d\ %H:%M)] archive_rest 开始 ==="
$E $NEW "mkdir -p /root/old_box_archive/scripts"
# 脚本/日志/清单
rsync -a -e "$E" /root/*.sh /root/*.py /root/*.log /root/*.txt /root/*.json /root/*.md $NEW:/root/old_box_archive/scripts/ 2>/dev/null; echo "scripts+logs 同步 $(ls /root/*.sh /root/*.py /root/*.log /root/*.txt /root/*.json /root/*.md 2>/dev/null | wc -l) 个文件"
for d in $DIRS; do
  [ -e /root/$d ] || { echo "skip $d (不存在)"; continue; }
  rsync -a --partial -e "$E" /root/$d $NEW:/root/old_box_archive/ 2>&1 | tail -1
  (cd /root && find $d -type f -print0 | sort -z | xargs -0 -P 8 -n 200 md5sum | sort -k2) > /root/md5_old_$d.txt
  $E $NEW "cd /root/old_box_archive && find $d -type f -print0 | sort -z | xargs -0 -P 8 -n 200 md5sum | sort -k2" > /root/md5_new_$d.txt
  if cmp -s /root/md5_old_$d.txt /root/md5_new_$d.txt; then echo "[md5 OK] $d $(wc -l < /root/md5_old_$d.txt)"; else echo "*** [md5 MISMATCH] $d"; fi
done
echo "=== [$(date +%H:%M)] archive_rest 完成 ==="
