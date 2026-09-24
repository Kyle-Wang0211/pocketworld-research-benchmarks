# -*- coding: utf-8 -*-
"""逐 epoch 逐域验证 + Prechelt 1998 判据。
对 checkpoints/casdiff_full/model_XXXXXX.ckpt 逐个用【官方 train.py --mode=test】跑 lists/<LISTS>/val_<domain>.txt,
把官方打印的 final {...} 里的 final_depth_error / depth_loss 记到 CSV, 然后按 Prechelt 算:
  E_opt(t) = min_{t'<=t} E_va(t');  GL(t) = 100*(E_va(t)/E_opt(t) - 1);  GL_alpha: GL(t) > alpha
  UP_s: 验证误差连续 s 个 strip 上升 (strip = 1 epoch, 每 epoch 测一次 => Prechelt "measure at the end of each strip")
只报数, 不做决定。用法: python epoch_eval.py <LISTS 目录名, 如 full 或 full_v2> [only_epoch]
"""
import os, sys, re, glob, json, subprocess, csv
LISTS = sys.argv[1] if len(sys.argv) > 1 else "full"
ONLY = int(sys.argv[2]) if len(sys.argv) > 2 else None
ROOT = "/root/diffmvs_full"; CK = ROOT + "/checkpoints/casdiff_full"; CSV = "/root/epoch_eval_%s.csv" % LISTS
PY = "/venv/main/bin/python"
COMMON = ("--mode=test --dataset=blend --batch_size=4 --trainpath=/root/monotrain --testpath=/root/monotrain "
          "--trainviews=8 --testviews=8 --numdepth=384 --numdepth_initial=48 --stage_iters 1 3 3 --cost_dim_stage 4 4 4 "
          "--CostNum 0 4 4 --min_radius 0.125 --max_radius 8 --conf_weight 0.05 --hidden_dim 0 32 20 "
          "--context_dim 32 32 16 --unet_dim 0 16 8 --logdir /tmp/epoch_eval_log").split()
done = set()
if os.path.exists(CSV):
    for r in csv.DictReader(open(CSV)):
        done.add((int(r["epoch"]), r["domain"]))
else:
    open(CSV, "w").write("epoch,domain,scale,final_depth_error,depth_loss,loss\n")
doms = sorted(os.path.basename(p)[4:-4] for p in glob.glob("%s/lists/%s/val_*.txt" % (ROOT, LISTS)))
for ck in sorted(glob.glob(CK + "/model_*.ckpt")):
    ep = int(re.search(r"model_(\d+)", ck).group(1))
    if ONLY is not None and ep != ONLY: continue
    scale = ["0", "0.25", "0.05"] if ep < 8 else ["0", "0.125", "0.025"]   # 官方两段式对应的 --scale
    for d in doms:
        if (ep, d) in done: continue
        lst = "%s/lists/%s/val_%s.txt" % (ROOT, LISTS, d)
        out = subprocess.run([PY, "-u", "train.py"] + COMMON + ["--scale"] + scale + ["--trainlist", lst, "--testlist", lst, "--loadckpt", ck],
                             cwd=ROOT, capture_output=True, text=True).stdout
        m = re.search(r"^final (\{.*\})", out, re.M)
        if not m:
            print("[eval fail] ep%d %s: %s" % (ep, d, out[-300:])); continue
        f = eval(m.group(1))
        open(CSV, "a").write("%d,%s,%s,%.6f,%.6f,%.6f\n" % (ep, d, "-".join(scale), f["final_depth_error"], f["depth_loss"], f["loss"]))
        print("ep%2d %-13s final_depth_error=%.4f depth_loss=%.4f" % (ep, d, f["final_depth_error"], f["depth_loss"]), flush=True)

# ---- Prechelt 判据 (只报数) ----
rows = list(csv.DictReader(open(CSV)))
for d in doms:
    cur = sorted(((int(r["epoch"]), float(r["final_depth_error"])) for r in rows if r["domain"] == d))
    if len(cur) < 2: continue
    E = [e for _, e in cur]; opt = min(E); gl = 100.0 * (E[-1] / opt - 1.0)
    up = 0
    for i in range(len(E) - 1, 0, -1):
        if E[i] > E[i - 1]: up += 1
        else: break
    print("Prechelt %-13s ep%d: E_va=%.4f E_opt=%.4f GL=%.2f%% (GL1/2/3/5 %s)  UP 连续上升=%d strip (UP2/3/4 %s)"
          % (d, cur[-1][0], E[-1], opt, gl, "/".join("触" if gl > a else "-" for a in (1, 2, 3, 5)), up,
             "/".join("触" if up >= s else "-" for s in (2, 3, 4))))
