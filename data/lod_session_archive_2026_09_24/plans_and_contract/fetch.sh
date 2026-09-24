#!/bin/bash
# 可续传拷贝:rsync --partial 失败就重试(断点保留在 .partial 里)。
# 用法: ./fetch.sh oct_prod
set -u
D=$1
for i in $(seq 1 50); do
  if rsync -a --partial -e "ssh -p <ssh-port> -o BatchMode=yes -o ServerAliveInterval=30" \
       root@<gpu-box-a>:/root/$D ./ ; then
    echo "== $D done attempt $i $(date +%T)"; exit 0
  fi
  echo "== $D attempt $i failed $(date +%T), retrying"; sleep 5
done
exit 1
