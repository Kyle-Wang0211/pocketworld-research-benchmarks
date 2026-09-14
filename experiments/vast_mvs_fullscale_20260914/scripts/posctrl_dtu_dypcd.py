#!/usr/bin/env python3
"""阳性对照:同一条 test_dtu_dypcd.filter_depth + 同一组 DTU 常数,
喂 MonoMVSNet v4ep0 自己的代价体深度(已知好用,TNT/Museum 门下出过 45.8M 点)。
若它也只通过 0.3% ⇒ 是我的搬运坏了;若它通过率正常 ⇒ DA3 深度确实过不了这道门。"""
import os, sys, shutil
sys.path.insert(0, "/root/MonoMVSNet"); os.chdir("/root/MonoMVSNet")
SRC = "/root/MonoMVSNet/outputs/v4ep0/scene0"
ROOT = "/root/posctrl_dypcd"; SCAN = "scene0"
scn = f"{ROOT}/{SCAN}"
os.makedirs(scn, exist_ok=True)
for sub in ("cams", "images"):
    dst = f"{scn}/{sub}"
    if not os.path.exists(dst): os.symlink(f"{SRC}/{sub}", dst)
shutil.copy("/root/mono_data/scene0/pair.txt", f"{scn}/pair.txt")
sys.argv = ["x", "--testpath", ROOT, "--testlist", "/dev/null",
            "--outdir", SRC, "--loadckpt", "/dev/null"]
import importlib.util
spec = importlib.util.spec_from_file_location("dyp", "/root/MonoMVSNet/test_dtu_dypcd.py")
dyp = importlib.util.module_from_spec(spec)
try: spec.loader.exec_module(dyp)
except SystemExit: pass
except Exception as ex: print("模块加载警告:", str(ex)[:140], flush=True)
print(f"[CONST] s={dyp.s} e={dyp.e} dist_base={dyp.dist_base} rel_diff_base={dyp.rel_diff_base} args.conf={dyp.args.conf}", flush=True)
dyp.filter_depth(scn, scn, SRC, "/root/posctrl_dtu_dypcd.ply")
