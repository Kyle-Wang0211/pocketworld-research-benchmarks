#!/bin/bash
# GSO/TG 全部退出后: 换 monotrain 链接 -> 建 lists/full_v3 -> 采样器验证 -> 冒烟 (不开训)
LOG=/root/post_regen.log; exec > $LOG 2>&1
while ps -eo command | awk '(/gso_batch_v2/ || /tg_batch_v2\.sh/) && !/awk/' | grep -q .; do sleep 120; done
echo "=== [$(date +%m-%d\ %H:%M)] 重生成全部退出 ==="
echo "GSO v2 完成 $(ls /root/gso_mvs_v2/gso_*/cams/pair.txt | wc -l) / 1033; 失败: $(grep -h '^\[FAIL' /root/gso_v2_s?.log /root/gso_v2_retry.log | awk '{print $2}' | sort -u | wc -l)"
echo "TG v2 完成 $(ls /root/tg_conv_v2/tg_*/cams/pair.txt | wc -l) / 292; 失败: $(grep -h FAIL /root/tg_batch_v2_?.log | wc -l)"
echo "TA v2 完成 $(ls /root/ta2/blendfmt_v2 | wc -l) scan"
cd /root/monotrain
for l in ta_* tg_* gso_*; do [ -L "$l" ] && rm "$l"; done
n=0; for d in /root/ta2/blendfmt_v2/*/; do b=$(basename $d); [ -f $d/cams/pair.txt ] && ln -s ${d%/} ta_$b && n=$((n+1)); done; echo "ta_ 链接 $n"
n=0; for d in /root/tg_conv_v2/tg_*/; do b=$(basename $d); [ -f $d/cams/pair.txt ] && ln -s ${d%/} $b && n=$((n+1)); done; echo "tg_ 链接 $n"
n=0; for d in /root/gso_mvs_v2/gso_*/; do b=$(basename $d); [ -f $d/cams/pair.txt ] && ln -s ${d%/} $b && n=$((n+1)); done; echo "gso_ 链接 $n"
echo "monotrain: sp=$(ls | grep -c '^sp_scene_') ta=$(ls | grep -c '^ta_') tg=$(ls | grep -c '^tg_') bmvs=$(ls | grep -cE '^[0-9a-f]{24}$') ak=$(ls | grep -c '^ak_') gso=$(ls | grep -c '^gso_')"
echo "--- build lists v3 ---"; /venv/main/bin/python /root/build_lists_v3.py 2>&1 | grep -v "less ref_view"
echo "--- sampler N=100000 on full_v3 ---"; /venv/main/bin/python /root/test_domain_sampler.py /root/diffmvs_full/lists/full_v3/train.txt 100000 2>&1 | grep -v "less ref_view"
echo "--- smoke full_v3 ---"; LISTS=full_v3 /venv/main/bin/python /root/smoke_loader.py 20 30 2>&1 | grep -v "less ref_view"
echo "=== [$(date +%H:%M)] post_regen done ==="
