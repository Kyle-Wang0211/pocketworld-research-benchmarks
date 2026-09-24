#!/bin/bash
set -e
cd /root
MAX_STUCK=16 NUM_CONC=24 EXTRA_CFG=fast_solve.gin OUTF=/root/ig7_official_g NUM_SCENES=320 nohup /root/ig7_official.sh > /root/ig7_official_g.log 2>&1 < /dev/null &
echo "调度器 pid $!"
nohup bash /root/ig7_coarse_timeout.sh > /dev/null 2>&1 < /dev/null &
echo "看门狗 pid $!"
