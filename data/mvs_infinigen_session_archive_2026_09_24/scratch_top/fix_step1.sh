#!/bin/bash
set -e
F=/root/infinigen/src/infinigen/core/constraints/example_solver/room/decorate.py
[ -f $F.orig_3f58bb8 ] || cp $F $F.orig_3f58bb8
python3 - <<'PY'
p="/root/infinigen/src/infinigen/core/constraints/example_solver/room/decorate.py"; t=open(p).read()
old='''            if wall_fn.__class__.__name__ == "Brick":
                kwargs = {}
            surface.assign_material(rooms__, wall_fn(**kwargs))'''
new='''            # 社区修复 princeton-vl/infinigen PR #506 (Fixes #505, 未合并), 09-24 用户批准照抄:
            # 只把 generate() 签名接受的 kwargs 传下去 (Concrete/Ceramic/MarbleRegular/MarbleVoronoi 的 generate(self) 不收参数)
            sig = inspect.signature(wall_fn.generate)
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            accepted_kwargs = {
                k: v
                for k, v in kwargs.items()
                if has_var_keyword or k in sig.parameters
            }
            surface.assign_material(rooms__, wall_fn(**accepted_kwargs))'''
assert t.count(old)==1, "anchor"
t=t.replace(old,new)
if "\nimport inspect\n" not in t:
    assert t.count("\nimport importlib\n")==1
    t=t.replace("\nimport importlib\n","\nimport importlib\nimport inspect\n")
open(p,"w").write(t); print("PR #506 已打")
PY
/root/ig_venv2/bin/python -m py_compile $F && echo "编译通过"
diff <(sed 's/^[ ]*#.*//' $F.orig_3f58bb8) <(sed 's/^[ ]*#.*//' $F) | head -30
cd /root/infinigen && timeout 300 /root/ig_venv2/bin/python - <<'PY' 2>&1 | grep -e "^CHECK" -e Error | head
import inspect, importlib
from infinigen.core.constraints.example_solver.room import decorate
from infinigen.assets.materials.ceramic.concrete import Concrete
kwargs=dict(vertical=True, alternating=False, shape="square")
for name,cls in [("Concrete",Concrete)]:
    wf=cls(); sig=inspect.signature(wf.generate)
    hv=any(p.kind==inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    acc={k:v for k,v in kwargs.items() if hv or k in sig.parameters}
    print("CHECK", name, "签名", sig, "=> 实传", acc)
    try: wf(**kwargs); print("CHECK 原写法居然没崩?")
    except TypeError as e: print("CHECK 原写法复现崩溃:", e)
    wf(**acc); print("CHECK 补丁写法调用成功")
PY
