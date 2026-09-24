# -*- coding: utf-8 -*-
"""修 test.py 的补丁: filename 写法照抄既有 conf 那段(test.py:162-168),
不要自己发明路径拼法。"""
import io
p = "/root/diffmvs_var/test.py"
s = io.open(p, encoding="utf-8").read()
OLD = """            # ★ 只读新增: 把 init stage 的二阶矩与第二峰质量各存一张 pfm
            for _k, _d in (("exp_variance", "expvar"), ("second_mass", "secmass")):
                if _k not in outputs: continue
                _v = outputs[_k].squeeze(1).detach().cpu().numpy()
                for _fn, _a in zip(filenames, _v):
                    _p = os.path.join(args.outdir, _d, _fn.format(_d, ".pfm").split("/")[-1])
                    os.makedirs(os.path.dirname(_p), exist_ok=True)
                    save_pfm(_p, _a.astype(np.float32))"""
NEW = """            # ★ 只读新增: 把 init stage 的二阶矩与第二峰质量各存一张 pfm
            #   路径写法逐字照抄下面既有的 conf 保存段(test.py 原 :162-168)
            for _k, _d in (("exp_variance", "expvar"), ("second_mass", "secmass")):
                if _k not in outputs: continue
                _v = outputs[_k].detach().cpu().numpy()
                for _fn, _a in zip(filenames, _v):
                    _p = os.path.join(args.outdir, _fn.format(_d, '.pfm'))
                    os.makedirs(_p.rsplit('/', 1)[0], exist_ok=True)
                    save_pfm(_p, np.ascontiguousarray(_a.squeeze().astype(np.float32)))"""
assert s.count(OLD) == 1, "锚点未命中"
io.open(p, "w", encoding="utf-8").write(s.replace(OLD, NEW))
print("✅ test.py 路径写法已改成照抄既有 conf 段")
