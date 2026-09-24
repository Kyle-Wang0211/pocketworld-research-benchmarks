#!/bin/bash
# ig7_v3.sh —— 单路 worker 调度 v3 (台湾 16×5090 箱)。渲染/转换命令与 ig7_render.sh 逐字相同, 只改调度:
#  v2 两个毛病 (09-23 11:08 UTC 实测):
#   ① 只预取 1 间 coarse。官方 base_indoors.gin:32-33 max_tries=50000 下, 找不到 5 个机位的房间要搜满
#      ~37 分钟才报 "Could not find 5 camera views" (seed 100174 实例), 期间 GPU 空等。
#   ② 后台 coarse 失败后前台原样重试 —— 同 seed 结果确定 (100085 两次都 rc=139 于 94s), 白等。
#  v3: 失败 seed 落 $OUT/failed/<seed> 永不重试; 预取 K 间; 每路凑满 NEED 间成功, 自己的 18 个 seed 用完后
#      用本路专属溢出 seed 补 (官方 Infinigen 对失败场景同样是丢弃, 不修)。
#  接管: 可在 v2 运行中途接手 —— v2 的 bash 被杀后留下的 python 孤儿进程不杀, v3 按 seed 轮询等它们结束;
#      渲染按机位断点续 (c<k> 下 Image.png + camview.npz + Depth.npy 三件齐 = 该机位完成)。
set -u
W=768; H=576; OUTW=768; OUTH=576
OUT=${OUT:?}; DEST=${DEST:-/root/ig7_blend}; SEEDS=${SEEDS:?}; NEED=${NEED:-18}; K=${K:-2}
CONV=${CONV:-/root/infinigen_to_blend.py}; P=${P:-/root/ig_venv2/bin/python}; VP=${VP:-/venv/main/bin/python}; IG=${IG:-/root/infinigen}; NCAM=${NCAM:-30}
mkdir -p $OUT/work $OUT/logs $OUT/failed $DEST
LOG(){ echo "[$(date +%F' '%H:%M:%S)] $*" | tee -a $OUT/run.log; }
CFG="-g fast_solve.gin singleroom.gin multiview_stereo.gin"
BASE="-p compose_indoors.terrain_enabled=False
      execute_tasks.generate_resolution=($W,$H)
      get_sensor_coords.W=$W get_sensor_coords.H=$H
      camera.spawn_camera_rigs.n_camera_rigs=$NCAM
      compose_indoors.restrict_single_supported_roomtype=True"
QUAL="configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True"

is_done(){   [ -f $DEST/ig_$1/cams/pair.txt ]; }
is_failed(){ [ -f $OUT/failed/$1 ]; }
has_blend(){ [ -f $OUT/work/s$1/coarse/scene.blend ]; }
busy(){      pgrep -f -- "(--seed|--scan) $1( |\$)" >/dev/null; }   # 该 seed 任何 coarse/render/convert 还活着
coarse_busy(){ pgrep -f -- "--seed $1 --task coarse" >/dev/null; }

do_coarse(){ # 与 ig7_render.sh do_coarse 同一条命令; 失败 => 落 failed 标记, 不重试
  local s=$1 d=$OUT/work/s$1
  rm -rf $d; mkdir -p $d
  local T0=$(date +%s)
  nice -n 5 $P -m infinigen_examples.generate_indoors --seed $s --task coarse \
    --output_folder $d/coarse $CFG $BASE > $OUT/logs/coarse_$s.log 2>&1
  local rc=$? T1=$(date +%s)
  if [ $rc -ne 0 ] || [ ! -f $d/coarse/scene.blend ]; then
    LOG "coarse seed=$s 失败 rc=$rc ($((T1-T0))s) $(grep -h -o 'ValueError: .*' $OUT/logs/coarse_$s.log | tail -1)"
    touch $OUT/failed/$s; rm -rf $d; return 1
  fi
  LOG "coarse seed=$s ok $((T1-T0))s"
}
declare -A CPID
alive(){ [ -n "${1:-}" ] && [ -e /proc/$1 ] && ! grep -q "^State:.*Z" /proc/$1/status 2>/dev/null; }  # 僵尸算死
start_coarse(){ # 后台起 coarse (已完成/已失败/已有 blend/已在跑 就不起); 记 PID 防「python 还没起来就被判失败」的竞态
  local s=$1
  if is_done $s || is_failed $s || has_blend $s || coarse_busy $s || alive "${CPID[$s]:-}"; then return 0; fi
  ( do_coarse $s ) & CPID[$s]=$!
}
cam_done(){ local c=$OUT/work/s$1/c$2
  ls $c/rgb/frames/Image/*/Image_*.png $c/rgb/frames/camview/*/camview_*.npz $c/gt/frames/Depth/*/Depth_*.npy >/dev/null 2>&1; }
shoot(){ # 与 ig7_render.sh shoot 逐字相同
  local s=$1 k=$2 d=$OUT/work/s$1/c$2
  rm -rf $d; mkdir -p $d
  $P -m infinigen_examples.generate_indoors --seed $s --task render \
     --input_folder $OUT/work/s$s/coarse --output_folder $d/rgb/out \
     $CFG $BASE $QUAL "execute_tasks.camera_id=[$k,0]" \
     "full/render_image.passes_to_save=[]" > $d/rgb.log 2>&1 || return 1
  $P -m infinigen_examples.generate_indoors --seed $s --task render \
     --input_folder $OUT/work/s$s/coarse --output_folder $d/gt/out \
     $CFG $BASE "execute_tasks.camera_id=[$k,0]" \
     "render.render_image_func=@flat/render_image" > $d/gt.log 2>&1 || return 1
  find $d -name "Image_*.exr" -delete
  find $d -type f \( -name "SurfaceNormal*" -o -name "InstanceSegmentation*" -o -name "Flow*" \
       -o -name "ObjectSegmentation*" -o -name "Vector*" -o -name "Objects_*" -o -name "Depth_*.png" \) -delete
}
do_room(){ # 按机位断点续
  local s=$1 T0=$(date +%s) k skip=0
  for k in $(seq 0 $((NCAM-1))); do
    if cam_done $s $k; then skip=$((skip+1)); continue; fi
    shoot $s $k || LOG "  🔴 seed=$s cam=$k 渲染失败"
  done
  local ok=0; for k in $(seq 0 $((NCAM-1))); do cam_done $s $k && ok=$((ok+1)); done
  LOG "render seed=$s $(($(date +%s)-T0))s  完整机位=$ok/$NCAM (续跑跳过 $skip)"
  [ $ok -ge $NCAM ]
}
convert_room(){ # 与 ig7_render.sh convert_room 同一条命令
  local s=$1
  $VP "$CONV" --frames $OUT/work/s$s --out $DEST --scan $s \
      --out_w $OUTW --out_h $OUTH --min_frames 8 >> $OUT/logs/conv_$s.log 2>&1
  local rc=$?
  if [ $rc -eq 0 ] && [ -f $DEST/ig_$s/cams/pair.txt ]; then
    LOG "convert seed=$s ok -> $DEST/ig_$s ($(du -sh $DEST/ig_$s|cut -f1), $(head -1 $DEST/ig_$s/cams/pair.txt) 视角)"
    rm -rf $OUT/work/s$s; return 0
  fi
  LOG "🔴 convert seed=$s 失败 rc=$rc, 保留 $OUT/work/s$s 待查"; tail -8 $OUT/logs/conv_$s.log >> $OUT/run.log; return 1
}
count_done(){ local n=0 s; for s in $SEEDS; do is_done $s && n=$((n+1)); done; echo $n; }

cd $IG
LOG "==== v3 接管: NEED=$NEED K=$K seeds=[$(echo $SEEDS | awk '{print $1".."$NF}')] 已成 $(count_done) 间"
set -- $SEEDS; ALL=("$@")
for idx in "${!ALL[@]}"; do
  s=${ALL[$idx]}
  [ $(count_done) -ge $NEED ] && break
  is_done $s && { busy $s || rm -rf $OUT/work/s$s; continue; }
  is_failed $s && continue
  # 预取: 当前这间 + 后面 K 个待办 seed
  start_coarse $s; n=0
  for s2 in "${ALL[@]:$((idx+1))}"; do
    [ $n -ge $K ] && break
    is_done $s2 || is_failed $s2 || { start_coarse $s2; n=$((n+1)); }
  done
  while busy $s || alive "${CPID[$s]:-}"; do sleep 10; done   # 等本 seed 的 coarse(含自己的子 shell) / v2 孤儿 render / 孤儿 convert 全部结束
  is_done $s && { rm -rf $OUT/work/s$s; LOG "seed=$s 由接管前的孤儿进程转换完成"; continue; }
  if ! has_blend $s; then is_failed $s || { touch $OUT/failed/$s; LOG "coarse seed=$s 失败 (接管前孤儿进程, 无 scene.blend)"; }; continue; fi
  if do_room $s; then convert_room $s; else LOG "🔴 seed=$s 产物不全, 跳过转换"; fi
  LOG "进度 $(count_done)/$NEED | 全箱成品 $(ls $DEST | wc -l) 间 $(du -sh $DEST | cut -f1)"
done
LOG "==== v3 结束: 本路成品 $(count_done)/$NEED, 失败 seed: $(ls $OUT/failed | tr '\n' ' ')"
