#!/usr/bin/env bash
# 新机器一条命令:环境 → 数据 → 缓存 → batch 扫描 → 出对比数字
#
#   scp bootstrap_and_bench.sh blend_cached.py predecode_blend.py root@HOST:/workspace/
#   ssh root@HOST 'tmux new -d -s bs "bash /workspace/bootstrap_and_bench.sh > /workspace/bs.log 2>&1"'
#
# 约 20 分钟(其中下载约 4 分钟 @126MB/s、解压约 5 分钟、预解码 <1 分钟)。
#
# 目的:回答"这台卡在我们这个负载上到底多快",与 H200 基准并排比:
#     H200 NVL:  batch4 = 8.5 样本/秒 | batch8 = 9.4 | batch16 = 10.2 | batch32 = OOM
#
# ⚠️ 本负载是**延迟受限**(每次前向 7 步串行 GRU + 扩散采样),
#    不吃张量核心也不吃 HBM 带宽 ⇒ 高主频的便宜卡可能更快。这个脚本就是去证伪的。
set -uo pipefail
W=/workspace
LOGP() { echo; echo "════════ $* ════════"; }

LOGP "0. 机器体检"
nvidia-smi --query-gpu=name,memory.total,clocks.max.graphics --format=csv,noheader
echo "nproc=$(nproc)  (⚠️ 容器里这是宿主机值)"
# 真实配额在 cgroup v1;v2 路径在 vast 的容器里读不到
Q=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null || echo -1)
P=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us 2>/dev/null || echo 100000)
[ "$Q" -gt 0 ] && echo "真实 CPU 配额 = $(echo "scale=1; $Q/$P" | bc) 核"
M=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || echo 0)
[ "$M" -gt 0 ] && echo "真实内存配额 = $((M/1024/1024/1024)) GiB"
df -h / | tail -1

LOGP "1. Python 环境"
source /venv/main/bin/activate 2>/dev/null || true
# ⚠️ 仓库 requirements 钉 torch==2.0.0,实测不必遵守;新版对 sm_90/sm_120 更好
python -c "import torch" 2>/dev/null || uv pip install -q torch torchvision
uv pip install -q timm numpy pillow opencv-python-headless plyfile tensorboardX einops

# 🔴 驱动/torch 版本必须匹配,而且**自检失败要当场停**。
#    实测踩过:一台机器驱动只到 CUDA 12.8,装的却是 cu130 的 torch;
#    因为本脚本只有 `set -uo pipefail` 没有 `set -e`,自检失败后一路跑到
#    BOOTSTRAPDONE,直到真开训练才报 "NVIDIA driver is too old" ——
#    白等了整个下载+预解码。下面这段会在版本不匹配时自动换装并重验,仍失败则退出。
gpu_ok() { python -c "
import torch,sys
if not torch.cuda.is_available(): sys.exit(1)
a=torch.randn(2048,2048,device='cuda'); (a@a).sum().item()
print('torch', torch.__version__, '| cuda', torch.version.cuda, '|',
      torch.cuda.get_device_name(0), '| cap', torch.cuda.get_device_capability(0))
" 2>/dev/null; }
if ! gpu_ok; then
  DRV=$(nvidia-smi | grep -o 'CUDA Version: [0-9.]*' | grep -o '[0-9.]*')
  echo "⚠️ GPU 自检失败,驱动只到 CUDA $DRV —— 换装匹配的 torch"
  case "$DRV" in
    12.*) IDX=https://download.pytorch.org/whl/cu128 ;;
    *)    IDX=https://download.pytorch.org/whl/cu126 ;;
  esac
  uv pip install -q --reinstall torch torchvision --index-url "$IDX"
  gpu_ok || { echo "🔴 换装后仍失败,停。手工处理驱动/torch 匹配。"; exit 1; }
  echo "⚠️ 本机 torch 版本与其他机器不同 —— **这是第二变量,必须记账**"
fi

LOGP "2. 仓库 + 补丁"
cd $W
[ -d diffmvs ] || git clone -q https://github.com/cvg/diffmvs.git
cd diffmvs
if ! grep -q NUM_WORKERS train.py; then
  cp train.py train.py.orig
  python - <<'PY'
src=open("train.py").read()
ot="""    TrainImgLoader = DataLoader(train_dataset, args.batch_size,
                                shuffle=True, num_workers=8, drop_last=True)"""
oe="""    TestImgLoader = DataLoader(test_dataset, args.batch_size,
                                shuffle=False, num_workers=8, drop_last=False)"""
assert ot in src and oe in src, "train.py 与预期不符,停 —— 别盲改"
nw='    _NW = int(os.environ.get("NUM_WORKERS", "8"))\n'
src=src.replace(ot, nw+"""    TrainImgLoader = DataLoader(train_dataset, args.batch_size,
                                shuffle=True, num_workers=_NW, drop_last=True,
                                persistent_workers=_NW > 0, pin_memory=True)""")
src=src.replace(oe,"""    TestImgLoader = DataLoader(test_dataset, args.batch_size,
                                shuffle=False, num_workers=_NW, drop_last=False,
                                persistent_workers=_NW > 0, pin_memory=True)""")
open("train.py","w").write(src); print("dataloader 补丁 OK")
PY
fi
cp $W/blend_cached.py datasets/ && echo "blend_cached 已装"

LOGP "3. 数据(GitHub Releases,16 个分卷)"
# ⚠️ 只下 BlendedMVS.zip 会得到 281MB 的分卷描述符,不是数据本体
mkdir -p $W/data && cd $W/data
if [ ! -d BlendedMVS ]; then
  B=https://github.com/YoYo000/BlendedMVS/releases/download/v1.0.0
  printf "%s\n" BlendedMVS.zip $(seq -f "BlendedMVS.z%02g" 1 15) \
    | xargs -P 6 -I{} wget -q -c "$B/{}" -O "{}"
  echo "下载完成 $(du -sh . | cut -f1)"
  command -v zip >/dev/null || (apt-get -qq update >/dev/null && apt-get -qq install -y zip >/dev/null)
  zip -q -s 0 BlendedMVS.zip --out combined.zip
  rm -f BlendedMVS.z?? BlendedMVS.zip
  unzip -q combined.zip && rm -f combined.zip
fi
echo "场景数 $(find BlendedMVS -maxdepth 1 -mindepth 1 -type d | wc -l) (应为 113)"

LOGP "4. 预解码缓存"
# 内存紧的机器传 NO_DEPTH_CACHE=1:只缓存图像(20.9 GiB 而非 48.7)。
# JPEG 解码才是 CPU 大头,深度 PFM 是 I/O ⇒ 少缓存深度损失小。
# 判据:缓存必须能整份留在页缓存里,否则反复回盘,等于白做。
mkdir -p $W/cache
DEPTH_FLAG="--depth"
[ "${NO_DEPTH_CACHE:-0}" = "1" ] && DEPTH_FLAG="" && echo "⚠️ 内存受限模式:只缓存图像,不缓存深度"
if [ ! -f $W/cache/images.json ]; then
  cd $W/diffmvs
  python -u $W/predecode_blend.py $W/data/BlendedMVS \
      $W/diffmvs/lists/blend/train.txt $W/cache --nviews 9 $DEPTH_FLAG --repo $W/diffmvs
fi
du -sh $W/cache
AVAIL=$(free -g | awk '/^Mem:/{print $7}')
CSZ=$(du -sB1 $W/cache | cut -f1); CSZ=$((CSZ/1024/1024/1024))
echo "缓存 ${CSZ} GiB / 可用内存 ${AVAIL} GiB"
[ "$CSZ" -gt "$((AVAIL*7/10))" ] && echo "🔴 缓存超过可用内存 70%,页缓存可能留不住 —— 考虑 NO_DEPTH_CACHE=1"

if [ "${SKIP_SWEEP:-0}" = "1" ]; then
  echo; echo "════════ 跳过 batch 扫描(SKIP_SWEEP=1),环境已就绪 ════════"
  echo "BOOTSTRAPDONE"; exit 0
fi

LOGP "5. batch 扫描(与 H200 同口径)"
cd $W/diffmvs
for B in 4 8 16; do
  echo "── batch=$B ──"
  NUM_WORKERS=16 BLEND_CACHE=$W/cache timeout 240 python -u train.py \
    --mode=train --dataset=blend_cached --trainpath=$W/data/BlendedMVS \
    --trainlist lists/blend/train.txt --testlist lists/blend/val.txt \
    --batch_size=$B --trainviews=9 --testviews=9 --numdepth=384 --numdepth_initial=48 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --min_radius 0.125 --max_radius 8 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --lr_sche onecycle --conf_weight 0.05 \
    --logdir $W/runs/sw_b$B --epochs=16 --train_epochs=1 --lr=0.001 \
    --scale 0 0.25 0.05 > $W/sw_b$B.log 2>&1
  grep "time = " $W/sw_b$B.log | tail -40 | sed 's/.*time = //' \
    | awk -v b=$B '{s+=$1;n++} END {if(n>0) printf "  %.3f s/iter ⇒ %.1f 样本/秒\n", s/n, b*n/s; else print "  无数据(OOM?)"}'
  grep -iE "out of memory" $W/sw_b$B.log | head -1
done

LOGP "结果对照"
cat <<'CMP'
  H200 NVL 基准:  batch4 8.5 | batch8 9.4 | batch16 10.2 样本/秒(batch32 OOM)
  段① 时长 = 96 轮 × 4218 iter × batch4 ÷ (样本/秒 ÷ 4)
             A+B 两个配置 = 40 轮
CMP
python - <<'PY'
import re,os
r={}
for b in (4,8,16):
    p=f"/workspace/sw_b{b}.log"
    if not os.path.exists(p): continue
    t=[float(x) for x in re.findall(r"time = ([\d.]+)", open(p,errors="ignore").read())][-40:]
    if t: r[b]=b*len(t)/sum(t)
if r:
    best=max(r.values())
    print(f"  本机最佳 {best:.1f} 样本/秒(H200 最佳 10.2)⇒ 相对 {best/10.2:.2f}x")
    ep=4218*4/best/3600
    print(f"  每轮 {ep*60:.0f} 分钟 | A+B(40轮) {ep*40:.1f} h | 全四配置(96轮) {ep*96:.1f} h")
PY
echo "BOOTSTRAPDONE"
