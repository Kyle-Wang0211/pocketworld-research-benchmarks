#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
R=$HOME/Developer/viobench-recordings; id=4ad6e500-ff59-4e67-9bb5-25fb2efe2faa
until mkdir $SP/xr_shared.lock 2>/dev/null; do sleep 10; done
trap 'rmdir $SP/xr_shared.lock' EXIT
out=$SP/xr_shared/euroc1920_4ad6e500
[ -f $out/imu0/data.csv ] && { echo exists; exit 0; }
free=$(df -k /private/tmp | tail -1 | awk '{print $4}')
[ $free -lt 5300000 ] && { echo "LOW DISK $free KB — not converting"; exit 1; }
/usr/bin/python3 $HOME/Developer/arloopbench/tools/pwvi_to_euroc.py $R/run-$id $out 2>&1 | tail -3
echo "S2 made $out (1920x1440 full-res of run-$id, pwvi_to_euroc.py no downscale; shared, reuse)" > $out/README.S2
du -sh $out; df -h /private/tmp | tail -1
