#!/usr/bin/env python3
"""ALIKED + LightGlue 臂:整条前端换掉(提取+匹配都换)。

与臂 A 的关键差别 —— 臂 A 只换匹配器、复用真机 DSP-SIFT 描述子;
本臂连关键点都换,所以必须从原图重新提取,且下游的 keypoints 表要整表替换。

配置依据(已实测):ALIKED @ resize=1600 正好出满 8192 关键点,与我们的
生产预算等价;1024 只出 2811(覆盖亏 2/3),2560 在 MPS 上掉进 90s 的悬崖。

内存:特征常驻 CPU,按对搬上 GPU(整机只有 18GB,不把 132×8192×128 压在显存里)。
"""
import argparse, sqlite3, shutil, time
from pathlib import Path

import numpy as np
import torch

import devutil
import lg_load  # 必须先于 lightglue 子模块(装 kornia 桩 + 绕开 pycolmap)
import chunked_attn
import chunked_assign

MAX_IMAGE_ID = 2147483647


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="提供相机/影像/配对表的源 DB")
    ap.add_argument("--images", required=True, help="解出的原图目录")
    ap.add_argument("--frame-map", required=True,
                    help="image_id → 解码帧文件名 的映射 JSON。⚠️ 必填:DB 帧序与容器帧序"
                         "并非常数偏移(实测 132 帧里 54 帧散落在 −18…+18),按序号猜必错")
    ap.add_argument("--out", required=True)
    ap.add_argument("--resize", type=int, default=1600)
    ap.add_argument("--max-kpts", type=int, default=8192)
    ap.add_argument("--det-thr", type=float, default=0.02,
                    help="ALIKED 检测阈值。官方默认 0.2 在我们 1600 档只出 ~4.6k 点(被阈值卡住,"
                         "不是被 8192 预算卡住);实测 0.02 每帧都能填满 8192,提取只慢 5%")
    ap.add_argument("--pairs", type=int, default=0)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--cpu-resident", action="store_true",
                    help="特征放 CPU、按对搬。⚠️ 实测会触发 MPSStream::copy_and_sync 同步,"
                         "16384 档单对从 11s 退化到 >240s。默认常驻 GPU(两刀之后放得下)")
    ap.add_argument("--half", action="store_true",
                    help="模型与输入转 fp16。实测省 31% 内存、约 4% 匹配会变")
    ap.add_argument("--assign-chunk", type=int, default=0,
                    help="分配矩阵按行分块(0=关)。原版一次造 5 个 M×N 张量,是砍掉注意力后"
                         "剩下的唯一 O(N²);分块后 8192 档活跃峰值 0.761GB→0.105GB,"
                         "且与 fp32 真值逐条相同")
    ap.add_argument("--model", default="aliked-n16",
                    choices=["aliked-t16", "aliked-n16", "aliked-n16rot", "aliked-n32"],
                    help="t16 的 c1..c4=8,16,32,64、dim=64 ⇒ 全分辨率稠密图与主干中间量**全部减半**"
                         "(@1600:0.46GB vs n16 的 0.92GB),权重现成不用训")
    ap.add_argument("--extract-amp", action="store_true",
                    help="提取端走 fp16 autocast —— 卷积输出降到 half,稠密图内存减半。"
                         "⚠️ 只降提取端;描述子出来立刻转回 fp32 再喂匹配器,"
                         "保证这一臂的单变量就是「提取精度」,不掺匹配器精度。"
                         "关键点坐标本来就走 kp32_store 存 fp32,不受影响")
    ap.add_argument("--pool-cap-gb", type=float, default=6.0,
                    help="MPS 缓存池上限,超过就 empty_cache。⚠️ 剪枝会让每层张量形状逐对变化,"
                         "缓存分配器无法复用块 ⇒ 池子无界增长:实测不设闸时 swap 冲到 14.3GB、"
                         "单对从 3.5s 退化到 ~10s,量到的是换页不是算法")
    ap.add_argument("--depth-conf", type=float, default=-1.0,
                    help="LightGlue 自带的自适应深度(提前退出)。官方默认 0.95,我们从第一臂起"
                         "就写死 −1 关掉,从未量过它对质量的影响 —— 这是 08-17 才补上的对照")
    ap.add_argument("--width-conf", type=float, default=-1.0,
                    help="LightGlue 自带的自适应宽度(逐层剪点)。官方默认 0.99。"
                         "⚠️ MPS 上 pruning_min_kpts 返回 −1,所以只要 >0 就真的会剪,"
                         "不像 CUDA 还要过 1024 点的门槛")
    ap.add_argument("--attn-chunk", type=int, default=0,
                    help="注意力按查询行分块(0=关)。1024 时 8192 档省 34% 内存且"
                         "匹配逐条 100% 相同 —— 无损,softmax 按行独立故数学等价")
    args = ap.parse_args()

    utils = lg_load.load("utils")
    aliked_mod = lg_load.load("aliked")
    lg_mod = lg_load.load("lightglue")
    dev = torch.device(args.device)
    devutil.strict_fp32()

    extractor = aliked_mod.ALIKED(model_name=args.model,
                                  max_num_keypoints=args.max_kpts,
                                  detection_threshold=args.det_thr).eval().to(dev)
    if args.attn_chunk:
        chunked_attn.patch(lg_mod, args.attn_chunk)
    if args.assign_chunk:
        chunked_assign.patch(lg_mod, args.assign_chunk)
    matcher = lg_mod.LightGlue(features="aliked",
                               depth_confidence=args.depth_conf,
                               width_confidence=args.width_conf).eval().to(dev)
    if args.half:
        matcher = matcher.half()
    print(f"{args.model}(resize={args.resize}, max={args.max_kpts}, "
          f"提取{'fp16' if args.extract_amp else 'fp32'}) + LightGlue @ {dev}", flush=True)

    db = sqlite3.connect(args.db)
    names = {i: n for i, n in db.execute("select image_id,name from images")}
    pairs = [p for (p,) in db.execute("select pair_id from matches order by pair_id")]
    base = {p: r for p, r in db.execute("select pair_id,rows from matches")}
    db.close()
    if args.pairs:
        step = max(1, len(pairs) // args.pairs)
        pairs = pairs[::step][:args.pairs]

    # ---- 提取(特征留在 CPU)----
    imgdir = Path(args.images)
    feats, t_ex = {}, 0.0
    kp32_store = {}
    import json
    fmap = json.load(open(args.frame_map))
    for k, (iid, nm) in enumerate(sorted(names.items())):
        if str(iid) not in fmap:
            raise KeyError(f"映射表缺 image_id={iid}({nm})")
        p = imgdir / fmap[str(iid)]
        if not p.exists():
            raise FileNotFoundError(f"{nm} → {p} 不存在")
        img = utils.load_image(str(p)).to(dev)
        t0 = time.perf_counter()
        with torch.no_grad():
            if args.extract_amp:
                with torch.autocast(device_type=dev.type, dtype=torch.float16):
                    f = extractor.extract(img, resize=args.resize)
                f = {k: (v.float() if torch.is_floating_point(v) else v) for k, v in f.items()}
            else:
                f = extractor.extract(img, resize=args.resize)
        devutil.sync(dev)
        t_ex += time.perf_counter() - t0
        kp, de, sz = f["keypoints"][0], f["descriptors"][0], f["image_size"][0]
        # ⚠️ 关键点坐标必须保留 fp32 存库:fp16 在 2048–4096 区间的间隔是 2.0px,
        #    坐标一旦落到 fp16 就直接毁掉重投影(我们正在为 0.06px 的赤字较劲)。
        #    只有喂给匹配器的副本可以转 half —— 那里坐标先被归一化到 ±1,
        #    实测 8192 档下 fp16 与 fp32 的匹配逐条相同。
        kp32 = kp.float().cpu()
        if args.half:
            kp, de, sz = kp.half(), de.half(), sz.half()
        if args.cpu_resident:
            feats[iid] = {"keypoints": kp.cpu(), "descriptors": de.cpu(),
                          "image_size": sz.cpu()}
        else:
            feats[iid] = {"keypoints": kp, "descriptors": de, "image_size": sz}
        kp32_store[iid] = kp32
        del img, f
        if (k + 1) % 20 == 0:
            print(f"  提取 {k+1}/{len(names)}  累计 {t_ex:.0f}s", flush=True)
    n_kp = np.mean([v["keypoints"].shape[0] for v in feats.values()])
    print(f"提取完成:{len(feats)} 帧,平均 {n_kp:.0f} 关键点,{t_ex/len(feats)*1000:.0f} ms/帧", flush=True)

    # ---- 匹配 ----
    out_rows, t_m, n_lg, n_base = [], 0.0, 0, 0
    stops, n_flush = [], 0
    for i, pid in enumerate(pairs):
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        if i1 not in feats or i2 not in feats:
            continue
        d = {"image%d" % j: {k: (v[None].to(dev) if args.cpu_resident else v[None])
                             for k, v in feats[x].items()}
             for j, x in ((0, i1), (1, i2))}
        t0 = time.perf_counter()
        with torch.no_grad():
            pred = matcher(d)
        devutil.sync(dev)
        t_m += time.perf_counter() - t0
        m = pred["matches"][0].cpu().numpy().astype(np.uint32)
        out_rows.append((pid, m))
        stops.append(int(pred["stop"]))
        n_lg += len(m); n_base += base.get(pid, 0)
        pool = devutil.pool_gb(dev)
        if pool > args.pool_cap_gb:
            devutil.empty(dev); n_flush += 1
        if i < 3 or (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(pairs)}] LG={len(m):5d} base={base.get(pid,0):5d} "
                  f"stop@{pred['stop']} {(time.perf_counter()-t0)*1000:7.1f}ms "
                  f"池={pool:.2f}GB flush={n_flush}", flush=True)

    k = len(out_rows)
    print(f"\n=== {k} 对 ===")
    print(f"ALIKED+LightGlue 平均 {n_lg/k:8.1f} 匹配/对")
    print(f"基线(DSP-SIFT 暴力+0.8) 平均 {n_base/k:8.1f}")
    print(f"比值 {n_lg/max(n_base,1):.3f}×    匹配 {t_m/k*1000:.1f} ms/对")
    print(f"自适应深度:平均在第 {np.mean(stops):.2f}/9 层停(9=跑满),"
          f"分布 {np.bincount(stops, minlength=10)[1:].tolist()}")

    # ---- 写库:keypoints 整表换掉,descriptors 清空(下游不需要)----
    shutil.copy(args.db, args.out)
    for suf in ("-wal", "-shm"):
        Path(args.out + suf).unlink(missing_ok=True)
    o = sqlite3.connect(args.out)
    o.execute("delete from keypoints"); o.execute("delete from descriptors")
    o.execute("delete from matches");   o.execute("delete from two_view_geometries")
    for iid in feats:
        kp = kp32_store[iid].numpy().astype(np.float32)   # fp32 原图坐标,绝不用 half 版
        o.execute("insert into keypoints(image_id,rows,cols,data) values(?,?,?,?)",
                  (iid, kp.shape[0], 2, kp.tobytes()))
    for pid, m in out_rows:
        o.execute("insert into matches(pair_id,rows,cols,data) values(?,?,?,?)",
                  (pid, m.shape[0], 2, m.tobytes()))
    o.commit(); o.close()
    print(f"已写出 {args.out}")


if __name__ == "__main__":
    main()
