# -*- coding: utf-8 -*-
"""给 CasDiffMVS 加一个【只读】输出: UCSNet 的 exp_variance(概率体二阶中心矩)。

为什么要它(不是自研,有出处):
  我们现有的 `photometric_confidence` = `prob_volume_sum4` = 峰顶 ±2 平面的概率质量
  (`module.py:564-571`),即「众数有多尖」——**对双峰结构完全盲**:概率体真分裂成两层时,
  只要近层那个峰够尖 sum4 就接近 1。这机制性地解释了实测到的「低纹理 conf 0.87–0.94 档
  分歧反而最大」。
  UCSNet(MIT) `networks/ucsnet.py:62-63` 用的是【全二阶矩】: sqrt(Σ_d p(d)·(d−E[d])²)。
  两峰相距 Δ 时,各自再尖方差也 ≈(Δ/2)² ⇒ **双峰必爆**。

🔴 铁律:这个补丁【只增加输出,不改变任何既有计算】。
  阴性对照: 打补丁后重跑推理,132 张 depth_est/*.pfm 必须与原版【逐字节相同】。
"""
import io, os, sys, shutil, re

SRC, DST = "/root/diffmvs", "/root/diffmvs_var"
if os.path.exists(DST): shutil.rmtree(DST)
shutil.copytree(SRC, DST, symlinks=True)
print("复制树 -> %s" % DST, flush=True)

# ---------- 1) module.py: 算 exp_variance 并返回 ----------
p = DST + "/models/module.py"
s = io.open(p, encoding="utf-8").read()
OLD = """        index = torch.sum(index * prob_volume, dim = 1, keepdim=True) # [B,1,H,W]
        normalized_depth = index / (num_depth-1.0)"""
NEW = """        index = torch.sum(index * prob_volume, dim = 1, keepdim=True) # [B,1,H,W]
        normalized_depth = index / (num_depth-1.0)

        # ★ UCSNet exp_variance: 概率体的【二阶中心矩】(networks/ucsnet.py:62-63, MIT)
        #   与下面的 photometric_confidence(=prob_volume_sum4, 峰顶±2 平面的概率质量)不同:
        #   sum4 只看「众数多尖」, 对双峰盲; 二阶矩在两峰相距 Delta 时 ~= (Delta/2)^2, 必然爆。
        #   🔴 只读, 不参与任何既有计算; 归一化到与 normalized_depth 同尺度。
        with torch.no_grad():
            _ig = torch.arange(0, num_depth, 1, device=prob_volume.device,
                               dtype=torch.float32).view(1, num_depth, 1, 1)
            exp_variance = torch.sqrt(torch.clamp(
                torch.sum(prob_volume * (_ig - index) ** 2, dim=1, keepdim=True), min=0.0))
            exp_variance = exp_variance / (num_depth - 1.0)
            # 顺带一个更直接对口「双层」的量: 第二峰的质量占比
            _pv = prob_volume
            _top1 = _pv.max(dim=1, keepdim=True)[0]
            _m = (_pv >= _top1 * 0.999)
            _far = _pv.masked_fill(_m, 0.0)
            # 把众数邻域(+-2 平面)也剔掉, 剩下的质量就是"另一簇"
            _nb = torch.nn.functional.max_pool3d(
                _m.float().unsqueeze(1), (5,1,1), stride=1, padding=(2,0,0)).squeeze(1) > 0
            second_mass = _pv.masked_fill(_nb, 0.0).sum(dim=1, keepdim=True)"""
assert s.count(OLD) == 1, "module.py 锚点不唯一/未命中"
s = s.replace(OLD, NEW)

OLD2 = "        return mask, normalized_depth, depth, view_weights.detach(), photometric_confidence"
NEW2 = ("        return (mask, normalized_depth, depth, view_weights.detach(), photometric_confidence,\n"
        "                exp_variance, second_mass)")
assert s.count(OLD2) == 1, "module.py return 锚点未命中"
io.open(p, "w", encoding="utf-8").write(s.replace(OLD2, NEW2))
print("  ✅ module.py 打好", flush=True)

# ---------- 2) diffusion.py: 接住并放进输出字典 ----------
p = DST + "/models/diffusion.py"
s = io.open(p, encoding="utf-8").read()
OLD3 = "                mask, inv_depth, init_depth, view_weights, conf = self.depthnet("
NEW3 = "                mask, inv_depth, init_depth, view_weights, conf, exp_var, second_mass = self.depthnet("
assert s.count(OLD3) == 1, "diffusion.py 解包锚点未命中"
s = s.replace(OLD3, NEW3)
OLD4 = """        return {
                "depth": depth_predictions, 
                "conf": confs,
                "photometric_confidence": confidences, 
                }"""
NEW4 = """        return {
                "depth": depth_predictions, 
                "conf": confs,
                "photometric_confidence": confidences, 
                # ★ 只读新增: UCSNet 二阶矩 + 第二峰质量占比(init stage)
                "exp_variance": exp_var,
                "second_mass": second_mass,
                }"""
assert s.count(OLD4) == 1, "diffusion.py 返回锚点未命中"
io.open(p, "w", encoding="utf-8").write(s.replace(OLD4, NEW4))
print("  ✅ diffusion.py 打好", flush=True)

# ---------- 3) test.py: 存成 pfm ----------
p = DST + "/test.py"
s = io.open(p, encoding="utf-8").read()
OLD5 = '            confs = outputs["photometric_confidence"]'
NEW5 = ('            confs = outputs["photometric_confidence"]\n'
        '            # ★ 只读新增: 把 init stage 的二阶矩与第二峰质量各存一张 pfm\n'
        '            for _k, _d in (("exp_variance", "expvar"), ("second_mass", "secmass")):\n'
        '                if _k not in outputs: continue\n'
        '                _v = outputs[_k].squeeze(1).detach().cpu().numpy()\n'
        '                for _fn, _a in zip(filenames, _v):\n'
        '                    _p = os.path.join(args.outdir, _d, _fn.format(_d, ".pfm").split("/")[-1])\n'
        '                    os.makedirs(os.path.dirname(_p), exist_ok=True)\n'
        '                    save_pfm(_p, _a.astype(np.float32))')
assert s.count(OLD5) == 1, "test.py 锚点未命中"
io.open(p, "w", encoding="utf-8").write(s.replace(OLD5, NEW5))
print("  ✅ test.py 打好", flush=True)
print("\n三处补丁完成。下一步必须过阴性对照: depth_est/*.pfm 与原版逐字节相同。")
