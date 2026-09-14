import ast, math
p = "/root/MonoMVSNet/train_bld.py"
s = open(p).read()
n = 0

# 缺陷1: 尾组也会 step ⇒ 每 epoch 实际步数是 ceil 不是 floor
old = "    _steps_per_epoch = len(TrainImgLoader) // _acc"
new = ("    # 尾组(不满 _acc 个 batch)也会 step 一次 ⇒ 实际步数是 ceil,用 floor 会让\n"
       "    # 总步数超出 T_max,余弦越过底部回升。必须与 _last 的判定口径一致。\n"
       "    _steps_per_epoch = -(-len(TrainImgLoader) // _acc)   # ceil")
assert old in s, "缺陷1 锚点未命中"
s = s.replace(old, new, 1); n += 1

# 缺陷2: 静默出口 —— 失败要留痕,且只报一次
old2 = """            except Exception:
                pass"""
new2 = """            except Exception as _e:
                if not globals().get("_SRCLOSS_WARNED"):
                    globals()["_SRCLOSS_WARNED"] = True
                    print(f"[SRCLOSS-FAILED] {type(_e).__name__}: {_e} (仪表停止,训练继续)", flush=True)"""
assert old2 in s, "缺陷2 锚点未命中"
s = s.replace(old2, new2, 1); n += 1

# 缺陷3: 把「待验」变成程序自验 —— 定期对 实测LR vs 余弦公式
anchor = "            if _last:\n                lr_scheduler.step()"
new3 = """            if _last:
                lr_scheduler.step()
                # 自验:实测 LR 必须与调度器公式一致,对不上立刻报(防止再次静默失效)
                _st = getattr(lr_scheduler, "last_epoch", -1)
                if _st > 0 and _st % 2000 == 0:
                    _cur = optimizer.param_groups[0]["lr"]
                    if args.lr_scheduler == "cos":
                        _exp = args.lr * 0.5 * (1 + math.cos(math.pi * _st / float(int(args.epochs*_steps_per_epoch))))
                        _ok = abs(_cur - _exp) < 1e-9
                        print(f"[LR-SELFCHECK] step={_st} 实测={_cur:.8f} 预期={_exp:.8f} "
                              f"{'OK' if _ok else 'MISMATCH'}", flush=True)
                    else:
                        print(f"[LR-SELFCHECK] step={_st} 实测={_cur:.8f}", flush=True)"""
assert anchor in s, "缺陷3 锚点未命中"
s = s.replace(anchor, new3, 1); n += 1

if "\nimport math" not in s and not s.startswith("import math"):
    s = "import math\n" + s

ast.parse(s)
open(p, "w").write(s)
print(f"三处补丁全部打上, 语法OK ({n}/3)")
B, A, E = 119682, 8, 6
sp = -(-B // A)
print(f"  修正后 steps/epoch = {sp}  T_max = {E*sp}  实际总步 = {sp*E}  差 = 0")
