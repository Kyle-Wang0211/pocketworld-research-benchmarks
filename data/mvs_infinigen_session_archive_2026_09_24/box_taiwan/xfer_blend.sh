#!/bin/bash
# 台湾 → 印度直传已转换房间(ssh -A 代理转发);先等台湾转换脚本跑完
echo "开始 $(date +%T)"
ssh -A -o BatchMode=yes -o LogLevel=ERROR -o ServerAliveInterval=30 -p <端口> root@<台湾箱> '
while pgrep -f "ig7_convert_al[l]" >/dev/null; do sleep 10; done; echo "台湾转换结束 $(date +%T): $(ls /root/ig7_blend | wc -l) 间, $(du -sh /root/ig7_blend | cut -f1)"
T0=$(date +%s)
rsync -a --partial -z --zc=zstd -e "ssh -o BatchMode=yes -o LogLevel=ERROR -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -p <端口>" /root/ig7_blend /root/ig7_blend_manifest.tsv /root/ig7_conv_logs root@<印度箱>:/root/ && echo "rsync 完成, 用时 $(( $(date +%s)-T0 ))s" || echo "rsync 失败 rc=$?"
'
echo "结束 $(date +%T)"
