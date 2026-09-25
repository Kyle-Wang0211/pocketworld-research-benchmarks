#!/bin/bash
# 删机前收尾:补转换新完成房间 → 增量补传 → 校验和空跑比对(差异应为 0)
echo "开始 $(date +%T)"
ssh -A -o BatchMode=yes -o LogLevel=ERROR -o ServerAliveInterval=30 -p <端口> root@<台湾箱> '
bash /root/ig7_convert_all.sh; tail -1 /root/ig7_convert.log
E="ssh -o BatchMode=yes -o LogLevel=ERROR -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -p <端口>"
rsync -a --partial -z --zc=zstd -e "$E" /root/ig7_blend /root/ig7_blend_manifest.tsv /root/ig7_conv_logs /root/ig7_convert.log root@<印度箱>:/root/ && echo "增量补传完成"
N=$(rsync -anc --itemize-changes -e "$E" /root/ig7_blend /root/ig7_blend_manifest.tsv root@<印度箱>:/root/ | grep -v "^\." | wc -l)
echo "校验和比对差异条数: $N"
echo "台湾: $(ls /root/ig7_blend | wc -l) 间 $(find /root/ig7_blend -type f | wc -l) 文件 $(du -sb /root/ig7_blend | cut -f1) 字节"
$E root@<印度箱> "echo \"印度: \$(ls /root/ig7_blend | wc -l) 间 \$(find /root/ig7_blend -type f | wc -l) 文件 \$(du -sb /root/ig7_blend | cut -f1) 字节\""
'
echo "结束 $(date +%T)"
