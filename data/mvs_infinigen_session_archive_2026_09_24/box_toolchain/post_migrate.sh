#!/bin/bash
# 搬运完成后: gso 链接 -> 建 list -> 采样器验证(N=100000) -> 数据通路冒烟
LOG=/root/post_migrate.log; exec > $LOG 2>&1
echo "=== [$(date +%m-%d\ %H:%M)] post_migrate ==="
cd /root/monotrain; n=0; for d in /root/gso_mvs/gso_*/; do b=$(basename $d); [ -f $d/cams/pair.txt ] || continue; [ -e $b ] || { ln -s ${d%/} $b; n=$((n+1)); }; done
echo "gso 链接新建 $n; monotrain: sp=$(ls | grep -c ^sp_scene_) ta=$(ls | grep -c ^ta_) tg=$(ls | grep -c ^tg_) bmvs=$(ls | grep -cE \"^[0-9a-f]{24}$\") ak=$(ls | grep -c ^ak_) gso=$(ls | grep -c ^gso_)"
echo "--- build lists ---"; /venv/main/bin/python /root/build_full_lists_v2.py 2>&1 | grep -v "less ref_view"
echo "--- sampler N=100000 on full list ---"; /venv/main/bin/python /root/test_domain_sampler.py /root/diffmvs_full/lists/full/train.txt 100000 2>&1 | grep -v "less ref_view"
echo "--- smoke loader ---"; /venv/main/bin/python /root/smoke_loader.py 20 30 2>&1 | grep -v "less ref_view"
echo "=== [$(date +%H:%M)] post_migrate done ==="
