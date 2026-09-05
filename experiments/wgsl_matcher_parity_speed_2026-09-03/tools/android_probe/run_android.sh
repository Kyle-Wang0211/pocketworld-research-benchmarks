#!/bin/bash
# 明天一条命令:插上手机、开 USB 调试,然后跑这个。
set -uo pipefail
P="$(cd "$(dirname "$0")" && pwd)"
echo "═══ 1/5 找设备 ═══"
adb devices -l | sed -n '2,5p'
N=$(adb devices | grep -c "device$")
[ "$N" -lt 1 ] && { echo "🔴 没有已授权的设备。请在手机上:设置→关于→连点版本号开发者模式→开 USB 调试→插线→手机上点"允许"。"; exit 1; }
echo "═══ 2/5 推送(二进制 + 夹具,约 30MB)═══"
adb shell mkdir -p /data/local/tmp/pwmatch
adb push "$P/pwmatchprobe" /data/local/tmp/pwmatch/ | tail -1
adb push "$P/fx13" /data/local/tmp/pwmatch/ | tail -1
adb shell chmod 755 /data/local/tmp/pwmatch/pwmatchprobe
echo "═══ 3/5 设备自报家门 + 默认核 8192²(Mali-G72 预计落 tiled)═══"
adb shell /data/local/tmp/pwmatch/pwmatchprobe /data/local/tmp/pwmatch/fx13 8192 2
echo "═══ 4/5 通用核 blocked(8x4)8192² ═══"
adb shell "OFFICIAL_AETHER_MATCH_DAWN_KERNEL=blocked OFFICIAL_AETHER_MATCH_DAWN_BLK_84=1 /data/local/tmp/pwmatch/pwmatchprobe /data/local/tmp/pwmatch/fx13 8192 2"
echo "═══ 5/5 通用核 blocked(8x4)产线口径 13312² ═══"
adb shell "OFFICIAL_AETHER_MATCH_DAWN_KERNEL=blocked OFFICIAL_AETHER_MATCH_DAWN_BLK_84=1 /data/local/tmp/pwmatch/pwmatchprobe /data/local/tmp/pwmatch/fx13 13312 2"
echo
echo "🔴 判据(与速度无关):"
echo "   8192²  的 sha256 应当是 fcb72732ae098e0b… (Mac 与 A16 都是这个)"
echo "   13312² 的 sha256 应当是 a59db73512ce…     (Mac 与 A16 都是这个)"
echo "   对得上 ⇒ 一套源码三端逐字节一致,得到实证。"
echo "   BACKEND_INFO 里的 kernel= 决定它走的是 mma 还是 tiled;subgroup=[a,b] 是这台机器的真实宽度。"
