import ast
p = "/root/MonoMVSNet/train_bld.py"
s = open(p).read()
assert "accum_steps" not in s, "已打过补丁"

# 1) 新增参数。默认 1 = 完全不改变原行为(单变量原则)
old = "parser.add_argument('--batch_size', type=int, default=2, help='train batch size')"
new = (old + "\n"
 "# 梯度累积:官方配方是 4 卡 x batch4 = 有效 batch 16(train_bld.sh + DDP 下 batch_size 是每进程的)。\n"
 "# 我们只有 1 卡, 直接 batch2 会让有效 batch 差 8 倍, 而 lr 却照抄 0.001 —— 步长实际大 8 倍。\n"
 "# 与其去猜缩放后的 lr, 不如用梯度累积把有效 batch 还原成 16, 这样官方的 lr/wd/lrepochs 可以逐字照抄。\n"
 "# 默认 1 = 与原版行为完全一致。\n"
 "parser.add_argument('--accum_steps', type=int, default=1, help='gradient accumulation steps')")
assert old in s; s = s.replace(old, new, 1)

# 2) train_sample 支持累积:按窗口首/尾决定 zero_grad / step, loss 缩放 1/accum
old = """def train_sample(model, model_loss, optimizer, sample, args):
    model.train()
    optimizer.zero_grad()
"""
new = """def train_sample(model, model_loss, optimizer, sample, args, accum_first=True, accum_last=True):
    model.train()
    if accum_first:
        optimizer.zero_grad()
"""
assert old in s; s = s.replace(old, new, 1)

old = """    loss.backward()
    optimizer.step()
"""
new = """    (loss / float(getattr(args, "accum_steps", 1))).backward()
    if accum_last:
        optimizer.step()
"""
assert old in s; s = s.replace(old, new, 1)

# 3) 主循环:传入窗口位置, 且 lr_scheduler 只在真正 step 的那一次前进
old = """            loss, scalar_outputs, image_outputs = train_sample(model, model_loss, optimizer, sample, args)
            lr_scheduler.step()"""
new = """            _a = max(1, args.accum_steps)
            _first = (batch_idx % _a == 0)
            _last = ((batch_idx + 1) % _a == 0) or (batch_idx + 1 == len(TrainImgLoader))
            loss, scalar_outputs, image_outputs = train_sample(model, model_loss, optimizer, sample, args,
                                                               accum_first=_first, accum_last=_last)
            if _last:
                lr_scheduler.step()"""
assert old in s; s = s.replace(old, new, 1)

ast.parse(s)
open(p, "w").write(s)
print("patched: accum_steps 已加入, 默认 1 不改变原行为")
