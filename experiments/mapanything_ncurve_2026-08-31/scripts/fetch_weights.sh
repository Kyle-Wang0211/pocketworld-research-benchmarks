#!/bin/zsh
# [下载 2026-08-31] 学校 VPN 隧道 ~180 KB/s 且会掐长连接(之前 hf_transfer 卡死在 0 字节)。
# 对策:curl -C - 断点续传 + 无限重试 + 每次重新解析签名 URL(它有时效)。
# 不用并发 —— 已实测隧道按总量限速,4 路 178 / 16 路 179 KB/s,加并发零收益。
cd "$(dirname "$0")"
fetch () {  # $1=repo  $2=目标目录  $3=期望字节
  local repo="$1" dir="$2" want="$3"
  local url="https://huggingface.co/$repo/resolve/main/model.safetensors"
  curl -sL --max-time 120 "https://huggingface.co/$repo/raw/main/config.json" -o "$dir/config.json"
  local n=0
  while :; do
    local have=0; [ -f "$dir/model.safetensors" ] && have=$(stat -f%z "$dir/model.safetensors")
    if [ "$have" -ge "$want" ]; then
      echo "$(date +%H:%M:%S) [$dir] ✅ 完成 $((have/1048576)) MB"; return 0
    fi
    n=$((n+1))
    echo "$(date +%H:%M:%S) [$dir] 第 $n 次续传,已有 $((have/1048576))/$((want/1048576)) MB"
    curl -L -C - --max-time 1800 --connect-timeout 30 --retry 0 \
         -o "$dir/model.safetensors" "$url" 2>/dev/null
    sleep 3
  done
}
fetch facebook/map-anything-apache-v1 weights/v1    2253389824   # 2149 MB,先下小的
fetch facebook/map-anything-apache    weights/giant 4914675712   # 4686 MB
echo "$(date +%H:%M:%S) 全部完成"
