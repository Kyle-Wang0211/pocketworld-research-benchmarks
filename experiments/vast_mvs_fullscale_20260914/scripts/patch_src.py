import re
# --- 1) 数据集:样本里带上来源桶 id ---
p="/root/MonoMVSNet/datasets/blendedmvs.py"
s=open(p).read()
if '"src"' not in s:
    old = '''        return {"imgs": imgs,                   # [Nv, 3, H, W]'''
    new = '''        # 仪表:标出这组来自哪个数据集(0=Hypersim 1=BlendedMVG 2=TartanAir),只加一个键,不改任何行为
        _src = 0 if scan.startswith("hs_") else (2 if scan.startswith("ta_") else 1)
        return {"src": np.array(_src, dtype=np.int64),
                "imgs": imgs,                   # [Nv, 3, H, W]'''
    assert old in s, "数据集锚点没找到"
    s=s.replace(old,new,1); open(p,"w").write(s); print("① blendedmvs.py 已加 src 键")
else: print("① 已有 src")

# --- 2) 训练循环:每个 batch 都把 (来源, loss) 追加到一个 tsv ---
p="/root/MonoMVSNet/train_bld.py"
s=open(p).read()
if "srcloss.tsv" not in s:
    old = """            if _last:
                lr_scheduler.step()"""
    new = """            if _last:
                lr_scheduler.step()
            # 仪表:逐 batch 记 (全局步, 来源桶, loss),用来把总 loss 按数据集拆开
            try:
                _sv = sample["src"].view(-1).tolist()
                with open(os.path.join(args.logdir, "srcloss.tsv"), "a") as _f:
                    for _b in _sv:
                        _f.write("%d\\t%d\\t%.6f\\n" % (global_step, _b, float(loss)))
            except Exception:
                pass"""
    assert old in s, "训练循环锚点没找到"
    s=s.replace(old,new,1)
    if "\nimport os" not in s and "import os" not in s.split("\n\n")[0]:
        s = "import os\n" + s
    open(p,"w").write(s); print("② train_bld.py 已加 srcloss.tsv")
else: print("② 已有")
