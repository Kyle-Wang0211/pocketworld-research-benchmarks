#!/bin/bash
# ============================================================================
# GC 对照臂看门狗
#
# 干什么: ep5 落盘 -> 停主训练 -> 从 ep5 跑一个 epoch 的 GC 臂 -> 重启主训练 -> 出点云
#
# 为什么必须停主训练: 主训练占 20 GB / 32 GB, 两个 batch=4 的训练放不下同一张 5090。
#   降到 batch=2 就不是单变量了(和基线不可比), 所以只能串行。
#
# 为什么必须用 --resume 而不是 --loadckpt (train.py:332-347):
#   --loadckpt 只 load 模型, start_epoch=0, OneCycle 从热身重来 (lr 4e-5);
#   --resume   还原优化器状态 + start_epoch=epoch+1, OneCycle last_epoch=len(loader)*start_epoch-1
#              => 接在 ep5 的 lr≈7e-4 上。基线进 ep6 也是这条曲线 ⇒ 两臂唯一变量 = --gc_weight。
#
# 对照的另一臂 = 主训练自己的 ep6 (重启后它就跑)。同起点 ep5、同优化器状态、同种子、
#   同采样顺序 (EqualDomainSampler seed=epoch+777)。
#
# 中止: touch /root/WD.ABORT
# ============================================================================
set -u
LOG(){ echo "[$(date +%m-%d\ %H:%M:%S)] $*"; }
ABORT(){ [ -f /root/WD.ABORT ] && { LOG "收到 /root/WD.ABORT, 看门狗退出, 未改动任何东西"; exit 9; }; }

FULL=/root/diffmvs_full/checkpoints/casdiff_full
EP5=$FULL/model_000005.ckpt
GCDIR=/root/gc_arm

LOG "看门狗启动。等 $EP5"
while [ ! -f "$EP5" ]; do ABORT; sleep 120; done
# 等文件写完(大小连续两次不变)
s1=0; while :; do ABORT; s2=$(stat -c%s "$EP5"); [ "$s1" = "$s2" ] && [ "$s2" -gt 1000000 ] && break; s1=$s2; sleep 20; done
LOG "ep5 落盘: $(stat -c%s $EP5) 字节 md5=$(md5sum $EP5 | cut -c1-12)"

# 让 epoch_snapshot 先把 ep5 的快照/快速臂做完(它自己跑, 约 4 分钟), 不然那份 ep5 点云就没了
LOG "等 epoch_snapshot 做完 ep5 的快照"
for i in $(seq 1 60); do ABORT; [ -f /root/snap_ckpt/full_ep5.ckpt ] && [ -f /root/arm_full_ep5/pc_t3.ply ] && break; sleep 30; done
LOG "  snap_ckpt/full_ep5.ckpt=$([ -f /root/snap_ckpt/full_ep5.ckpt ] && echo 有 || echo 无)  arm_full_ep5/pc_t3.ply=$([ -f /root/arm_full_ep5/pc_t3.ply ] && echo 有 || echo 无)"

ABORT
# ---- 停主训练 ----
PIDS=$(pgrep -f "diffmvs_full.*train.py|train.py.*casdiff_full" | head -5)
LOG "停主训练 PID: $(pgrep -f 'train.py' | tr '\n' ' ')"
pkill -f "train_full.sh"; pkill -INT -f "train.py"
for i in $(seq 1 30); do pgrep -f "train.py" >/dev/null || break; sleep 5; done
pgrep -f "train.py" >/dev/null && { LOG "SIGINT 没停住, 上 SIGKILL"; pkill -KILL -f "train.py"; sleep 5; }
LOG "主训练已停。显存: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"

# ---- 建 GC 臂 ----
ABORT
rm -rf $GCDIR && mkdir -p $GCDIR
cp $EP5 $GCDIR/model_000005.ckpt
LOG "GC 臂 logdir 就绪, 起点 md5=$(md5sum $GCDIR/model_000005.ckpt | cut -c1-12) (= 主训练 ep5)"

cd /root/diffmvs_gc
# 逐字取自 /root/resume_full.sh 第一段的 COMMON, 只改 logdir 并加 --gc_weight 1
COMMON="--mode=train --dataset=blend --batch_size=4 --epochs=16 --lr=0.001 --lr_sche onecycle --resume \
--logdir $GCDIR --trainpath=/root/monotrain --trainviews=8 --testviews=8 --numdepth=384 --numdepth_initial=48 \
--stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 --min_radius 0.125 --max_radius 8 --conf_weight 0.05 \
--hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 --domain_balance 100000 --repeat_cap 0 \
--trainlist lists/full_v3/train.txt --testlist lists/full_v3/val.txt"

LOG "起 GC 臂 (--gc_weight 1, 预计 15.6 h/epoch)"
setsid nohup /venv/main/bin/python -u train.py $COMMON --train_epochs=8 --scale 0 0.25 0.05 --gc_weight 1 \
  </dev/null > $GCDIR/gc_arm.log 2>&1 &
sleep 120
LOG "  自报: $(grep -m1 '\[GC\]' $GCDIR/gc_arm.log)"
LOG "  起点: $(grep -m1 'start at epoch' $GCDIR/gc_arm.log)"
LOG "  首步: $(grep -m1 '^Epoch' $GCDIR/gc_arm.log | cut -c1-100)"

# ---- 等它跑完 epoch 6 ----
STALL=0; LASTSTEP=""
while [ ! -f $GCDIR/model_000006.ckpt ]; do
  ABORT
  sleep 300
  # 存活闸1: 进程没了还没出 ckpt => 挂了, 别空转, 立刻把主训练还回去
  if ! pgrep -f -- "--logdir /root/gc_arm" >/dev/null; then
    LOG "🔴 GC 臂进程消失且没有 ep6 ckpt。尾部日志:"; tail -5 $GCDIR/gc_arm.log
    LOG "把卡还给主训练, 看门狗退出"
    cd /root && setsid nohup /root/resume_full.sh </dev/null >> /root/train_full.nohup 2>&1 &
    exit 7
  fi
  L=$(grep '^Epoch' $GCDIR/gc_arm.log | tail -1 | cut -c1-90)
  # 存活闸2: 进程在但步数 30 分钟不动 => 挂死
  STEP=$(echo "$L" | grep -oE "Iter [0-9]+")
  if [ "$STEP" = "$LASTSTEP" ]; then STALL=$((STALL+1)); else STALL=0; LASTSTEP="$STEP"; fi
  if [ "$STALL" -ge 6 ]; then
    LOG "🔴 GC 臂 30 分钟步数没动 ($STEP), 判为挂死"; tail -5 $GCDIR/gc_arm.log
    pkill -KILL -f -- "--logdir /root/gc_arm"; sleep 5
    cd /root && setsid nohup /root/resume_full.sh </dev/null >> /root/train_full.nohup 2>&1 &
    exit 7
  fi
  echo "    $L"
done
sleep 60
LOG "GC 臂 ep6 落盘: md5=$(md5sum $GCDIR/model_000006.ckpt | cut -c1-12)"
# 🔴 不能用 "diffmvs_gc" 匹配: 那是工作目录, 不在命令行里。用 logdir 认。
pkill -f -- "--logdir /root/gc_arm"; sleep 10
pgrep -f -- "--logdir /root/gc_arm" >/dev/null && { LOG "GC 臂没停住, SIGKILL"; pkill -KILL -f -- "--logdir /root/gc_arm"; sleep 5; }
pgrep -f "train.py" >/dev/null && { LOG "🔴 还有 train.py 在跑, 不敢重启主训练, 退出"; exit 8; }
LOG "GC 臂已停"

# ---- 重启主训练(它会从 ep5 跑出基线 ep6) ----
ABORT
cd /root && setsid nohup /root/resume_full.sh </dev/null >> /root/train_full.nohup 2>&1 &
sleep 90
LOG "主训练已重启: $(grep -m1 'start at epoch' /root/train_full.nohup | tail -1)"

# ---- GC 臂出点云(同一条 infer_arm.sh, 与所有既有臂同口径) ----
LOG "GC 臂出点云 -> /root/arm_gc_ep6"
/root/infer_arm.sh $GCDIR/model_000006.ckpt /root/arm_gc_ep6 > /root/arm_gc_ep6.infer.log 2>&1
LOG "  rc=$? depth=$(ls /root/arm_gc_ep6/depth_est 2>/dev/null | wc -l)"
LOG "全部完成。对照:  GC臂 /root/arm_gc_ep6  vs  基线 /root/arm_full_ep6 (主训练跑完 ep6 后由 epoch_snapshot 产出)"
touch /root/WD.DONE
