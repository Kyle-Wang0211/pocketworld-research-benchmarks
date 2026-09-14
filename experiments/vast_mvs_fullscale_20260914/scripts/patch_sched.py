import ast
p = "/root/MonoMVSNet/train_bld.py"
s = open(p).read()
if "_steps_per_epoch" in s:
    print("已打过补丁"); raise SystemExit

old_ms = "    milestones = [len(TrainImgLoader) * int(epoch_idx) for epoch_idx in args.lrepochs.split(':')[0].split(',')]"
new_ms = """    # 🔴 调度器的单位必须与 lr_scheduler.step() 的调用频率一致。
    # 上游假设每个 batch step 一次;我们用了梯度累积(每 accum_steps 个 batch 才 step),
    # 若不同步缩放,余弦/阶梯只会走完 1/accum_steps 的行程 ⇒ 退火几乎不发生。
    _acc = max(1, getattr(args, "accum_steps", 1))
    _steps_per_epoch = len(TrainImgLoader) // _acc
    milestones = [_steps_per_epoch * int(epoch_idx) for epoch_idx in args.lrepochs.split(':')[0].split(',')]"""
assert old_ms in s, "milestones 锚点未命中"
s = s.replace(old_ms, new_ms, 1)

s = s.replace("last_epoch=len(TrainImgLoader) * start_epoch - 1)",
              "last_epoch=_steps_per_epoch * start_epoch - 1)", 1)

old_cos = "lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=int(args.epochs*len(TrainImgLoader)), eta_min=0)"
new_cos = ("lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=int(args.epochs*_steps_per_epoch), eta_min=0)\n"
           "        for _ in range(_steps_per_epoch * start_epoch): lr_scheduler.step()   # 续训时对齐到已走过的步数")
assert old_cos in s, "cos 锚点未命中"
s = s.replace(old_cos, new_cos, 1)

s = s.replace("OneCycleLR(optimizer, max_lr=args.lr,total_steps=int(args.epochs*len(TrainImgLoader)))",
              "OneCycleLR(optimizer, max_lr=args.lr,total_steps=int(args.epochs*_steps_per_epoch))", 1)

anchor = "    for epoch_idx in range(start_epoch, args.epochs):"
selfrep = ('    print(f"[SCHED-SELFREPORT] scheduler={args.lr_scheduler} accum_steps={_acc} "\n'
           '          f"batches/epoch={len(TrainImgLoader)} steps/epoch={_steps_per_epoch} "\n'
           '          f"epochs={args.epochs} T_max={int(args.epochs*_steps_per_epoch)} lr0={args.lr}", flush=True)\n')
assert anchor in s, "自证锚点未命中"
s = s.replace(anchor, selfrep + anchor, 1)

ast.parse(s)
open(p, "w").write(s)
print("补丁已打, 语法OK")
