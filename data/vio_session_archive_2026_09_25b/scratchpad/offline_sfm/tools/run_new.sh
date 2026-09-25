#!/bin/bash
# run_new.sh <tag> <scene> —— [offline_sfm 新引擎轮] 新引擎回放(只读使用 preint 的现成二进制与配置,输出写本目录)。
# 二进制:scratchpad/preint/v/okvis_cd_nothr(xrslam feat/okvis2-preint@4e8dda2,单线程,回放器带 PW_BKPOSE_STATE ⇒
#   后端 CSV 追加 v / bg / ba 九列;带 --cam-delay-ms)。喂法逐项照抄 preint/tools/run.sh(= bkpose/wobble 手机同款),
#   只加本轮两项:--cam-delay-ms 20(相机事件晚于同时刻 IMU 20 ms 投递 = 实拍顺序,引擎时间戳不变)、
#   --td-extra-ms -5(🔴 只限本次实验,不写进任何规则或配置)。--pace 0:单线程下结果与节奏无关,逐位可复现。
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
O=$SP/offline_sfm/newrun; R=$HOME/Developer/viobench-recordings; B=$SP/preint/v/okvis_cd_nothr
TAG=$1; SC=$2
case $SC in
  13f5) RUN=$R/run-13f53d2f-5935-4b1a-a499-4dc8367ea935;;
  6d18) RUN=$R/run-6d187dff-403a-4882-b692-7bdc6c3cfa2a;;
  7353) RUN=$R/run-73538ad6-8418-4eaf-8b75-a63c9d32af46;;
  *) echo bad scene; exit 2;;
esac
kb=$(df -k ~ | tail -1 | awk '{print $4}'); [ "$kb" -lt $((3*1024*1024)) ] && { echo "STOP 磁盘 < 3 GB"; exit 90; }
L=$SP/.xrslam_run.lock
until mkdir $L 2>/dev/null; do sleep 3; done
echo "offline_sfm $$ $(date +%T) $TAG" > $L/owner
trap 'rm -f $L/owner; rmdir $L 2>/dev/null' EXIT
echo "$TAG $SC bin=okvis_cd_nothr --pace 0 --cam-delay-ms 20 --td-extra-ms -5 loadavg=$(sysctl -n vm.loadavg) start=$(date +%T)" > $O/$TAG.cmd
$B/pwvi_runner $SP/preint/cfg/slam_config.yaml $SP/preint/cfg/dev_$SC.yaml pwvi://$RUN $O/$TAG.body.tum --downscale 3 --rate-hz 30 \
   --rate-frac 0.8 --pace 0 --drop-before-imu --intrinsics-jsonl --exposure-half --camera-out $O/$TAG.cam.tum \
   --frame-map-out $O/$TAG.map --hex-out $O/$TAG.hex --keyed-out $O/$TAG.keyed.csv --backend-out $O/$TAG.backend.csv \
   --cam-delay-ms 20 --td-extra-ms -5 > $O/$TAG.log 2>&1
RC=$?
echo "end=$(date +%T) rc=$RC" >> $O/$TAG.cmd
echo "rc=$RC $TAG"; grep -E "^\[pwvi\]|=== " $O/$TAG.log | head -5
