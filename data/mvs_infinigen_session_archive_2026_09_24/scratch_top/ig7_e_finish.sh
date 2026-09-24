#!/bin/bash
# 等 e 轮剩下的孤儿任务跑完 (上限 4 小时; 3h 超时看门狗会先处理 coarse), 然后把没法续的场景挪开, 用新配置续跑 c 的渲染。
LOG=/root/ig7_e_finish.log; log(){ echo "[$(date +%F' '%T)] $*" >> $LOG; }
T0=$(date +%s)
log "开始等 e 轮孤儿任务: $(ps -eo args | grep -c 'generate_[i]ndoors.*/root/ig7_official_e/') 个"
while ps -eo args | grep -q "generate_[i]ndoors.*/root/ig7_official_e/"; do
  if [ $(( $(date +%s)-T0 )) -gt 14400 ]; then log "等待超 4h, 不再等"; break; fi
  sleep 60
done
log "e 孤儿任务结束 (或超时)"
mkdir -p /root/ig7_official_e_crashed /root/ig7_official_e_partial
for d in /root/ig7_official_e/*/; do
  s=$(basename $d)
  if [ ! -f $d/logs/FINISH_coarse ]; then mv $d /root/ig7_official_e_crashed/ && log "coarse 未成, 移出 $s"; continue; fi
  i=$(ls $d/frames/Image/*/Image_*.png 2>/dev/null | wc -l); g=$(ls $d/frames/Depth/*/Depth_*.npy 2>/dev/null | wc -l)
  if { [ $i -lt 30 ] || [ $g -lt 30 ]; } && [ ! -f $d/coarse/scene.blend ]; then mv $d /root/ig7_official_e_partial/ && log "帧不全且场景文件已被清理 (彩图 $i 深度 $g), 移出 $s"; fi
done
log "e 剩 $(ls -d /root/ig7_official_e/*/ | wc -l) 个场景, 用新配置 --use_existing 续跑"
cd /root; EXTRA_CFG=fast_solve.gin OUTF=/root/ig7_official_e nohup /root/ig7_official.sh --use_existing > /root/ig7_official_e_resume.log 2>&1 &
log "e 续跑 pid $!"
