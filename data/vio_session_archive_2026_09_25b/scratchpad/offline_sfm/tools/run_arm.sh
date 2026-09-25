#!/bin/bash
# run_arm.sh <feed_name> <rep> [driver args...] —— [offline_sfm 2026-09-25] 一次出货核运行。
# feed_name = feeds/<feed_name>.jsonl(如 13f5_p0_B2);输出 runs/<feed_name>_r<rep>/。
# 与 bkpose / wobble 共用 scratchpad/.xrslam_run.lock(mkdir 锁),我的运行不与它们的回放重叠。
# 跑完只删本次运行自己生成的 session.db*(12 MB 级中间库;delivered_poses / tracks / 诊断 jsonl 保留)。
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
O=$SP/offline_sfm
FEED=$1; REP=$2; shift 2
D=$O/runs/${FEED}_r${REP}
kb=$(df -k ~ | tail -1 | awk '{print $4}')
if [ "$kb" -lt $((3*1024*1024)) ]; then echo "STOP: 剩余空间 $(df -h ~ | tail -1 | awk '{print $4}') < 3 GB"; exit 90; fi
rm -rf "$D"; mkdir -p "$D"
L=$SP/.xrslam_run.lock
until mkdir $L 2>/dev/null; do sleep 0.1; done
echo "offline_sfm $$ $(date +%T) $FEED r$REP" > $L/owner
trap 'rm -f $L/owner; rmdir $L 2>/dev/null' EXIT
echo "$FEED r$REP args=$* loadavg=$(sysctl -n vm.loadavg) start=$(date +%T)" > $D/cmd.txt
cd "$D" && env -i HOME=$O/home PATH=/usr/bin:/bin /usr/bin/time -l $O/build/offline_pose_arm_driver $O/feeds/$FEED.jsonl "$D" "$@" > run.log 2> err.log
RC=$?
echo "end=$(date +%T) rc=$RC loadavg_end=$(sysctl -n vm.loadavg)" >> $D/cmd.txt
for f in session.db session.db-shm session.db-wal; do [ -f "$D/$f" ] && [ ! -L "$D/$f" ] && rm -f "$D/$f"; done
echo "rc=$RC $FEED r$REP $(grep -E '^RESULT' $D/run.log | cut -c1-160)"
