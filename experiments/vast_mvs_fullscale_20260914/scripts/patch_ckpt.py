import re
p="/root/MonoMVSNet/train_bld.py"
s=open(p).read()
if "iter_save_freq" in s:
    print("已打过补丁"); raise SystemExit
s=s.replace("parser.add_argument('--accum_steps', type=int, default=1, help='gradient accumulation steps')",
            "parser.add_argument('--accum_steps', type=int, default=1, help='gradient accumulation steps')\n"
            "parser.add_argument('--iter_save_freq', type=int, default=0, help='save a checkpoint every N iters (0 = off, 官方行为不变)')")
old = """            if _last:
                lr_scheduler.step()"""
new = """            if _last:
                lr_scheduler.step()
            # 仪表:按迭代存盘,默认 0 = 关闭 = 官方行为逐字不变
            if args.iter_save_freq > 0 and batch_idx > 0 and batch_idx % args.iter_save_freq == 0 \\
               and ((not is_distributed) or (dist.get_rank() == 0)):
                torch.save({'epoch': epoch_idx, 'iter': batch_idx,
                            'model': model.module.state_dict(),
                            'optimizer': optimizer.state_dict()},
                           "{}/iter_{:06d}.ckpt".format(args.logdir, epoch_idx * len(TrainImgLoader) + batch_idx))"""
assert old in s, "锚点没找到"
s=s.replace(old,new,1)
open(p,"w").write(s)
print("补丁已打:--iter_save_freq(默认0=不改变官方行为)")
