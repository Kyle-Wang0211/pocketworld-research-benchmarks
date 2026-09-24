#!/bin/bash
# ETH3D 阳性对照 —— 第 1 阶段: 取数据 + 建评测工具
# 🔴 ETH3D 是 CC BY-NC-SA: 仅用于内部评测, 绝不进训练、绝不进出货。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
export DEBIAN_FRONTEND=noninteractive
D=/root/eth3d; mkdir -p $D/dl
LOG "装依赖 (p7zip / PCL / Eigen)"
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq p7zip-full libpcl-dev libeigen3-dev >/dev/null 2>&1
LOG "  7z=$(which 7z) PCL=$(ls -d /usr/include/pcl-* 2>/dev/null | head -1) Eigen=$(ls -d /usr/include/eigen3 2>/dev/null)"
for f in multi_view_training_dslr_undistorted.7z multi_view_training_dslr_scan_eval.7z; do
  [ -f $D/dl/$f ] && { LOG "已有 $f"; continue; }
  LOG "下载 $f"
  curl -sS -o $D/dl/$f "https://www.eth3d.net/data/$f"
  LOG "  $(ls -la $D/dl/$f | awk "{printf \"%.2f GB\", \$5/1e9}")"
done
LOG "解压"
for f in $D/dl/*.7z; do 7z x -y -o$D "$f" >/dev/null 2>&1 || LOG "🔴 解压失败 $f"; done
LOG "目录结构:"
ls $D | head -20
echo "--- 场景数 ---"; ls -d $D/*/ 2>/dev/null | wc -l
LOG "建 ETH3D 官方评测器"
cd /root && [ -d multi-view-evaluation ] || git clone --depth 1 -q https://github.com/ETH3D/multi-view-evaluation.git
cd /root/multi-view-evaluation && cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null 2>&1 && cmake --build build -j 8 2>&1 | tail -3
ls -la /root/multi-view-evaluation/build/ETH3DMultiViewEvaluation 2>/dev/null || echo "🔴 评测器未生成"
touch /root/ETHPREP_DONE
