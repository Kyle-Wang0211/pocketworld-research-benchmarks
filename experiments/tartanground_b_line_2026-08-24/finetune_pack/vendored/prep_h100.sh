#!/usr/bin/env bash
# 上机第一步:环境体检 + 仓库准备 + dataloader 补丁
#
# 用法:  MVG_ROOT=/data/BlendedMVG ./prep_h100.sh
#
# 做四件事,每件都会在不满足时**直接报错停下**,而不是让你跑到第 3 小时才发现。
set -euo pipefail
DIFFMVS_DIR="${DIFFMVS_DIR:-$HOME/diffmvs}"

echo "════════ 1. 机器体检 ════════"
GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
NCPU=$(nproc)
RAM=$(free -g | awk '/^Mem:/{print $2}')
echo "GPU     : $GPU_NAME  ${GPU_MEM} MiB"
echo "内存    : ${RAM} GB"
echo "vCPU    : $NCPU"
echo "盘      : $(df -h "${MVG_ROOT:-${MVS_ROOT:-/}}" | tail -1 | awk '{print $4}') 可用"

# 挑机优先级(⚠️ 已修正:内存排第一,不是 vCPU)
#   预解码缓存(predecode_blend.py)把 JPEG 解码从每轮都做变成只做一次,
#   之后全走 mmap + OS 页缓存 ⇒ **内存够大就等于没有 CPU 瓶颈**。
#   所以 vCPU 从"硬门槛"降级成"第一轮快慢"。
if [ "$RAM" -lt 200 ]; then
  echo "🔴 内存只有 ${RAM}GB。预解码缓存要整份驻留在页缓存里才有意义;"
  echo "   装不下就会反复回盘,CPU/IO 瓶颈原样回来。目标 ≥200GB。"
fi
if [ "$GPU_MEM" -lt 70000 ]; then
  echo "🔴 显存 ${GPU_MEM}MiB < 70GB。40GB 卡并发不了多配置,单卡方案的全部优势来自显存。"
fi
if [ "$NCPU" -lt 24 ]; then
  echo "⚠️ vCPU 只有 $NCPU。有缓存后它只影响**预解码那一次**与第一轮,不是硬门槛,"
  echo "   但预解码会比较慢。"
fi

echo
echo "════════ 2. 仓库 ════════"
if [ ! -d "$DIFFMVS_DIR" ]; then
  echo "clone cvg/diffmvs → $DIFFMVS_DIR"
  git clone https://github.com/cvg/diffmvs.git "$DIFFMVS_DIR"
fi
cd "$DIFFMVS_DIR"
python -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available())"

echo
echo "════════ 3. dataloader 补丁(train.py:357-360)════════"
# 官方把 num_workers=8 硬编码。H100 + 64vCPU 下 8 个 worker 喂不饱卡。
# ⚠️ 三处改动**全部只影响吞吐,不影响数值**:
#      num_workers      : 读数据的进程数
#      persistent_workers: 每个 epoch 不重建 worker(BlendedMVG 场景多,重建开销可观)
#      pin_memory        : 锁页内存,H2D 拷贝更快
#    喂给模型的样本内容与顺序完全不变(shuffle 由 seed 决定,见 train.py:301)。
if grep -q "NUM_WORKERS" train.py; then
  echo "补丁已在,跳过"
else
  cp train.py train.py.orig
  python - <<'PY'
import re
src = open("train.py").read()
old_train = """    TrainImgLoader = DataLoader(train_dataset, args.batch_size,
                                shuffle=True, num_workers=8, drop_last=True)"""
old_test = """    TestImgLoader = DataLoader(test_dataset, args.batch_size,
                                shuffle=False, num_workers=8, drop_last=False)"""
assert old_train in src, "train.py 的 TrainImgLoader 段与预期不符,别盲改 —— 手工核对"
assert old_test in src, "train.py 的 TestImgLoader 段与预期不符,别盲改 —— 手工核对"
nw = '    _NW = int(os.environ.get("NUM_WORKERS", "8"))\n'
new_train = nw + """    TrainImgLoader = DataLoader(train_dataset, args.batch_size,
                                shuffle=True, num_workers=_NW, drop_last=True,
                                persistent_workers=_NW > 0, pin_memory=True)"""
new_test = """    TestImgLoader = DataLoader(test_dataset, args.batch_size,
                                shuffle=False, num_workers=_NW, drop_last=False,
                                persistent_workers=_NW > 0, pin_memory=True)"""
src = src.replace(old_train, new_train).replace(old_test, new_test)
open("train.py","w").write(src)
print("✅ 已打补丁(原文件存为 train.py.orig)")
PY
fi
python -c "import ast;ast.parse(open('train.py').read());print('train.py 语法 OK')"

echo
echo "════════ 4. 数据体检 ════════"
if [ -z "${MVG_ROOT:-}" ]; then
  echo "⚠️ 未设 MVG_ROOT,跳过。下完数据后跑:"
  echo "   python3 make_blendmvg_list.py \$MVG_ROOT \$LISTS_DIR"
else
  echo "BlendedMVG 根目录 : $MVG_ROOT"
  echo "场景目录数        : $(find "$MVG_ROOT" -maxdepth 1 -mindepth 1 -type d | wc -l)"
  echo "实际体积          : $(du -sh "$MVG_ROOT" 2>/dev/null | cut -f1)"
  echo
  echo "🔴 下一步必须跑全量体检(不是抽查):"
  echo "   python3 $(dirname "$0")/make_blendmvg_list.py $MVG_ROOT \$LISTS_DIR"
  echo "   理由:datasets/blend.py 在 __getitem__ 里才拼路径,缺文件要等训练跑到"
  echo "   那个样本才炸。几十 GB 下载出现零星缺文件很常见,在 H100 上跑到第 3 小时"
  echo "   才崩是最贵的失败方式。"
fi
echo
echo "════════ 5. 装 blend_cached 数据集 ════════"
HERE="$(cd "$(dirname "$0")" && pwd)"
cp "$HERE/blend_cached.py" "$DIFFMVS_DIR/datasets/"
python -c "import ast;ast.parse(open('$DIFFMVS_DIR/datasets/blend_cached.py').read())"
echo "✅ → $DIFFMVS_DIR/datasets/blend_cached.py"
echo "   训练时传 --dataset=blend_cached(train_blendmvg_scratch.sh 会按 BLEND_CACHE 自动选)"

cat <<'NEXT'

✅ prep 完成。接下来:

  ① 预解码(消除 CPU 瓶颈,一次性)
     python3 predecode_blend.py $MVS_ROOT $DIFFMVS_DIR/lists/blend/train.txt \
             $CACHE_DIR --nviews 9 --depth --repo $DIFFMVS_DIR
     🔴 跑完看它报的合计体积,必须明显小于 free -g 的 available

  ② pilot 试跑(量 it/s 与显存,决定并发几个 + 真实时长)
     BLEND_CACHE=$CACHE_DIR TIER=mvs MVS_ROOT=... ./train_blendmvg_scratch.sh pilot

  ③ 段① 并发四配置 → ④ 评测选赢家 → ⑤ 建 MVG 清单 → ⑥ 段② 微调
NEXT
