#!/bin/bash
# Widen the voxel linear-index products in Open3D 0.20.0 kernel/VoxelBlockGridImpl.h from int32 to int64 (the file's own
# `using index_t = int;` overflows at 2^31/(res^3*3) blocks, see run_3mm segfault 2026-09-17). Nothing else changes.
set -euo pipefail
cd /root/Open3D; git checkout -q -- cpp/open3d/t/geometry/kernel/VoxelBlockGridImpl.h
F=cpp/open3d/t/geometry/kernel/VoxelBlockGridImpl.h
python3 - "$F" <<'PY'
import re,sys
p=sys.argv[1]; s=open(p).read(); n0=s
# workload sizes n = blocks * res^3 (ParallelFor takes int64)
s=re.sub(r"index_t n = (indices\.GetLength\(\)|n_blocks) \* resolution3;", r"int64_t n = static_cast<int64_t>(\1) * resolution3;", s)
# linear voxel index = block_idx * res^3 + voxel_idx
s=re.sub(r"index_t linear_idx = block_idx \* resolution3 \+ voxel_idx;", r"int64_t linear_idx = static_cast<int64_t>(block_idx) * resolution3 + voxel_idx;", s)
s=re.sub(r"(\n\s+)block_idx \* resolution3 \+ voxel_idx;", r"\1static_cast<int64_t>(block_idx) * resolution3 + voxel_idx;", s)
# neighbour linear index helpers return block_buf_idx * res^3 + ... -> int64 return, int64 product
s=re.sub(r"return block_buf_idx \* resolution3 \+", r"return static_cast<int64_t>(block_buf_idx) * resolution3 +", s)
s=re.sub(r"index_t linear_idx_i =", r"int64_t linear_idx_i =", s)
s=re.sub(r"index_t linear_idx =\n", r"int64_t linear_idx =\n", s)
s=re.sub(r"index_t linear_idx_k = GetLinearIdxAtP\(", r"int64_t linear_idx_k = GetLinearIdxAtP(", s)
s=re.sub(r"index_t color_linear_idx = linear_idx_k \* 3;", r"int64_t color_linear_idx = linear_idx_k * 3;", s)
# lambdas that compute a linear index must return int64 (they are declared `-> index_t`)
s=re.sub(r"\) -> index_t \{(\s*\n\s*index_t block_buf_idx)", r") -> int64_t {\1", s)
open(p,"w").write(s)
import difflib; d=[l for l in difflib.unified_diff(n0.splitlines(), s.splitlines(), lineterm="") if l.startswith(("+","-")) and not l.startswith(("+++","---"))]
print("\n".join(d)); print("changed lines:", len(d)//2)
PY
git diff --stat
# deps + configure + build the python wheel (CPU only, no GUI)
apt-get install -y -qq xorg-dev libxcb-shm0 libglu1-mesa-dev python3-dev libc++-dev libc++abi-dev libsdl2-dev ninja-build libxi-dev libtbb-dev libosmesa6-dev libudev-dev autoconf libtool > /root/o3d_apt.log 2>&1 || echo "apt had errors (see /root/o3d_apt.log)"
mkdir -p /root/Open3D/build && cd /root/Open3D/build
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_CUDA_MODULE=OFF -DBUILD_GUI=OFF -DBUILD_WEBRTC=OFF -DBUILD_EXAMPLES=OFF -DBUILD_UNIT_TESTS=OFF \
      -DBUILD_PYTHON_MODULE=ON -DPython3_EXECUTABLE=/root/venv_o3d/bin/python -DBUILD_ISPC_MODULE=OFF -DUSE_SYSTEM_TBB=OFF -DBUILD_SHARED_LIBS=OFF .. 
nice -n 10 ninja -j20 pip-package
ls -la /root/Open3D/build/lib/python_package/pip_package/*.whl
echo BUILD_DONE
