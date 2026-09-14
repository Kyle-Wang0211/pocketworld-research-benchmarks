#!/usr/bin/env python3
"""用 MonoMVSNet **自己的**动态融合(test_dypcd_tnt_adv.py 的 filter_depth)重出点云。
常数借用它官方 advanced 里的 Museum(室内带物件, 最接近我们的场景):
  s=1, conf=0.25, dist=1/4, rel_diff=1/1500, fusion_view=11
🔴 作者原注:"we have lost the final version of the hyperparameters" —— 连他们自己
   发表的数字都不是从这份代码逐字复现的, 所以这组常数是"官方给的可复现起点",不是最优。
不改它的任何判据逻辑, 只把场景名接进它的字典。"""
import sys, os, shutil
sys.argv = ["x", "--testpath", "/root/mono_dypcd", "--testlist", "/dev/null",
            "--outdir", "/root/mono_dypcd_out", "--loadckpt", "/dev/null"]
sys.path.insert(0, "/root/MonoMVSNet")
os.chdir("/root/MonoMVSNet")

import importlib.util
spec = importlib.util.spec_from_file_location("dyp", "/root/MonoMVSNet/test_dypcd_tnt_adv.py")
dyp = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(dyp)
except SystemExit:
    pass
except Exception as e:
    print("模块加载警告(不影响 filter_depth):", str(e)[:120])

SCAN = "scene0"
for d, v in (("s_all", 1), ("conf_all", 0.25), ("dist_all", 1/4),
             ("rel_diff_all", 1/1500), ("fusion_view", 11)):
    getattr(dyp, d)[SCAN] = v
print("接入常数:", {d: getattr(dyp, d)[SCAN] for d in
                 ("s_all", "conf_all", "dist_all", "rel_diff_all", "fusion_view")})

SRC = __import__("os").environ.get("SRC", "/root/MonoMVSNet/outputs/ours/scene0")
PAIR = __import__("os").environ.get("PAIRDIR", "/root/mono_dypcd/scene0")
os.makedirs(PAIR, exist_ok=True)
shutil.copy("/root/mono_data/scene0/pair.txt", f"{PAIR}/new_pair.txt")
for sub in ("cams", "images"):
    dst = f"{PAIR}/{sub}"
    if not os.path.exists(dst): os.symlink(f"{SRC}/{sub}", dst)

out_ply = __import__("os").environ.get("OUTPLY", "/root/regionmerge/mono_dypcd.ply")
# 🔴 隐含契约:filter_depth 拿 PAIR 的 basename 当 scan 键去查 s_all/conf_all/...
# 参数化路径时极易破坏(2026-09-11 就因 PAIRDIR 不以 scene0 结尾而 KeyError)。提前断言。
_key = os.path.basename(PAIR.rstrip("/"))
print(f"[SCAN-CONTRACT] PAIR basename = {_key!r};常数表已注入的键 = {sorted(dyp.s_all)}")
assert _key in dyp.s_all, (f"🔴 basename {_key!r} 不在常数表里 ⇒ filter_depth 会 KeyError。"
                           f"PAIRDIR 必须以 /{SCAN} 结尾。")
dyp.filter_depth(PAIR, PAIR, SRC, out_ply)
print("WROTE", out_ply)
