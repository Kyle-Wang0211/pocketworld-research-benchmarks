#!/bin/bash
# 可续传分块拷贝 216M 的 octree.bin:每块 256 MiB,ssh+dd 写到本地文件对应偏移,
# 每块两端 sha256 比对通过才记入 done 列表;中断后重跑只补没通过的块。
set -u
H="-p <ssh-port> -o BatchMode=yes -o ServerAliveInterval=30"
R=root@<gpu-box-a>
RF=/root/oct_216M/octree.bin
LF=oct_216M/octree.bin
SIZE=3899807424
CH_MB=256
NCH=$(( (SIZE + CH_MB*1048576 - 1) / (CH_MB*1048576) ))
mkdir -p oct_216M
touch oct_216M.chunks_done
# 小文件先拷
for f in hierarchy.bin metadata.json log.txt; do
  [ -s oct_216M/$f ] || scp -P <ssh-port> -o BatchMode=yes -q $R:/root/oct_216M/$f oct_216M/$f
done
for i in $(seq 0 $((NCH-1))); do
  if grep -qx "$i" oct_216M.chunks_done; then continue; fi
  for attempt in $(seq 1 20); do
    ssh $H $R "dd if=$RF bs=1048576 skip=$((i*CH_MB)) count=$CH_MB 2>/dev/null" \
      | dd of=$LF bs=1048576 seek=$((i*CH_MB)) conv=notrunc 2>/dev/null
    rs=$(ssh $H $R "dd if=$RF bs=1048576 skip=$((i*CH_MB)) count=$CH_MB 2>/dev/null | sha256sum" 2>/dev/null | awk '{print $1}')
    ls=$(dd if=$LF bs=1048576 skip=$((i*CH_MB)) count=$CH_MB 2>/dev/null | shasum -a 256 | awk '{print $1}')
    if [ -n "$rs" ] && [ "$rs" = "$ls" ]; then
      echo "$i" >> oct_216M.chunks_done
      echo "== chunk $i/$((NCH-1)) ok $ls $(date +%T)"
      break
    fi
    echo "== chunk $i attempt $attempt mismatch/failed (r=$rs l=$ls) $(date +%T)"; sleep 5
  done
done
echo "== all chunks: $(sort -n oct_216M.chunks_done | uniq | wc -l)/$NCH  $(date +%T)"
