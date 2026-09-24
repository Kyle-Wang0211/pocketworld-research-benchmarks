# -*- coding: utf-8 -*-
"""bug ② 的自证: 先复现, 再证明消失, 再做阴性对照。

三问:
  A) 旧版能不能复现「--resume 从 epoch 6 续跑 == 重放 epoch 0」?
  B) 新版该现象是否消失?
  C) 阴性对照: 新版下, 连续跑的 epoch k 与 从 k 续跑的 epoch k, 抽样是否【逐位相同】?
     并且 epoch 之间必须【互不相同】(否则等于把 bug 换成了另一个 bug)。
"""
import importlib.util, hashlib, sys
import torch

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

OLD = load("/root/_bk_domain_sampler.py", "samp_old")
NEW = load("/root/diffmvs_full/datasets/domain_sampler.py", "samp_new")

# 构造与真实训练同形的 metas: 六个域, 域名前缀要能被 domain_of 认出来
# 前缀逐字取自 domain_sampler.py::_RULES; blendedmvg 是 24 位十六进制场景名
PREFIX = ["ak_", "gso_", "sp_scene_", "ta_", "tg_"]
def make_metas(n_per=4000):
    metas = []
    for pre in PREFIX:
        for i in range(n_per):
            metas.append(("%s%05d" % (pre, i), 0, [1, 2, 3]))
    for i in range(n_per):                       # blendedmvg: 24 hex
        metas.append(("%024x" % i, 0, [1, 2, 3]))
    return metas

metas = make_metas()
# 先确认 domain_of 认得这些前缀, 认不出会 raise
try:
    doms = sorted({NEW.domain_of(m[0]) for m in metas})
    print("域识别 OK:", doms)
except Exception as e:
    print("🔴 domain_of 不认这些前缀, 换成真实 metas:", e)
    sys.path.insert(0, "/root/diffmvs_full")
    raise SystemExit(1)

PER = 500
def sig(sampler):
    return hashlib.md5(",".join(map(str, list(iter(sampler)))).encode()).hexdigest()[:16]

print("\n" + "=" * 64)
print("A) 旧版 —— 复现 bug")
old_cont = OLD.EqualDomainSampler(metas, PER, seed=123, repeat_cap=0, total_epochs=16)
old_sigs = [sig(old_cont) for _ in range(8)]        # 连续跑 epoch 0..7
old_resume = OLD.EqualDomainSampler(metas, PER, seed=123, repeat_cap=0, total_epochs=16)
old_r6 = sig(old_resume)                            # 「从 epoch 6 续跑」的第一轮
print("   连续跑 epoch0 签名 :", old_sigs[0])
print("   连续跑 epoch6 签名 :", old_sigs[6])
print("   续跑 后第一轮签名   :", old_r6)
print("   ⇒ 续跑第一轮 == epoch0 ? %s   (bug 就是它)" % (old_r6 == old_sigs[0]))
print("   ⇒ 续跑第一轮 == epoch6 ? %s   (本应是它)" % (old_r6 == old_sigs[6]))

print("\n" + "=" * 64)
print("B) 新版 —— bug 应消失")
new_cont = NEW.EqualDomainSampler(metas, PER, seed=123, repeat_cap=0, total_epochs=16)
new_sigs = []
for k in range(8):
    new_cont.set_epoch(k)
    new_sigs.append(sig(new_cont))
new_resume = NEW.EqualDomainSampler(metas, PER, seed=123, repeat_cap=0, total_epochs=16)
new_resume.set_epoch(6)
new_r6 = sig(new_resume)
print("   连续跑 epoch0 签名 :", new_sigs[0])
print("   连续跑 epoch6 签名 :", new_sigs[6])
print("   续跑(set_epoch 6) :", new_r6)
print("   ⇒ 续跑 == epoch6 ? %s   (要求 True)" % (new_r6 == new_sigs[6]))
print("   ⇒ 续跑 == epoch0 ? %s   (要求 False)" % (new_r6 == new_sigs[0]))

print("\n" + "=" * 64)
print("C) 阴性对照")
allk = all(
    (lambda s: (s.set_epoch(k), sig(s))[1])(NEW.EqualDomainSampler(metas, PER, 123, 0, 16)) == new_sigs[k]
    for k in range(8))
print("   epoch 0..7 逐个「新建+set_epoch(k)」都等于连续跑的第 k 轮: %s (要求 True)" % allk)
uniq = len(set(new_sigs))
print("   8 个 epoch 的签名互不相同: %s  (%d/8 唯一, 要求 8)" % (uniq == 8, uniq))
print("   每轮样本数 = %d  (= per_domain %d x 6 域)" % (len(new_cont), PER))

ok = (old_r6 == old_sigs[0]) and (new_r6 == new_sigs[6]) and (new_r6 != new_sigs[0]) and allk and uniq == 8
print("\n%s" % ("✅ 四项全过: bug 已复现且已修复" if ok else "🔴 有项目未通过"))
