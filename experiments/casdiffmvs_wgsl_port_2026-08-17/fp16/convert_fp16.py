#!/usr/bin/env python3
"""fp32 → fp16 ONNX 转换(onnxconverter_common.float16)。

用法: python convert_fp16.py --in X.onnx --out X_fp16.onnx [--block Op1,Op2]
keep_io_types=True:IO 保持 fp32,壳/harness 喂数零改动。
"""
import argparse
import onnx
from onnxconverter_common import float16

ap = argparse.ArgumentParser()
ap.add_argument("--inp", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--block", default="", help="逗号分隔的 op_block_list 追加项")
a = ap.parse_args()

# ⚠️ occ 1.16.0 已知 bug:remove_unnecessary_cast_node 在 Cast 直连图输出时
#    拿到 list 而非 node,AttributeError。绕行 = 跳过该清理(只留冗余 Cast 对,
#    ORT 图优化会折叠,数值无影响)。
float16.remove_unnecessary_cast_node = lambda graph: None

m = onnx.load(a.inp)
extra = [s for s in a.block.split(",") if s]
block = list(float16.DEFAULT_OP_BLOCK_LIST) + extra
print("默认 block list:", sorted(float16.DEFAULT_OP_BLOCK_LIST))
if extra:
    print("追加 block:", extra)
m16 = float16.convert_float_to_float16(
    m, keep_io_types=True, op_block_list=block, disable_shape_infer=False)
onnx.save(m16, a.out)
import os
print(f"✅ {a.out}  {os.path.getsize(a.out)/1e6:.1f} MB "
      f"(原 {os.path.getsize(a.inp)/1e6:.1f} MB)")
