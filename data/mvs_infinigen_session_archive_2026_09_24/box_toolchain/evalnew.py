# -*- coding: utf-8 -*-
"""对【新 ep0(skyfix)】跑逐域验证, 命令行逐字复用 epoch_eval.py 的 COMMON,
   只把 --loadckpt 指向新权重。老 ep0 的数已在 /root/epoch_eval.log。
🔴 口径警告: skyfix 改写了 TartanAir 的 cam.txt(深度范围)=> tartanair 这一档的
   【验证数据本身变了】, 跨跑不可比。可比的是没被动过的域, 其中 arkitscenes
   是真实室内(离酒店房间最近), 最值得看。"""
import os, sys, re, glob, subprocess
ROOT="/root/diffmvs_full"; PY="/venv/main/bin/python"
CK=sys.argv[1]; LISTS=sys.argv[2] if len(sys.argv)>2 else "full_v3"
COMMON=("--mode=test --dataset=blend --batch_size=4 --trainpath=/root/monotrain --testpath=/root/monotrain "
        "--trainviews=8 --testviews=8 --numdepth=384 --numdepth_initial=48 --stage_iters 1 3 3 --cost_dim_stage 4 4 4 "
        "--CostNum 0 4 4 --min_radius 0.125 --max_radius 8 --conf_weight 0.05 --hidden_dim 0 32 20 "
        "--context_dim 32 32 16 --unet_dim 0 16 8 --logdir /tmp/eval_new").split()
os.chdir(ROOT)
for lst in sorted(glob.glob("lists/%s/val_*.txt"%LISTS)):
    d=os.path.basename(lst)[4:-4]
    out=subprocess.run([PY,"-u","train.py"]+COMMON+["--scale","0.0","0.125","0.025",
        "--trainlist",lst,"--testlist",lst,"--loadckpt",CK],capture_output=True,text=True)
    m=re.findall(r"final_depth_error['\"]?[:=]\s*([0-9.eE+-]+)", out.stdout+out.stderr)
    n=re.findall(r"depth_loss['\"]?[:=]\s*([0-9.eE+-]+)", out.stdout+out.stderr)
    print("  %-14s final_depth_error=%s depth_loss=%s" % (d, m[-1] if m else "??", n[-1] if n else "??"), flush=True)
