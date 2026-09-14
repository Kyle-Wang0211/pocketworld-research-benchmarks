#!/bin/bash
# 等孤儿 sp2mvsnet(PID 2368261, batch 80-99) 结束, 再从 shard 80 重启 sp_stream 到 420 (幂等, 80-99 会秒过)
while kill -0 2368261 2>/dev/null; do sleep 5; done
echo "[$(date +%H:%M)] 孤儿转换结束, 重启 sp_stream 80..419" >> /root/sp_stream.log
exec /root/sp_stream.sh 80 420
