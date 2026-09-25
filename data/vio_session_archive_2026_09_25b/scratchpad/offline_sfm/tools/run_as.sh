#!/bin/bash
# run_as.sh <tag> <scene> <acc_shift_ms> <td_extra_ms> —— [offline_sfm 加计前移轮] 与 run_new.sh 完全相同的喂法
# (新引擎 4e8dda2 单线程、--pace 0、--cam-delay-ms 20),只多 --acc-shift-ms(加计时间戳整体平移,陀螺不动;
# 🔴 只作实验,不写进任何规则或配置)与可变的 --td-extra-ms。二进制:preint/v/okvis_as_nothr(只读使用;
# 引擎库与 okvis_cd_nothr 同一份 sha 3481b22f,回放器多一个 --acc-shift-ms 选项)。输出写 offline_sfm/asrun/。
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
O=$SP/offline_sfm/asrun; R=$HOME/Developer/viobench-recordings; B=$SP/preint/v/okvis_as_nothr
TAG=$1; SC=$2; AS=$3; TD=$4
case $SC in
  13f5) RUN=$R/run-13f53d2f-5935-4b1a-a499-4dc8367ea935;;
  6d18) RUN=$R/run-6d187dff-403a-4882-b692-7bdc6c3cfa2a;;
  7353) RUN=$R/run-73538ad6-8418-4eaf-8b75-a63c9d32af46;;
  *) echo bad scene; exit 2;;
esac
kb=$(df -k ~ | tail -1 | awk '{print $4}'); [ "$kb" -lt $((3*1024*1024)) ] && { echo "STOP 磁盘 < 3 GB"; exit 90; }
L=$SP/.xrslam_run.lock
until mkdir $L 2>/dev/null; do sleep 0.1; done
echo "offline_sfm $$ $(date +%T) $TAG" > $L/owner
trap 'rm -f $L/owner; rmdir $L 2>/dev/null' EXIT
echo "$TAG $SC bin=okvis_as_nothr --pace 0 --cam-delay-ms 20 --acc-shift-ms $AS --td-extra-ms $TD loadavg=$(sysctl -n vm.loadavg) start=$(date +%T)" > $O/$TAG.cmd
$B/pwvi_runner $SP/preint/cfg/slam_config.yaml $SP/preint/cfg/dev_$SC.yaml pwvi://$RUN $O/$TAG.body.tum --downscale 3 --rate-hz 30 \
   --rate-frac 0.8 --pace 0 --drop-before-imu --intrinsics-jsonl --exposure-half --camera-out $O/$TAG.cam.tum \
   --frame-map-out $O/$TAG.map --hex-out $O/$TAG.hex --keyed-out $O/$TAG.keyed.csv --backend-out $O/$TAG.backend.csv \
   --cam-delay-ms 20 --acc-shift-ms $AS --td-extra-ms $TD > $O/$TAG.log 2>&1
RC=$?
echo "end=$(date +%T) rc=$RC" >> $O/$TAG.cmd
echo "rc=$RC $TAG"
