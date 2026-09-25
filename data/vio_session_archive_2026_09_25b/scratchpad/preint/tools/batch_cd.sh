#!/bin/bash
# 前端能否精确积到帧时刻:相机事件晚投 20 ms(IMU 已覆盖帧时刻,模拟直播时相机帧晚到),引擎与时间戳不变。
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
$P/tools/run.sh 13f5_okvis_cd0 13f5 okvis_cd_nothr --pace 0 --cam-delay-ms 0 | head -1
for sc in 13f5 6d18 7353; do
  for e in base okvis; do $P/tools/run.sh ${sc}_${e}_cd20 $sc ${e}_cd_nothr --pace 0 --cam-delay-ms 20 | head -1; done
done
echo BATCH_CD_DONE
