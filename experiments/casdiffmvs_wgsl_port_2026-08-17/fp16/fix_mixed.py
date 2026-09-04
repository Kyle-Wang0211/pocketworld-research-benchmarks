#!/usr/bin/env python3
"""occ node_block_list 边界漏插 Cast 的补丁:
对单类型参数 T 的算术/采样节点,若输入声明类型与输出声明类型不一致
(fp32↔fp16 混型),在该输入前插 Cast 到输出类型。"""
import sys, onnx
from onnx import TensorProto, helper

m = onnx.load(sys.argv[1])
g = m.graph
FLOATS = (TensorProto.FLOAT, TensorProto.FLOAT16)

vt = {}
for vi in list(g.value_info) + list(g.output) + list(g.input):
    t = vi.type.tensor_type.elem_type
    if t:
        vt[vi.name] = t
for t in g.initializer:
    vt[t.name] = t.data_type

# 这些 op 的全部 float 输入必须同型 T(Where 的 cond 是 bool,自动跳过)
UNI = {"Add", "Sub", "Mul", "Div", "Pow", "MatMul", "Gemm", "Concat", "Sum",
       "Min", "Max", "Where", "PRelu", "GridSample", "InstanceNormalization"}

new_nodes, count = [], 0
for n in g.node:
    if n.op_type in UNI and n.output and vt.get(n.output[0]) in FLOATS:
        tgt = vt[n.output[0]]
        for i, iname in enumerate(list(n.input)):
            it = vt.get(iname)
            if it in FLOATS and it != tgt:
                cname = f"{iname}_autocast_{count}"
                new_nodes.append(helper.make_node(
                    "Cast", [iname], [cname], name=f"AutoCast_{count}", to=tgt))
                vt[cname] = tgt
                n.input[i] = cname
                count += 1
    new_nodes.append(n)

del g.node[:]
g.node.extend(new_nodes)
onnx.save(m, sys.argv[2])
print(f"✅ 插入 {count} 个调和 Cast → {sys.argv[2]}")
