#!/bin/bash
# 用法: gen_wgsl.sh <名字> "<env 空格分隔>"  —— 在 Mac 上经变换链生成主核 WGSL,验 fx13 sha,push 到 Mate 10 的 app 目录。
# 之后 run_apk.sh 的 extra 里带同一组 env + OFFICIAL_AETHER_MATCH_DAWN_WGSL_FILE=/data/data/com.kyle.pwprobe/files/wgsl/<名字>.wgsl
set -euo pipefail
NAME=$1; ENVS=$2; B=/private/tmp/pwofficial-dawn-host/build; O=/private/tmp/pw_wgsl_gen; mkdir -p $O
env ${=ENVS} OFFICIAL_AETHER_MATCH_DAWN_WGSL_DUMP=1 $B/fair_match_portable_arm ~/Developer/pw_android_probe/fx13 $O 2 1 0.8 $NAME >$O/$NAME.out 2>$O/$NAME.err
sha=$(grep -oE '"pairs_sha256":"[0-9a-f]{12}' $O/$NAME.out | cut -d'"' -f4); [ "$sha" = "a59db73512ce" ] || { echo "SHA FAIL $sha"; exit 1; }
awk '/===WGSL_BEGIN===/{f=1;next}/===WGSL_END===/{f=0}f' $O/$NAME.err > $O/$NAME.wgsl
d=${PW_ADB_SERIAL:-D3H7N18328002468}
adb -s $d push $O/$NAME.wgsl /data/local/tmp/pwmatch/$NAME.wgsl >/dev/null
adb -s $d shell "run-as com.kyle.pwprobe sh -c 'mkdir -p files/wgsl && cp /data/local/tmp/pwmatch/$NAME.wgsl files/wgsl/'"
echo "OK $NAME sha=$sha lines=$(wc -l < $O/$NAME.wgsl) → files/wgsl/$NAME.wgsl"
