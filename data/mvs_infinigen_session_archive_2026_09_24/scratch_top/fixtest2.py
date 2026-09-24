# -*- coding: utf-8 -*-
"""修:test.py 拿到 outputs 时已经过 tensor2numpy, 不是 tensor。"""
import io
p = "/root/diffmvs_var/test.py"
s = io.open(p, encoding="utf-8").read()
OLD = "                _v = outputs[_k].detach().cpu().numpy()"
NEW = ("                # 🔴 test.py 拿到的 outputs 已经过 tensor2numpy(utils.py), 不是 tensor\n"
       "                _v = np.asarray(outputs[_k])")
assert s.count(OLD) == 1, "锚点未命中"
io.open(p, "w", encoding="utf-8").write(s.replace(OLD, NEW))
print("✅ 已改")
# 顺带确认 tensor2numpy 真的存在
import subprocess
print(subprocess.run(["grep","-n","tensor2numpy","/root/diffmvs_var/test.py"],
                     capture_output=True,text=True).stdout.strip())
