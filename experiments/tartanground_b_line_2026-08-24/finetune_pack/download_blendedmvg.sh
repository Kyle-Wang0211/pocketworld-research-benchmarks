#!/usr/bin/env bash
# ============================================================================
# 在租用机上下载 BlendedMVG(= BlendedMVS + BlendedMVS+ + BlendedMVS++)
#
#   bash download_blendedmvg.sh /data/blendedmvg_zips [mvs|plus|plusplus|all]
#
# 源:GitHub Releases(**不要碰 OneDrive**,上次租机的教训)
#   v1.0.0 BlendedMVS   -> BlendedMVS.z01..z15 + BlendedMVS.zip   27.50 GiB
#   v1.0.1 BlendedMVS+  -> BlendedMVS1.z01..   + BlendedMVS1.zip  81.7  GiB
#   v1.0.2 BlendedMVS++ -> BlendedMVS2.z01..z42+ BlendedMVS2.zip  80.01 GiB
#   (资产清单与逐个字节数由 GitHub API 现取,不写死 —— 2026-08-24 核对过
#    v1.0.1/v1.0.2 的分卷各 2,044,723,200 B)
#
# ⚠️ 只下 *.zip 会得到几十 MB 的分卷描述符,不是数据本体;必须把 .z01.. 全下齐,
#    再 `zip -s 0 X.zip --out combined.zip` 合并后 unzip。
# ⚠️ 每个文件下完都与 API 报的 size **逐字节核对**,不一致就重下(最多 --retries 次)。
# ⚠️ 磁盘:压缩 ≈189 GiB,解压 ≈261 GiB;加预解码缓存与解压峰值,保守准备 1 TB。
#    只跑 BlendedMVS 一档(段①口径)则 150 GB 够。
# ============================================================================
set -euo pipefail
OUT=${1:?用法: bash download_blendedmvg.sh <下载目录> [mvs|plus|plusplus|all]}
WHICH=${2:-all}
RETRIES=${RETRIES:-6}
mkdir -p "$OUT"

case "$WHICH" in
  mvs)       TAGS="v1.0.0" ;;
  plus)      TAGS="v1.0.1" ;;
  plusplus)  TAGS="v1.0.2" ;;
  all)       TAGS="v1.0.0 v1.0.1 v1.0.2" ;;
  *) echo "第二个参数只能是 mvs|plus|plusplus|all"; exit 2 ;;
esac

for tag in $TAGS; do
  echo "════════ release $tag ════════"
  curl -sSfL "https://api.github.com/repos/YoYo000/BlendedMVS/releases/tags/$tag" \
    | python3 -c "
import json,sys
r=json.load(sys.stdin)
for a in r['assets']:
    print(a['name'], a['size'], a['browser_download_url'])
" > "$OUT/.assets_$tag.txt"

  total=$(awk '{s+=$2} END{printf "%.2f", s/1073741824}' "$OUT/.assets_$tag.txt")
  echo "资产 $(wc -l < "$OUT/.assets_$tag.txt") 个,合计 ${total} GiB"

  while read -r name size url; do
    dst="$OUT/$name"
    if [ -f "$dst" ]; then
      have=$(stat -c%s "$dst" 2>/dev/null || stat -f%z "$dst")
      if [ "$have" = "$size" ]; then echo "[skip] $name 已完整"; continue; fi
    fi
    ok=0
    for k in $(seq 1 "$RETRIES"); do
      # -C - 断点续传;--speed-time/--speed-limit 治 CDN 静默失速(<10KB/s 持续 60s 就断开重来)
      curl -L -C - --retry 3 --speed-time 60 --speed-limit 10000 \
           -o "$dst" "$url" || true
      have=$(stat -c%s "$dst" 2>/dev/null || stat -f%z "$dst" 2>/dev/null || echo 0)
      if [ "$have" = "$size" ]; then echo "[ok] $name $size B"; ok=1; break; fi
      echo "[retry $k/$RETRIES] $name: 得到 $have 期望 $size"
      sleep $((5 * k))
    done
    [ "$ok" = 1 ] || { echo "🔴 $name 下载失败"; exit 1; }
  done < "$OUT/.assets_$tag.txt"
done

cat <<'NEXT'

✅ 下载完成且逐字节核对通过。合并解压:

   cd <下载目录>
   zip -s 0 BlendedMVS.zip  --out combined_mvs.zip  && unzip -q combined_mvs.zip  -d /data/BlendedMVG
   zip -s 0 BlendedMVS1.zip --out combined_p1.zip   && unzip -q combined_p1.zip   -d /data/BlendedMVG
   zip -s 0 BlendedMVS2.zip --out combined_p2.zip   && unzip -q combined_p2.zip   -d /data/BlendedMVG

   解压后 /data/BlendedMVG/<24位场景ID>/{blended_images,cams,rendered_depth_maps}

下一步:建清单 + 全量体检(缺文件要等训练跑到那个样本才炸)
   python3 make_blendmvg_list.py /data/BlendedMVG /data/lists
NEXT
