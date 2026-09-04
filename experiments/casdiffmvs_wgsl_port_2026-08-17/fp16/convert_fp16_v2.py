#!/usr/bin/env python3
"""fp16 转换第二轮:定向保 fp32。

病灶假设(第一轮 >1%像素 24.5%、p50 0.40% 的来源):
  ① warp 坐标链:grid ∈ [-1,1] 的 fp16 分辨率 ~4.9e-4 ⇒ 768px 下 ~0.2px 系统性抖动;
  ② 方差成本 mean(x²)−mean(x)² 与 384-bin softmax 回归的 fp16 归约/相消。

刀法:
  - node_block_list = 每个 GridSample 的 grid 输入向后切片(遇 Conv/激活/归一化即停,
    不进入网络本体)⇒ 几何算术全程 fp32;
  - op_block_list += GridSample/Softmax/ReduceSum/ReduceMean/Sqrt(共 246 节点,
    归约是访存瓶颈非算力瓶颈,代价小)。
"""
import sys, onnx
from onnxconverter_common import float16

float16.remove_unnecessary_cast_node = lambda graph: None  # occ 1.16 已知崩溃,绕行

SRC, DST = sys.argv[1], sys.argv[2]
m = onnx.load(SRC)
g = m.graph

produced = {}
for n in g.node:
    for o in n.output:
        produced[o] = n
inits = {t.name for t in g.initializer}
gin = {i.name for i in g.input}

STOP = {"Conv", "ConvTranspose", "Relu", "Sigmoid", "Tanh",
        "InstanceNormalization", "AveragePool", "MaxPool", "Softmax"}

block_nodes, seen = set(), set()
def slice_back(tname):
    if tname in seen or tname in inits or tname in gin:
        return
    seen.add(tname)
    n = produced.get(tname)
    if n is None or n.op_type in STOP:
        return                      # 网络本体输出:留 fp16,converter 会插 Cast
    block_nodes.add(n.name)
    for i in n.input:
        slice_back(i)

ngrid = 0
for n in g.node:
    if n.op_type == "GridSample":
        slice_back(n.input[1])      # input[1] = grid
        ngrid += 1
print(f"GridSample {ngrid} 个,几何切片 node_block_list = {len(block_nodes)} 节点")

extra_ops = ["GridSample", "Softmax", "ReduceSum", "ReduceMean", "Sqrt"]
block_ops = list(float16.DEFAULT_OP_BLOCK_LIST) + extra_ops
m16 = float16.convert_float_to_float16(
    m, keep_io_types=True, op_block_list=block_ops,
    node_block_list=sorted(block_nodes), disable_shape_infer=False)
onnx.save(m16, DST)
import os
print(f"✅ {DST}  {os.path.getsize(DST)/1e6:.1f} MB;追加 op_block: {extra_ops}")
