#!/bin/bash
# b 轮换并发: 只停官方调度器顶层进程, 在途任务(coarse/render)让它们自然跑完 —— 场景进程自己写 FINISH 标记
# (execute_tasks.py:362/374), 所以不丢活。全部收尾后: 崩溃场景移出 (官方同轮内本就不重试确定性失败; --use_existing
# 只认 FINISH, 不移会被重跑), 然后 b 用官方 --use_existing 续跑剩下的渲染, 同时 c 新开一轮 (并发 8, 尝试 540)。
set -u
LOG=/root/ig7_drain_resume.log
log(){ echo "[$(date +%F' '%T)] $*" >> $LOG; }
log "开始排空: 在途 generate_indoors $(pgrep -fc 'generate_[i]ndoors') 个"
while pgrep -f "generate_[i]ndoors" >/dev/null; do sleep 60; done
log "在途任务全部结束"
mkdir -p /root/ig7_official_b_crashed
for d in /root/ig7_official_b/*/; do
  s=$(basename $d)
  if [ ! -f $d/logs/FINISH_coarse ]; then
    why=$(grep -h -o '^[A-Za-z]*Error: .*' $d/logs/*.err 2>/dev/null | tail -1 | cut -c1-80)
    mv $d /root/ig7_official_b_crashed/$s && log "移出 coarse 未成场景 $s: ${why:-无报错信息}"
  fi
done
log "b 剩 $(ls -d /root/ig7_official_b/*/ | wc -l) 个场景 (全部 coarse 已成), 崩溃移出 $(ls /root/ig7_official_b_crashed | wc -l) 个"
cd /root
OUTF=/root/ig7_official_b nohup /root/ig7_official.sh --use_existing > /root/ig7_official_b_resume.log 2>&1 &
log "b 续跑已起 pid $!"
sleep 30
OUTF=/root/ig7_official_c NUM_SCENES=540 nohup /root/ig7_official.sh > /root/ig7_official_c.log 2>&1 &
log "c 新一轮已起 pid $! (尝试 540, 并发 8)"
