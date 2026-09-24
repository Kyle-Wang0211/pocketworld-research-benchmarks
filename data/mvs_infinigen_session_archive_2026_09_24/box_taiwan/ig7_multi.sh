#!/bin/bash
# 台湾 16×5090 箱: 每张卡起一路 /root/ig7_render.sh run, 各渲一段 seed。
# 钉卡照抄 Infinigen 官方本地调度 datagen/util/submitit_emulator.py:107 —— 每个 job 设自己的 CUDA_VISIBLE_DEVICES。
# (同卡多路 PAR>1 实测负收益, 那是另一回事: 这里每路独占一张卡。)
# 分工: 旧箱 107.209.104.125 渲 100000..100011 (由它的 /root/ig7_cutoff.sh 截停);
#       本箱渲 100012..100299 = 288 间 = 16 路 x 18 间。
# 参数与旧箱完全一致: 768x576 / 30 机位 / 8192+去噪 / PAR=1 / 成品 /root/ig7_blend/ig_<seed>
#
# v2 (09-23 10:26 UTC): v1 首轮 16 路每个进程都按 384 核开线程 (nlwp 1075-1214/进程, load 868),
#   seed 100138 coarse 死于 "libgomp: Thread creation failed: Resource temporarily unavailable"。
#   🔴 根因未定: pids.events=max 0 (pids 上限从未触发) / max_map_count 实测 ~4k 远低于 65530 => 两个常见原因都不是。
#   v2 实测: coarse 每进程线程 ~1100 -> 434, load 868 -> 133 (缓解, 不是根治); 剩余线程无视亲和掩码, 来源未查明。
#   Infinigen 源码没有官方限线程设置 (唯一一处 threads_mode 在 trees/utils/helper.py:60 被注释掉)。
#   => 每路 taskset 划 12 物理核 + 其超线程 (24 逻辑 CPU), 且落在该 GPU 所在 NUMA 节点
#      (nvidia-smi topo: GPU0-7 -> NUMA0 = 0-95,192-287; GPU8-15 -> NUMA1 = 96-191,288-383);
#      libgomp / oneTBB / OpenBLAS 默认线程数都按亲和掩码算, 再用 *_NUM_THREADS 兜底。
BASE=100012; PER=18; NGPU=16; NT=12
for i in $(seq 0 $((NGPU-1))); do
  s0=$((BASE+PER*i))
  if [ $i -lt 8 ]; then j=$i; P0=0; H0=192; else j=$((i-8)); P0=96; H0=288; fi
  a=$((P0+12*j)); b=$((H0+12*j))
  CPUS="$a-$((a+11)),$b-$((b+11))"
  CUDA_VISIBLE_DEVICES=$i SEED0=$s0 ROOMS=$PER OUT=/root/ig7_g$i DEST=/root/ig7_blend \
  OMP_NUM_THREADS=$NT MKL_NUM_THREADS=$NT OPENBLAS_NUM_THREADS=$NT NUMEXPR_NUM_THREADS=$NT \
    nohup taskset -c $CPUS bash -c "/root/ig7_render.sh run >> /root/ig7_g$i.log 2>&1; touch /root/IG7_G${i}_DONE" >/dev/null 2>&1 &
  echo "GPU $i -> seed $s0..$((s0+PER-1))  CPU $CPUS"
  sleep 1
done
