#!/bin/zsh
# giant 断点续传:HF 单文件下载会断,循环重试直到 safetensors 落盘。
cd "$(dirname "$0")"; source .venv/bin/activate
for i in $(seq 1 200); do
  python - <<'PY' && break
from huggingface_hub import snapshot_download
p=snapshot_download("facebook/map-anything-apache", local_dir="weights/giant",
                    max_workers=4, resume_download=True)
print("DONE", p)
PY
  echo "[retry $i] $(date +%H:%M:%S) $(du -sh weights/giant | cut -f1)"
  sleep 5
done
echo "FINISHED $(du -sh weights/giant)"
