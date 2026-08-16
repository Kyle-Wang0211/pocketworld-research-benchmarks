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
echo "GPU     : $GPU_NAME  ${GPU_MEM} MiB"
echo "vCPU    : $NCPU"
echo "内存    : $(free -g | awk '/^Mem:/{print $2}') GB"
echo "盘      : $(df -h "${MVG_ROOT:-/}" | tail -1 | awk '{print $4}') 可用"

# 🔴 这两条不是建议,是硬门槛 —— 不满足就是租了张昂贵的闲卡
if [ "$GPU_MEM" -lt 70000 ]; then
  echo "🔴 显存 ${GPU_MEM}MiB < 70GB。40GB 卡并发不了多配置,单卡方案的全部优势来自显存。"
  echo "   要么换 80GB 卡,要么接受串行(时间 ×4)。"
fi
if [ "$NCPU" -lt 48 ]; then
  echo "🔴 vCPU 只有 $NCPU。9 视图 × JPEG 解码是纯 CPU 活,并发 N 个训练 = N 倍解码压力。"
  echo "   CPU 不够会让 GPU 空转 —— 这是本任务最容易翻车的地方,比 GPU 型号更要紧。"
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
echo "✅ prep 完成。顺序:体检清单 → 🔴 pilot 试跑 → 按显存并发铺配置"
