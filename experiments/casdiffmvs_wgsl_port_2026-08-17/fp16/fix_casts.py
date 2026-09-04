#!/usr/bin/env python3
"""occ 转换后处理:原图自带的 Cast(to=FLOAT) 输出被 converter 重标成 fp16,
但 `to` 属性没跟着改 ⇒ ORT 加载报 Type Error。
修法:以 value_info 声明为准,把 Cast 的 to 改成一致。"""
import sys
import onnx
from onnx import TensorProto

m = onnx.load(sys.argv[1])
g = m.graph
vt = {}
for vi in list(g.value_info) + list(g.output) + list(g.input):
    t = vi.type.tensor_type.elem_type
    if t:
        vt[vi.name] = t

fixed = 0
for n in g.node:
    if n.op_type != "Cast":
        continue
    to = next(a for a in n.attribute if a.name == "to")
    declared = vt.get(n.output[0])
    if declared in (TensorProto.FLOAT, TensorProto.FLOAT16) and to.i != declared \
            and to.i in (TensorProto.FLOAT, TensorProto.FLOAT16):
        print(f"  fix {n.name}: to {to.i} -> {declared}")
        to.i = declared
        fixed += 1
onnx.save(m, sys.argv[2])
print(f"✅ 修正 {fixed} 个 Cast → {sys.argv[2]}")
