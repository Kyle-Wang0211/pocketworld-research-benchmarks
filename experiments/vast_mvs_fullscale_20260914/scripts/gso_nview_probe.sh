#!/bin/bash
M=/root/gso_probe/Vtech_Roll_Learn_Turtle
for NV in 12 24 32 49; do
  rm -rf /root/gso_mvs/nv$NV
  S=$(date +%s)
  /root/ig_venv/bin/python /root/gso_stage1.py $M /root/gso_mvs nv$NV $NV 128 >/dev/null 2>&1 || { echo "  NV=$NV 渲染失败"; continue; }
  /venv/main/bin/python /root/gso_stage2.py /root/gso_mvs nv$NV >/dev/null 2>&1 || { echo "  NV=$NV 转换失败"; continue; }
  E=$(( $(date +%s)-S ))
  /venv/main/bin/python - "$NV" "$E" <<'PYEOF'
import sys, numpy as np
NV=int(sys.argv[1]); E=int(sys.argv[2])
L=[l.split() for l in open(f"/root/gso_mvs/nv{NV}/cams/pair.txt").read().strip().split("\n")]
n=int(L[0][0]); cnt=[]
for i in range(n):
    row=L[2+2*i]; sc=[float(x) for x in row[2::2]]
    cnt.append(sum(1 for s in sc if s > 1.0))     # 分数>1 才算真共视(观察到真共视是 10+,假的是 1e-4)
cnt=np.array(cnt)
print("  NV=%-3d 耗时%4ds | 每ref有效源视图 中位=%2d 最小=%2d | 能凑满8个的ref占比=%.2f"
      % (NV, E, int(np.median(cnt)), int(cnt.min()), float((cnt>=8).mean())))
PYEOF
done
