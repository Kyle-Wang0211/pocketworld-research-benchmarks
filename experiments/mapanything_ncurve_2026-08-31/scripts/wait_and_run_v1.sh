#!/bin/zsh
# [守候 2026-08-31] v1 下完立刻跑分块质量验证,不用人盯。
# 只需要 v1 —— 回答「手机上必须分块,分块到底损失多少」。
# 若分块的损失比 giant→v1 的损失还大,那纠结用哪个 checkpoint 就没意义了。
cd "$(dirname "$0")"; source .venv/bin/activate
W=weights/v1/model.safetensors; WANT=2253389824
while :; do
  [ -f "$W" ] && [ "$(stat -f%z $W)" -ge "$WANT" ] && break
  sleep 60
done
echo "$(date +%H:%M:%S) ✅ v1 就位,开跑"
export MAPANYTHING_STATIC_GEOM=1
# 基准臂:一次全量。⚠️ MPS 上限 13.32 GB,v1 在 N=48 才 7.37 GiB,
#        外推 132 帧约 12.2 GiB —— 贴着上限,先试,失败就退到 N=64。
for N in 132 64; do
  echo "$(date +%H:%M:%S) --- 全量基准 N=$N ---"
  if python chunked_stream.py --model weights/v1 --chunk $N --overlap 0 --limit $N \
       --out qual_v1_full$N > qual_full$N.log 2>&1; then
    echo "$(date +%H:%M:%S) ✅ 全量 N=$N 成功"; FULL=$N; break
  else
    echo "$(date +%H:%M:%S) ❌ 全量 N=$N 失败(多半是显存),降级重试"
  fi
done
# 分块臂
for K in 8 4 2; do
  echo "$(date +%H:%M:%S) --- 分块 K=$K ---"
  python chunked_stream.py --model weights/v1 --chunk $K --overlap 2 --limit ${FULL:-64} \
    --out qual_v1_k$K > qual_k$K.log 2>&1 && echo "$(date +%H:%M:%S) ✅ K=$K" || echo "$(date +%H:%M:%S) ❌ K=$K"
done
echo "$(date +%H:%M:%S) 全部完成"
