#!/bin/bash
# 16 路 × 2 线程 = 32 核;OpenCV 单独限(它不认 OMP_NUM_THREADS)
for p in $(pgrep -f "tartanground2mv"); do kill -9 $p 2>/dev/null; done
for p in $(pgrep -f "tg_batch.sh"); do kill -9 $p 2>/dev/null; done
sleep 3
rm -rf /root/tg_work/*
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
export OPENCV_FOR_THREADS_NUM=2
export TG_STRIDE=5 TG_MAXF=150
cd /root
/venv/main/bin/python - <<'PYEOF'
lines = [l for l in open("/root/tg_plan.tsv") if l.strip()]
N = 16
for i in range(N):
    with open("/root/tg_plan16_%d.tsv" % i, "w") as f:
        for j, l in enumerate(lines):
            if j % N == i: f.write(l)
print("split into", N)
PYEOF
for i in $(seq 0 15); do
  nohup /root/tg_batch.sh /root/tg_plan16_$i.tsv > /root/tg_s16_$i.log 2>&1 &
done
sleep 3
echo "launched $(pgrep -cf tg_batch.sh) shards"
