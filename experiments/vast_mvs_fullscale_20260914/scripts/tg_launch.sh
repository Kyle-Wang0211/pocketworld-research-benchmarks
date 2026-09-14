#!/bin/bash
# 单独的启动器,避免 pkill 自杀
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4
export TG_STRIDE=5 TG_MAXF=150
rm -rf /root/tg_work/*
cd /root
for i in 0 1 2 3 4 5 6 7; do
  nohup /root/tg_batch.sh /root/tg_plan_$i.tsv > /root/tg_shard_$i.log 2>&1 &
done
sleep 2
echo "launched $(pgrep -cf tg_batch.sh) shards"
