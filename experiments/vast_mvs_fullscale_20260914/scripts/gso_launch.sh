#!/bin/bash
export GSO_NV=20 GSO_SAMPLES=128
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
cd /root
/venv/main/bin/python - <<'PYEOF'
import json
ms = json.load(open("/root/gso_models.json"))
N = 2
for i in range(N):
    open("/root/gso_list_%d.txt" % i, "w").write("\n".join(ms[i::N]) + "\n")
print("共", len(ms), "个模型,切成", N, "份;每份", len(ms[::N]))
PYEOF
for i in 0 1; do nohup /root/gso_batch.sh /root/gso_list_$i.txt > /root/gso_s$i.log 2>&1 & done
sleep 2; echo "launched $(pgrep -cf gso_batch.sh) workers"
