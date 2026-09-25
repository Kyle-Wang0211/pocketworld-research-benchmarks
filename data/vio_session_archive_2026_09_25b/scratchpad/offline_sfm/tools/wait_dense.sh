#!/bin/bash
# 等补充批结束,最多等 $1 秒
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
end=$(( $(date +%s) + ${1:-580} ))
until grep -qE "补充批完成|停止于|STOP|不跑" $O/batch_dense.log 2>/dev/null || [ $(date +%s) -ge $end ]; do sleep 5; done
echo "已完成 $(grep -c '^rc=0' $O/batch_dense.log)/36"; grep -E "补充批完成|停止于|STOP|不跑" $O/batch_dense.log
