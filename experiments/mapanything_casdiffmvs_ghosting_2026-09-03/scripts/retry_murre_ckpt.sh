#!/bin/bash
for i in $(seq 1 200); do
  if /root/venv_murre/bin/gdown "1gcThkgOQRmjAxhGJRV7SwzwXKBWP1cDa" -O /root/regionmerge/ckpt/murre_ckpt.zip >> /root/regionmerge/gdown_retry.log 2>&1; then
     echo "GDOWN_OK attempt $i $(date)" >> /root/regionmerge/gdown_retry.log; break
  fi
  echo "attempt $i failed $(date)" >> /root/regionmerge/gdown_retry.log
  sleep 600
done
