# -*- coding: utf-8 -*-
"""修 bug ②: EqualDomainSampler 的 epoch 计数器在进程重启时归零。

现状: __init__ 里 self.epoch = 0, __iter__ 里 self.epoch += 1
  ⇒ 种子用的是「本进程内第几次迭代」, 不是「真实第几个 epoch」
  ⇒ --resume 从 epoch 6 续跑时, 采样器回到 0 ⇒ epoch 6 抽到与 epoch 0 逐字节相同的子集。

修法 = 抄标准 API, 不自研:
  - torch.utils.data.distributed.DistributedSampler.set_epoch 的实现体就是 `self.epoch = epoch`
  - DUSt3R easy_dataset.py 的 ResizedDataset 同样是 set_epoch(epoch) 由训练器传真实 epoch
  ⇒ 给 EqualDomainSampler 加 set_epoch, 去掉自增; train.py 的 epoch 循环里调用它。
    调用处用 hasattr 守卫, 对 shuffle=True 那条路径(RandomSampler 无此方法)是零影响。

行尾: 以二进制读写并原样保留 (本仓历史上有 CRLF 文件, 整份改写会炸出上百行假 diff)。
"""
import io, os, sys, hashlib

ROOT = "/root/diffmvs_full"
SAMP = os.path.join(ROOT, "datasets/domain_sampler.py")
TRAIN = os.path.join(ROOT, "train.py")


def read(p):
    b = open(p, "rb").read()
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    return b, ("CRLF" if crlf > lf else "LF"), crlf, lf


def write(p, text, eol):
    data = text.replace("\r\n", "\n")
    if eol == "CRLF":
        data = data.replace("\n", "\r\n")
    open(p, "wb").write(data.encode("utf-8"))


for p in (SAMP, TRAIN):
    b, eol, crlf, lf = read(p)
    print("%-46s %s  (CRLF %d / LF %d)  md5 %s" % (p, eol, crlf, lf, hashlib.md5(b).hexdigest()[:12]))

# ---------------- ① domain_sampler.py ----------------
b, eol, _, _ = read(SAMP)
s = b.decode("utf-8").replace("\r\n", "\n")

old_iter = """        g = torch.Generator()
        g.manual_seed(self.epoch + 777)   # DUSt3R easy_dataset.py ResizedDataset.set_epoch: default_rng(seed=epoch+777)
        self.epoch += 1
"""
assert s.count(old_iter) == 1, "锚点①不唯一, 停"
new_iter = """        g = torch.Generator()
        g.manual_seed(self.epoch + 777)   # DUSt3R easy_dataset.py ResizedDataset.set_epoch: default_rng(seed=epoch+777)
"""
s = s.replace(old_iter, new_iter)

old_sizes = """    def sizes(self):
        return {d: int(len(self.idx[d])) for d in self.domains}
"""
assert s.count(old_sizes) == 1, "锚点②不唯一, 停"
new_sizes = """    def set_epoch(self, epoch):
        \"\"\"由训练器传入【真实 epoch】。实现体逐字同 torch DistributedSampler.set_epoch,
        语义同 DUSt3R easy_dataset.py 的 set_epoch —— 种子必须来自真实 epoch,
        否则 --resume 后采样器从 0 重数, 会重放早期 epoch 的同一批子集。\"\"\"
        self.epoch = int(epoch)

    def sizes(self):
        return {d: int(len(self.idx[d])) for d in self.domains}
"""
s = s.replace(old_sizes, new_sizes)
write(SAMP, s, eol)
print("\n✅ domain_sampler.py: 去掉 self.epoch 自增, 加 set_epoch")

# ---------------- ② train.py ----------------
b, eol, _, _ = read(TRAIN)
t = b.decode("utf-8").replace("\r\n", "\n")

old_loop = """    for epoch_idx in range(start_epoch, total_epochs):
        print('Epoch {}:'.format(epoch_idx))
"""
assert t.count(old_loop) == 1, "锚点③不唯一, 停"
new_loop = """    for epoch_idx in range(start_epoch, total_epochs):
        print('Epoch {}:'.format(epoch_idx))
        # 采样器的随机流必须由【真实 epoch】驱动, 否则 --resume 会重放早期 epoch 的子集。
        # 与 torch DistributedSampler 的标准用法一致; shuffle=True 那条路径无此方法, hasattr 守卫。
        if hasattr(TrainImgLoader.sampler, "set_epoch"):
            TrainImgLoader.sampler.set_epoch(epoch_idx)
"""
t = t.replace(old_loop, new_loop)
write(TRAIN, t, eol)
print("✅ train.py: epoch 循环里调用 set_epoch(epoch_idx)")
