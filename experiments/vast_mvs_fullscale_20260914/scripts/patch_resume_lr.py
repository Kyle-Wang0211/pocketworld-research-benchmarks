p="/root/MonoMVSNet/train_bld.py"
s=open(p).read()
old="""        lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=int(args.epochs*_steps_per_epoch), eta_min=0)
        for _ in range(_steps_per_epoch * start_epoch): lr_scheduler.step()   # 续训时对齐到已走过的步数"""
new = '''        # 🔴 续训时 optimizer.load_state_dict 已把 param_groups["lr"] 恢复成"上次那一步的 lr";
        #    CosineAnnealingLR 构造时 setdefault("initial_lr", group["lr"]) 会把它当成 base_lr,
        #    下面的对齐循环于是在"已衰减的基准"上再衰减一遍 ⇒ 退火被平方
        #    (实测 0.00087052 = 0.00093301 x 0.93301,而闭式解应为 0.00093301)。
        #    必须先把 lr 复位到 args.lr,base_lrs 才等于官方起点。
        for _g in optimizer.param_groups:
            _g["lr"] = args.lr
            _g.pop("initial_lr", None)
        lr_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=int(args.epochs*_steps_per_epoch), eta_min=0)
        for _ in range(_steps_per_epoch * start_epoch): lr_scheduler.step()   # 续训时对齐到已走过的步数
        # 对齐结果必须等于闭式解,对不上就停,不许带着错的 lr 跑几十小时
        _s0 = _steps_per_epoch * start_epoch
        _exp0 = args.lr * 0.5 * (1 + math.cos(math.pi * _s0 / float(int(args.epochs*_steps_per_epoch))))
        _cur0 = optimizer.param_groups[0]["lr"]
        _ok0 = "OK" if abs(_cur0 - _exp0) < 1e-9 else "MISMATCH"
        print("[RESUME-LR-SELFCHECK] start_epoch=%d 对齐到 step=%d 实测=%.8f 预期=%.8f %s"
              % (start_epoch, _s0, _cur0, _exp0, _ok0), flush=True)
        assert abs(_cur0 - _exp0) < 1e-9, "续训 LR 对齐失败: 实测 %r 预期 %r" % (_cur0, _exp0)'''
assert s.count(old)==1, "锚点命中 %d 次" % s.count(old)
open(p,"w").write(s.replace(old,new))
print("patched")
