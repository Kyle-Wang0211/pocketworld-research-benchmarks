#!/usr/bin/env python3
"""A2:用 ONNX Runtime 跑 97 帧,与 PyTorch 参考逐像素比。

  python3.11 run_ort.py --onnx X.onnx --fixture .../fx_official \
      --ref .../bench_baseline/EXTNF --out .../ort_out [--ep CPU]

🔑 **能做逐像素比的前提**(已实测,不是假设):
   参考跑用了 `--ext-noise`,即扩散噪声显式生成并落盘;实测它与模型内部
   `randn_like` 的结果**97 帧逐比特相同**。所以 ORT 吃同一份噪声就能对拍。
   不做这一步的话,对拍的是扩散噪声(同输入两跑 21.5% 像素差 >1%)。

⚠️ 口径必须对齐:ONNX 若用 `--fuse-conv3d` 导出,参考也必须带 `--fuse-conv3d`,
   否则会混进 3D→2D 融合那 ~1e-6 的差,把 ORT 自身的误差掩盖掉。
"""
import argparse, json, os, time
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--ep", default="CPU", help="CPU / CoreML")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--threads", type=int, default=0)
    args = ap.parse_args()
    import onnxruntime as ort

    meta = json.load(open(f"{args.fixture}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    NIMG = meta["num_src"] + 1
    IM = np.fromfile(f"{args.fixture}/images.f16", np.float16).reshape(NF, H, W)
    CM = np.fromfile(f"{args.fixture}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{args.fixture}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
    ND = 384

    so = ort.SessionOptions()
    if args.threads:
        so.intra_op_num_threads = args.threads
    eps = {"CPU": ["CPUExecutionProvider"],
           "CoreML": ["CoreMLExecutionProvider", "CPUExecutionProvider"]}[args.ep]
    t0 = time.time()
    sess = ort.InferenceSession(args.onnx, so, providers=eps)
    print(f"会话建立 {time.time()-t0:.1f}s   EP={sess.get_providers()}")
    want = {i.name for i in sess.get_inputs()}
    for i in sess.get_inputs():
        print(f"  in  {i.name:14} {i.shape}")
    print(f"  (图未使用的输入已自动跳过)")

    nrun = args.limit or NF
    if args.out:
        os.makedirs(f"{args.out}/depth", exist_ok=True)
    ts, stat = [], []
    for f in range(nrun):
        view = [f] + list(NB[f][:NIMG - 1])
        imgs = np.stack([np.repeat(IM[v].astype(np.float32)[None], 3, 0)
                         for v in view])[None]
        Ks = np.stack([CM[v, 0:9].reshape(3, 3) for v in view])
        wc = np.stack([np.vstack([np.hstack([CM[v, 9:18].reshape(3, 3),
                                             CM[v, 18:21][:, None]]),
                                  [0, 0, 0, 1]]).astype(np.float32) for v in view])
        base = np.zeros((NIMG, 2, 4, 4), np.float32)
        base[:, 0] = wc
        base[:, 1, :3, :3] = Ks
        pms = []
        for dv_ in (8., 4., 2., 1.):
            mm = base.copy()
            mm[:, 1, :2, :] = base[:, 1, :2, :] / dv_
            pms.append(mm[None])
        dv = np.linspace(1 / float(CM[f, 25]), 1 / float(CM[f, 24]),
                         ND, dtype=np.float32)[None]
        nz = np.load(f"{args.ref}/noise/{f:04d}.npz")   # ← 与参考同一份噪声
        allf = {"imgs": imgs, "pm_stage1": pms[0], "pm_stage2": pms[1],
                "pm_stage3": pms[2], "pm_stage4": pms[3], "depth_values": dv,
                "noise_stage2": nz["n2"].astype(np.float32),
                "noise_stage3": nz["n3"].astype(np.float32)}
        # ⚠️ 只喂图里真有的输入:stage_iters=[1,3,3] 只用 stage1-3,
        #    `pm_stage4` 从未被读到 ⇒ 导出时被裁掉,硬喂会 InvalidArgument。
        feed = {k: v for k, v in allf.items() if k in want}
        t = time.time()
        out = sess.run(["depth", "conf0", "conf1", "conf2"], feed)
        ts.append(time.time() - t)
        d = out[0][0].astype(np.float32)
        if args.out:
            np.save(f"{args.out}/depth/{f:04d}.npy", d)
            for k in range(3):                      # 官方 filter.py 要三阶段 conf
                os.makedirs(f"{args.out}/conf{k}", exist_ok=True)
                np.save(f"{args.out}/conf{k}/{f:04d}.npy",
                        out[1 + k][0].astype(np.float32))
        ref = np.load(f"{args.ref}/depth/{f:04d}.npy")
        rel = np.abs(d - ref) / np.maximum(ref, 1e-6)
        stat.append((int((d != ref).sum()), d.size, float(rel.max()),
                     float(np.median(rel)), float((rel > 0.01).mean())))
        if f % 10 == 0:
            print(f"  帧{f:3d}/{nrun}  {ts[-1]*1000:7.0f} ms  "
                  f"最大相对差 {100*rel.max():.4f}%", flush=True)

    S = np.array(stat)
    warm = ts[1:] or ts
    print(f"\n══ ORT-{args.ep} ══")
    print(f"  {1000*np.mean(warm):.0f} ms/帧 (p50 {1000*np.median(warm):.0f})"
          f"   {nrun} 帧 {sum(ts):.1f}s")
    print(f"\n══ 与 PyTorch 参考逐像素比 ══")
    print(f"  不同像素 {int(S[:,0].sum()):,}/{int(S[:,1].sum()):,} "
          f"({100*S[:,0].sum()/S[:,1].sum():.2f}%)")
    print(f"  相对差 p50 {100*np.median(S[:,3]):.6f}%   最大 {100*S[:,2].max():.4f}%")
    print(f"  >1% 的像素 {100*S[:,4].mean():.4f}%")
    # 🔴 判据必须看**分布**,不能看单点最大值 —— 353 万像素里总有个别点把 max 拉高,
    #    拿 max 当门等于用错尺子。参照:模型自身扩散噪声让同输入两跑 21.5% 像素差 >1%。
    frac1 = S[:, 4].mean()
    ok = frac1 < 1e-4 and np.median(S[:, 3]) < 1e-5
    print(f"\n  ⇒ {'✅ 数值等价(>1% 像素 %.4f%%,p50 %.2e —— fp32 累加顺序量级)' % (100*frac1, np.median(S[:,3])) if ok else '🔴 有实质差异,需定位'}")


if __name__ == "__main__":
    main()
