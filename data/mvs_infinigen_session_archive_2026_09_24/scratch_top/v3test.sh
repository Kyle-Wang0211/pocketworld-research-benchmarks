#!/bin/bash
# v3 演练: 假 P / 假 VP, seed 9000xx。失败集 {900002(coarse rc=1), 900005(coarse rc=139)};
# 900001 预先放「半截渲染」(c0,c1 完整, c2 只有 rgb) 验证断点续; 900003 预先标 failed 验证不重试;
# 900004 预先放「孤儿 coarse 正在跑」(后台 sleep 进程, 命令行含 --seed 900004 --task coarse) 验证等待接管。
T=/tmp/v3t; rm -rf $T; mkdir -p $T/bin $T/ig
cat > $T/bin/P <<'P'
#!/bin/bash
s=""; task=""; of=""; while [ $# -gt 0 ]; do case $1 in --seed) s=$2;; --task) task=$2;; --output_folder) of=$2;; esac; shift; done
sleep 1
if [ "$task" = coarse ]; then
  case $s in 900002) exit 1;; 900005) exit 139;; esac
  mkdir -p $of; touch $of/scene.blend; exit 0
fi
base=$(dirname $of); k=$(basename $(dirname $base) | tr -d c)
if [[ $of == */rgb/out ]]; then mkdir -p $base/frames/Image/camera_$k $base/frames/camview/camera_$k; touch $base/frames/Image/camera_$k/Image_${k}_0_0001_0.png $base/frames/camview/camera_$k/camview_${k}_0_0001_0.npz
else mkdir -p $base/frames/Depth/camera_$k; touch $base/frames/Depth/camera_$k/Depth_${k}_0_0001_0.npy; fi
echo "P $task seed=$s cam=$k" >> /tmp/v3t/calls.log
P
cat > $T/bin/VP <<'V'
#!/bin/bash
out=""; scan=""; while [ $# -gt 0 ]; do case $1 in --out) out=$2;; --scan) scan=$2;; esac; shift; done
mkdir -p $out/ig_$scan/cams; echo 3 > $out/ig_$scan/cams/pair.txt; echo "VP convert $scan" >> /tmp/v3t/calls.log
V
chmod +x $T/bin/P $T/bin/VP
OUT=$T/out; mkdir -p $OUT/failed $OUT/work
touch $OUT/failed/900003
for k in 0 1; do d=$OUT/work/s900001/c$k; mkdir -p $d/rgb/frames/Image/x $d/rgb/frames/camview/x $d/gt/frames/Depth/x; touch $d/rgb/frames/Image/x/Image_1.png $d/rgb/frames/camview/x/camview_1.npz $d/gt/frames/Depth/x/Depth_1.npy; done
d=$OUT/work/s900001/c2; mkdir -p $d/rgb/frames/Image/x; touch $d/rgb/frames/Image/x/Image_1.png
mkdir -p $OUT/work/s900001/coarse; touch $OUT/work/s900001/coarse/scene.blend
# 孤儿 coarse: 8 秒后写 scene.blend
( mkdir -p $OUT/work/s900004/coarse; exec -a "orphan --seed 900004 --task coarse" bash -c "sleep 8; touch $OUT/work/s900004/coarse/scene.blend" ) &
sleep 0.5
OUT=$OUT DEST=$T/dest SEEDS="900001 900002 900003 900004 900005 900006 900007 900008" NEED=4 K=2 NCAM=4 \
  P=$T/bin/P VP=$T/bin/VP IG=$T/ig CONV=/dev/null timeout 300 bash /root/ig7_v3_test.sh > $T/stdout 2>&1
echo "rc=$?"; echo "=== run.log"; cat $OUT/run.log; echo "=== 成品"; ls $T/dest; echo "=== failed"; ls $OUT/failed
echo "=== 900001 渲染调用 (应只有 cam 2,3)"; grep "render seed=900001" $T/calls.log | sort -u
echo "=== coarse 调用 (900002/900005 各应恰好 1 次, 900003/900004 应 0 次)"; grep coarse $T/calls.log | sort | uniq -c
echo "=== 900007/900008 应未被用到 (NEED=4 满即止)"; grep -c -e 900008 $T/calls.log
