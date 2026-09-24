#!/bin/bash
# ============================================================================
# Infinigen Indoors = 第七域   开渲脚本
# 🔴 先跑 `./ig7_render.sh smoke` (1 间 x 3 机位, 约 12 分钟) 验通链路, 再跑 run。
#
# 每一条配置的出处 (禁止自研, 全部落到源码行号):
#  画质 configure_render_cycles.num_samples=8192   core/init.py:223
#       configure_render_cycles.denoise=True       core/init.py:216-221 (True 时选 OPTIX 去噪器)
#       ★ 8192 本来就是 configs_nature/base.gin:27 的出厂值; denoise 出厂 False
#         (base.gin:29, configs_indoor/base_indoors.gin:43 又写一遍) => 本档唯一改动是 denoise
#       ★ adaptive_threshold 保持 base_indoors.gin:44 的 0.005 不动; 实测日志里
#         每帧都跑满 "Sample 8192/8192", 自适应没提前收手。
#  分辨率 execute_tasks.generate_resolution        configs_nature/base.gin:62 (出厂 1280x720)
#         落点 core/execute_tasks.py:235-236 -> scene.render.resolution_x/y
#       ★ coarse 和 render 必须传【同一个】值:相机 sensor 在 coarse 期由
#         spawn_camera -> adjust_camera_sensor 写死 (core/placement/camera.py:103-110, 117),
#         render 期只改 scene.render.resolution 不重算 sensor。
#       ★ 绝不用 render_image.render_resolution_override (rendering/render.py:553-555):
#         它只改分辨率 => core/util/camera.py:33-37 抛 ValueError。报错点在
#         render.py:571 save_camera_parameters,在渲染【之后】=> 彩图渲完了但
#         camview_*.npz 没写出,且后面的 postprocess 和 reorganize_old_framesfolder 全没跑。
#       ★ 官方自证非 16:9 可行: configs_indoor/topview.gin:1 = (720,720)。
#         4:3 走 adjust_camera_sensor 得 sensor_width = 18*(4/3) = 24.0 整数,通过 assert。
#  机位 camera.spawn_camera_rigs.n_camera_rigs      docs/source/ConfiguringCameras.md:99 官方 MVS 档 = 30
#       multiview_stereo.gin -> configure_cameras.mvs_setting=True
#                               (configs_nature/multiview_stereo.gin:4 -> placement/camera.py:682)
#       🔴 configure_cameras.mvs_radius 本脚本【故意不设】—— 用 configs_indoor/base_indoors.gin:72
#          的官方默认 ("uniform", 1, 2) m。自己填大值会让 keep_cam_pose_proposal
#          在单间里找不到合法位姿,camera_pose_proposal 空转十几分钟。
#       选机位 execute_tasks.camera_id=[k,0]        configs_nature/base.gin:12
#  房型 compose_indoors.restrict_single_supported_roomtype=True
#       官方 mvs_indoors 命令里就有 (ConfiguringCameras.md:99)。
#       generate_indoors.py:170-182: 只从 Bedroom/LivingRoom/Kitchen/Bathroom/DiningRoom
#       这 5 种【写了家具约束的】房型里随机挑一种。不加这条, singleroom 可能抽到
#       车库/办公室/阳台 —— 源码注释原话是那些房型会 "empty-ish", 空房间 = 白墙无纹理 = 废数据。
#  通道 full/render_image.passes_to_save=[]         官方自证 configs_nature/asset_demo.gin:9
#       (出厂 base.gin:39-54 存 14 个 AOV,MVS 一个都不用;实测省 9.4% 时间 + 60% 磁盘)
#  深度 render.render_image_func=@flat/render_image  官方 datagen/job_funcs.py:443
#       flat scope = base.gin:37-38 (override_num_samples=16, flat_shading=True)
#                  + base.gin:55-60 (passes_to_save 含 ['z','Depth'])
#       官方把这一趟放 CPU: datagen/configs/compute_platform/local_256GB.gin:45-46
#       (render_type="flat", gpus=0)。本脚本留在 GPU —— 实测只要 4-6 秒,不值得另开 CPU 档。
#       ★ 本机没编 customgt (src/infinigen/datagen/customgt/build/customgt 不存在),
#         所以 Depth 是 H x W (实测),不是 GroundTruthAnnotations.md:92 说的 2H x 2W ——
#         那是 opengl_gt 那条路。要 2x 深度得先编 customgt,是额外代价。
#       ★ 没命中的像素 = 1e10 哨兵 (实测占 3.5%),转换器按 --max_depth 掩掉。
# ============================================================================
set -u

# --------------------------------- 旋钮 -----------------------------------
# 分辨率: 两个选项, 中间挡位和更高都不值。1536x1152 = 训练尺寸 768x576 的【整数 2 倍】。实测降采样回 768x576 后
#   高频(Laplacian 均值)比原生 768 渲染高 15.2%,而 2048x1536 再往上已经饱和
#   (1536降采样 vs 2048降采样 PSNR 40.9 dB = 基本同一张图)。1024x768 因为不是整数比
#   反而比原生还糊 (高频比 0.908)。=> 要么 768x576 原生,要么 1536x1152,中间和更高都不值。
#   🔴 代价是 2.80 倍 GPU 时间 (实测每可用帧 185s vs 66s, 含深度真值那一趟)。
#      同机时下 768 原生能多出 2.8 倍房间。默认给 768x576;
#      要买那 +15.2% 锐度就把这两个数改成 1536 1152 (OUTW/OUTH 保持 768/576 不动)。
W=${W:-768}; H=${H:-576}
NCAM=${NCAM:-30}                  # 每间机位数 (官方 MVS 档)
PAR=${PAR:-1}                     # 🔴 实测并行【负收益】: 空箱 N=1 = 63 秒/帧, N=2/3/4 单帧等效
                                  #    73.0/73.7/73.5 秒。5090 在 N=1 就已经算满 (GPU 均值 83%,
                                  #    N=2 起就是 98-99%)。PAR>1 只多占显存 (线性 4.62 GB/路) 还更慢。
ROOMS=${ROOMS:-300}
SEED0=${SEED0:-100000}            # 起始 seed (避开探枪用过的 0..)
OUT=${OUT:-/root/ig7}
DEST=${DEST:-/root/ig7_blend}     # 🔴 成品先落这里,不直接写 /root/monotrain
CONV=${CONV:-/root/infinigen_to_blend.py}
# 🔴 落盘尺寸必须是 768x576, 不是可选项:
#    datasets/blend.py:107-115 的 __getitem__ 读 jpg 后【不做任何 resize】, 直接 stack;
#    EqualDomainSampler (domain_sampler.py:102) 把七个域洗在同一个 batch 里,
#    默认 collate 要求同一 batch 内形状一致 => 七个域必须同分辨率。
#    实测六个现役域 (sp_/ak_/gso_/ta_/tg_/blendedmvg) 落盘的 jpg 和 pfm 【文件尺寸】全部是
#    768x576 (注意: 文件尺寸 != 信息量, 其中几个域是从更低分辨率升采上来的; 这里要对齐的
#    恰恰是文件尺寸, 因为 collate 只看 tensor 形状)。
OUTW=${OUTW:-768}; OUTH=${OUTH:-576}
# --------------------------------------------------------------------------

P=/root/ig_venv2/bin/python
VP=/venv/main/bin/python
IG=/root/infinigen
mkdir -p $OUT/queue $OUT/work $OUT/logs $DEST
LOG(){ echo "[$(date +%F' '%H:%M:%S)] $*" | tee -a $OUT/run.log; }

CFG="-g fast_solve.gin singleroom.gin multiview_stereo.gin"
BASE="-p compose_indoors.terrain_enabled=False
      execute_tasks.generate_resolution=($W,$H)
      get_sensor_coords.W=$W get_sensor_coords.H=$H
      camera.spawn_camera_rigs.n_camera_rigs=$NCAM
      compose_indoors.restrict_single_supported_roomtype=True"
QUAL="configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True"

# ---------- 一间房的 coarse (纯 CPU) --------------------------------------
do_coarse(){ # $1=seed
  local s=$1 d=$OUT/work/s$1
  [ -f $d/coarse/scene.blend ] && return 0
  rm -rf $d; mkdir -p $d
  local T0=$(date +%s)
  nice -n 5 $P -m infinigen_examples.generate_indoors --seed $s --task coarse \
    --output_folder $d/coarse $CFG $BASE > $OUT/logs/coarse_$s.log 2>&1
  local rc=$? T1=$(date +%s)
  if [ $rc -ne 0 ]; then
    LOG "coarse seed=$s 失败 rc=$rc ($((T1-T0))s)"; tail -6 $OUT/logs/coarse_$s.log >> $OUT/run.log
    rm -rf $d; return 1
  fi
  LOG "coarse seed=$s ok $((T1-T0))s"
  return 0
}

# ---------- 一个机位: 彩图 + 深度 -----------------------------------------
shoot(){ # $1=seed $2=k
  local s=$1 k=$2 d=$OUT/work/s$1/c$2
  mkdir -p $d
  $P -m infinigen_examples.generate_indoors --seed $s --task render \
     --input_folder $OUT/work/s$s/coarse --output_folder $d/rgb/out \
     $CFG $BASE $QUAL "execute_tasks.camera_id=[$k,0]" \
     "full/render_image.passes_to_save=[]" > $d/rgb.log 2>&1 || return 1
  $P -m infinigen_examples.generate_indoors --seed $s --task render \
     --input_folder $OUT/work/s$s/coarse --output_folder $d/gt/out \
     $CFG $BASE "execute_tasks.camera_id=[$k,0]" \
     "render.render_image_func=@flat/render_image" > $d/gt.log 2>&1 || return 1
  # 立刻删 MVS 用不到的大件: Image.exr 是 Image.png 的 HDR 副本(占 90% 体积);
  # GT 的法线/光流/两种分割都不训练用。删完每视角只剩 Image.png + camview.npz + Depth.npy。
  find $d -name "Image_*.exr" -delete
  find $d -type f \( -name "SurfaceNormal*" -o -name "InstanceSegmentation*" -o -name "Flow*" \
       -o -name "ObjectSegmentation*" -o -name "Vector*" -o -name "Objects_*" -o -name "Depth_*.png" \) -delete
  return 0
}

# ---------- 一间房的全部机位 ----------------------------------------------
do_room(){ # $1=seed  $2=机位数
  # 🔴 不能用 `jobs -rp` 数并发: run 里还挂着一个后台 coarse, 会被一起数进来、
  #    也会被结尾的裸 `wait` 等上, 把 CPU/GPU 流水线重叠打掉。只认自己记下的 PID。
  local s=$1 n=$2 T0=$(date +%s) k p
  local RUN=""
  for k in $(seq 0 $((n-1))); do
    if [ "$PAR" -le 1 ]; then
      shoot $s $k || LOG "  🔴 seed=$s cam=$k 渲染失败"
    else
      shoot $s $k & RUN="$RUN $!"
      while [ $(set -- $RUN; echo $#) -ge $PAR ]; do
        local ALIVE=""
        for p in $RUN; do kill -0 $p 2>/dev/null && ALIVE="$ALIVE $p"; done
        RUN=$ALIVE
        [ $(set -- $RUN; echo $#) -ge $PAR ] && sleep 2
      done
    fi
  done
  for p in $RUN; do wait $p; done
  local T1=$(date +%s)
  local nkv=$(find $OUT/work/s$s -name "camview_*.npz" | wc -l)
  local ndp=$(find $OUT/work/s$s -name "Depth_*.npy"  | wc -l)
  LOG "render seed=$s $((T1-T0))s  camview=$nkv/$n  depth=$ndp/$n"
  [ "$nkv" -ge "$n" ] && [ "$ndp" -ge "$n" ]
}

# ---------- 转换 + 清场 ----------------------------------------------------
convert_room(){ # $1=seed
  local s=$1
  if [ ! -f "$CONV" ]; then LOG "⚠ 没有 $CONV, 保留原始产物"; return 1; fi
  $VP "$CONV" --frames $OUT/work/s$s --out $DEST --scan $s \
      --out_w $OUTW --out_h $OUTH --min_frames 8 \
      >> $OUT/logs/conv_$s.log 2>&1
  local rc=$?
  if [ $rc -eq 0 ] && [ -f $DEST/ig_$s/cams/pair.txt ]; then
    LOG "convert seed=$s ok -> $DEST/ig_$s ($(du -sh $DEST/ig_$s|cut -f1), $(head -1 $DEST/ig_$s/cams/pair.txt) 视角)"
    rm -rf $OUT/work/s$s        # 🔴 只有转换成功才删
    return 0
  fi
  LOG "🔴 convert seed=$s 失败 rc=$rc, 保留 $OUT/work/s$s 待查"; tail -8 $OUT/logs/conv_$s.log >> $OUT/run.log
  return 1
}

cd $IG
case "${1:-run}" in
  smoke)
    LOG "SMOKE: 1 间 x 3 机位 @ ${W}x${H}, 全链路自证"
    s=$SEED0
    do_coarse $s || exit 1
    do_room $s 3 || { LOG "🔴 smoke 渲染产物不全"; exit 1; }
    $VP - $OUT/work/s$s $W $H <<'PY'
import sys,glob,numpy as np
d,W,H=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
cs=sorted(glob.glob(d+"/**/camview_*.npz",recursive=True))
ds=sorted(glob.glob(d+"/**/Depth_*.npy",recursive=True))
print("  camview=%d  depth=%d"%(len(cs),len(ds)))
exp=15.0*W/(18.0*(W/H)); locs=[]
for f in cs:
    z=np.load(f);K=z["K"];T=z["T"];locs.append(T[:3,3])
    ok=abs(K[0,0]-exp)<1e-3 and abs(K[0,2]-W/2)<1e-6 and abs(K[1,2]-H/2)<1e-6 and tuple(z["HW"])==(H,W)
    print("   %s fx=%.2f cx=%.1f cy=%.1f HW=%s -> %s"%(f.split('/')[-1],K[0,0],K[0,2],K[1,2],tuple(z["HW"]),"OK" if ok else "!!! 不合法"))
L=np.array(locs); import itertools
dd=[np.linalg.norm(a-b) for a,b in itertools.combinations(L,2)]
print("   机位两两距离 min=%.3f 中位=%.3f max=%.3f m -> %s"%(min(dd),np.median(dd),max(dd),
      "互异 OK" if min(dd)>1e-3 else "!!! 机位重合"))
for f in ds:
    a=np.load(f); m=a<1e9
    print("   %s %s 有效=%.3f 深度 %.2f-%.2f m"%(f.split('/')[-1],a.shape,m.mean(),a[m].min(),a[m].max()))
PY
    convert_room $s && LOG "SMOKE 通过" || LOG "🔴 SMOKE 转换未通过"
    ;;
  run)
    LOG "开渲 ${ROOMS} 间 x ${NCAM} 机位 @ ${W}x${H}, 8192+去噪, PAR=$PAR"
    LOG "seed $SEED0..$((SEED0+ROOMS-1)) | 工作区 $OUT | 成品 $DEST -> ig_<seed>"
    # coarse(CPU) 与 render(GPU) 流水线重叠: 先把下一间的 coarse 甩到后台再渲当前这间
    NEXTPID=""
    for s in $(seq $SEED0 $((SEED0+ROOMS-1))); do
      if [ -n "$NEXTPID" ]; then wait $NEXTPID || true; NEXTPID=""; fi
      if [ ! -f $OUT/work/s$s/coarse/scene.blend ]; then
        do_coarse $s || continue
      fi
      n=$((s+1))
      if [ $n -lt $((SEED0+ROOMS)) ]; then do_coarse $n & NEXTPID=$!; fi
      if do_room $s $NCAM; then convert_room $s; else LOG "🔴 seed=$s 产物不全, 跳过转换"; fi
      LOG "进度 $((s-SEED0+1))/$ROOMS | 成品 $(ls $DEST 2>/dev/null|wc -l) 间 $(du -sh $DEST 2>/dev/null|cut -f1) | 剩余磁盘 $(df -h /root|tail -1|awk '{print $4}')"
    done
    LOG "结束。成品 $(ls $DEST|wc -l) 间, $(du -sh $DEST|cut -f1)"
    ;;
  *) echo "用法: $0 [smoke|run]"; exit 2 ;;
esac
