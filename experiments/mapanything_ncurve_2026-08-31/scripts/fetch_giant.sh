#!/bin/zsh
# 只下 giant,断点续传 + 无限重试。setsid 脱离进程组,避免前台命令超时被杀时连带
cd "$(dirname "$0")"
U="https://huggingface.co/facebook/map-anything-apache/resolve/main/model.safetensors"
W=4914675712
while :; do
  have=0; [ -f weights/giant/model.safetensors ] && have=$(stat -f%z weights/giant/model.safetensors)
  [ "$have" -ge "$W" ] && { echo "$(date +%H:%M:%S) ✅ giant 完成"; break; }
  echo "$(date +%H:%M:%S) 续传,已有 $((have/1048576))/$((W/1048576)) MB"
  curl -L -C - --max-time 1800 --connect-timeout 30 -o weights/giant/model.safetensors "$U" 2>/dev/null
  sleep 3
done
