# [CHUNK-STREAM 2026-08-31] MapAnything 分块 + 执行级流式推理。
#
# 为什么这么做(不是自研,是这一族的公开解法):
#   全对全注意力(Fast3R / VGGT / MapAnything)对帧数二次,显存无界 ——
#   VGGT-Long(ICRA 2026, arXiv 2507.16443)的答案是 "Chunk it, Loop it, Align it"。
#   官方 memory_efficient_inference 只对 dense head 做 minibatch
#   (model.py:1558 原注释 "the memory bottleneck"),编码器与跨视图注意力仍是 N 视图一次过。
#
# 🔑 我们比 VGGT-Long 省一大半:**我们有位姿**。
#   全对全注意力同时在做两件事 —— 推相对几何、保一致性。
#   第一件我们的稀疏线已经解决了,所以:
#     · 位姿直接喂进去(Images + Calibration + Pose 模式)
#     · 各块输出天然落在同一个世界系 ⇒ 融合就是拼接,不需要 IRLS/回环对齐
#     · 重叠只为跨块一致性,不为配准 ⇒ 可以远小于 VGGT-Long 的 50%
#
# 🔑 尺度:08-26 那批喂的是 COLMAP 位姿(无尺度),契约里
#   ignore_pose_scale_inputs = not metric_poses ⇒ 于是需要 3.834 的全局重缩放。
#   ARKit 位姿是**米制**的 ⇒ metric_poses=True,模型直接出米制,不需要重缩放。
#
# 流式:块间释放显存、结果逐块吐出 ⇒ 显存由块大小定界,且天然支持渐进预览。
# ⚠️ 这是**执行级**流式,不是架构级(CUT3R/StreamVGGT 那种循环状态需要重训)。
import argparse, json, os, threading, time
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from mapanything.models import MapAnything
from mapanything.utils.image import preprocess_inputs
# [相机锁定] 复用 08-26 生产实验的实现,不自己重推(它是 camera_locked 臂
# "scale 3.834 / 残差中位 0.034" 的来源)。
from mapanything_camera_lock import fit_camera_similarity
from mapanything.utils.geometry import depthmap_to_world_frame


class PeakPoller(threading.Thread):
    """MPS 无 reset_peak_memory_stats,轮询 driver_allocated_memory 抓峰值。"""
    def __init__(self, hz=100):
        super().__init__(daemon=True); self._halt = False; self.peak = 0; self._dt = 1.0 / hz
    def run(self):
        while not self._halt:
            self.peak = max(self.peak, torch.mps.driver_allocated_memory()); time.sleep(self._dt)
    def stop(self):
        self._halt = True; self.join(timeout=1.0); return self.peak



# [编码缓存 2026-08-31] 分块 + 重叠 ⇒ 同一视图会落在多个块里被**重复编码**。
# 实测拆分:K=4 时编码器占单次前向的 **50%**,且严格线性(0.34 s/view,K=2..16 不变)。
# overlap=2 / K=4 ⇒ 每视图被编码 2 次 ⇒ 编码器工作量白白翻倍。
#
# 🔑 无损性:编码器的输入只有 (image, data_norm_type) —— **与位姿、与块内其它视图
#    都无关**(见 model.py 的 ViTEncoderInput 构造)。同一视图在任何块里的编码输出
#    逐位相同,缓存复用是严格等价,不是近似。
#
# 实现上不改模型代码:把 self.encoder 换成带缓存的包装,靠 side-channel 传视图 id。
# 只保留后续块还会用到的视图(滑动窗口),显存开销 = overlap × 单视图特征。
class CachingEncoder(torch.nn.Module):
    def __init__(self, enc):
        super().__init__()
        self.enc = enc
        self.cache = {}
        self.keys = None          # 由调用方在每次 infer 前设好
        self.hits = 0
        self.misses = 0

    # 注意:模型对 self.encoder.* 的属性访问全部发生在 __init__(model.py:198-238),
    # forward 只调 self.encoder(input) ⇒ 构造完成后再包装是安全的,无需透传属性。

    def forward(self, inp):
        from uniception.models.encoders import ViTEncoderInput, ViTEncoderOutput
        keys = self.keys
        imgs = inp.image
        n = len(keys)
        per = imgs.shape[0] // n
        miss_idx = [i for i, k in enumerate(keys) if k not in self.cache]
        self.hits += n - len(miss_idx)
        self.misses += len(miss_idx)
        if miss_idx:
            sub = torch.cat([imgs[i * per:(i + 1) * per] for i in miss_idx], dim=0)
            out = self.enc(ViTEncoderInput(image=sub, data_norm_type=inp.data_norm_type))
            feats = out.features.chunk(len(miss_idx), dim=0)
            regs = (out.registers.chunk(len(miss_idx), dim=0)
                    if out.registers is not None else [None] * len(miss_idx))
            for j, i in enumerate(miss_idx):
                self.cache[keys[i]] = (feats[j], regs[j])
        F = torch.cat([self.cache[k][0] for k in keys], dim=0)
        R = None
        if self.cache[keys[0]][1] is not None:
            R = torch.cat([self.cache[k][1] for k in keys], dim=0)
        return ViTEncoderOutput(features=F, registers=R)

    def evict_except(self, keep):
        keep = set(keep)
        for k in [k for k in self.cache if k not in keep]:
            del self.cache[k]



# [PLY 导出 2026-08-31] 格式与 08-26 生产实验的 mapanything_infer_ply.py 一致
# (binary_little_endian,x/y/z float32 + red/green/blue uchar),这样现成的
# mapanything_compare.py 和对比网页能直接吃。
PLY_DTYPE = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),
                      ("r","u1"),("g","u1"),("b","u1")])

def write_ply(path, xyz, rgb):
    n = xyz.shape[0]
    arr = np.empty(n, dtype=PLY_DTYPE)
    arr["x"], arr["y"], arr["z"] = xyz[:,0], xyz[:,1], xyz[:,2]
    arr["r"], arr["g"], arr["b"] = rgb[:,0], rgb[:,1], rgb[:,2]
    hdr = (f"ply\nformat binary_little_endian 1.0\nelement vertex {n}\n"
           "property float x\nproperty float y\nproperty float z\n"
           "property uchar red\nproperty uchar green\nproperty uchar blue\n"
           "end_header\n")
    with open(path, "wb") as f:
        f.write(hdr.encode()); f.write(arr.tobytes())
    return n


def load_scene(frozen_root: Path):
    """从冻结场景读真实内参与位姿(COLMAP 约定 world_to_camera = [R|T])。"""
    sel = json.loads((frozen_root / "selection.json").read_text())
    out = []
    for im in sel["images"]:
        R = np.array(im["R"], dtype=np.float64).reshape(3, 3)
        T = np.array(im["T"], dtype=np.float64).reshape(3)
        w2c = np.eye(4); w2c[:3, :3] = R; w2c[:3, 3] = T
        out.append({
            "name": im["name"], "pgm": im["gray_pgm"],
            "K": np.array(im["K"], dtype=np.float32).reshape(3, 3),
            "c2w": np.linalg.inv(w2c).astype(np.float32),   # MapAnything 要 cam2world
        })
    return out


def build_views(scene, idxs, images_dir: Path, metric_poses: bool):
    raw = []
    for i in idxs:
        s = scene[i]
        img_path = images_dir / (Path(s["name"]).stem + ".jpg")
        raw.append({
            "img": np.asarray(Image.open(img_path).convert("RGB"), dtype=np.uint8),
            "intrinsics": s["K"],
            "camera_poses": s["c2w"],
            "is_metric_scale": torch.tensor([bool(metric_poses)]),
        })
    return preprocess_inputs(raw, verbose=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", default=str(Path.home() / ".codex/builds/pw-dense-xorwow-2000-20260829/FrozenB28"))
    ap.add_argument("--images", default="images")
    ap.add_argument("--model", default="facebook/map-anything-apache")
    ap.add_argument("--chunk", type=int, default=8, help="每块视图数 K")
    ap.add_argument("--overlap", type=int, default=2, help="块间重叠(只为一致性,不为配准)")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 帧(0=全部 132)")
    ap.add_argument("--metric-poses", action="store_true", default=True)
    ap.add_argument("--out", default="chunk_out")
    ap.add_argument("--no-cache", action="store_true", help="关掉编码缓存(等价性对照用)")
    ap.add_argument("--conf-percentile", type=float, default=0.0,
                    help="按置信度百分位过滤(0=不过滤);与 08-26 生产实验同口径")
    ap.add_argument("--cfg", default="", help="用随机权重跑(给 config.json 路径),不下权重")
    a = ap.parse_args()

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    outdir = Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    scene = load_scene(Path(a.frozen))
    n_total = len(scene) if a.limit <= 0 else min(a.limit, len(scene))

    print(f"[setup] device={dev} model={a.model}", flush=True)
    print(f"[setup] MPS 上限 {torch.mps.recommended_max_memory()/2**30:.2f} GB", flush=True)
    t0 = time.time()
    if a.cfg:
        # 随机初始化:耗时/显存只取决于架构,可在无权重时验证结构与等价性
        import json as _json
        _c = _json.load(open(a.cfg)); _c["encoder_config"]["torch_hub_pretrained"] = False
        model = MapAnything(**_c).to(dev).eval()
    else:
        model = MapAnything.from_pretrained(a.model).to(dev).eval()
    print(f"[setup] 加载 {time.time()-t0:.1f}s  "
          f"参数 {sum(p.numel() for p in model.parameters())/1e6:.0f} M", flush=True)

    # 位姿契约:与 08-26 生产实验同源,只是 metric_poses 由 False 改为 True
    infer_kwargs = dict(ignore_depth_inputs=True, ignore_depth_scale_inputs=True,
                        ignore_pose_scale_inputs=not a.metric_poses)

    # [编码缓存] 包装 encoder。--no-cache 可关掉用于等价性对照。
    cache_enc = None
    if not a.no_cache:
        cache_enc = CachingEncoder(model.encoder).to(dev).eval()
        model.encoder = cache_enc

    step = max(1, a.chunk - a.overlap)
    starts = list(range(0, n_total, step))
    chunks = [list(range(s, min(s + a.chunk, n_total))) for s in starts]
    chunks = [c for c in chunks if c]

    # [逐块尺度 2026-08-31 修正] 🔴 每块的深度尺度是模型**各自预测**的
    # (实测块0=0.744/块1=0.837/块2=0.901)。之前只用块0拟合一个"全局尺度"套给所有块,
    # 会让不同块的点沿视线方向前后错开 —— 渲染出来就是一团雾。
    # 世界变换已由我们自己的位姿承担(depthmap_to_world_frame),所以每块**只需要各自的尺度**。
    emitted = set()          # 已吐出的视图,重叠部分只吐一次
    xyz_all, rgb_all = [], []
    rows, wall0 = [], time.time()
    for ci, idxs in enumerate(chunks):
        torch.mps.empty_cache(); time.sleep(0.3)
        base = torch.mps.driver_allocated_memory()
        views = build_views(scene, idxs, Path(a.images), a.metric_poses)
        if cache_enc is not None:
            cache_enc.keys = list(idxs)          # side-channel:告诉缓存这一块是哪些视图
        poller = PeakPoller(); poller.start(); t = time.time(); err = None
        try:
            with torch.inference_mode():
                outs = model.infer(views, memory_efficient_inference=True, minibatch_size=1,
                                   use_amp=True, amp_dtype="fp16",
                                   apply_mask=True, mask_edges=True, **infer_kwargs)
            torch.mps.synchronize()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]; outs = None
        dt = time.time() - t; peak = poller.stop()

        new = [i for i in idxs if i not in emitted]
        npts = 0
        CHUNK_SCALE = 1.0
        if outs is not None and len(idxs) >= 3:
            try:
                src = np.stack([o_["camera_poses"][0].detach().float().cpu().numpy()[:3, 3]
                                for o_ in outs], 0).astype(np.float64)
                dst = np.stack([scene[g]["c2w"][:3, 3] for g in idxs], 0).astype(np.float64)
                fit = fit_camera_similarity(src, dst)
                CHUNK_SCALE = fit["scale"]
                print(f"  块{ci} 深度尺度 {CHUNK_SCALE:.5f}  "
                      f"(相机中心拟合残差 中位 {fit['residual_median']:.4f} / "
                      f"p95 {fit['residual_p95']:.4f})", flush=True)
            except Exception as e:
                print(f"  ⚠️ 块{ci} 尺度拟合失败,退回 1.0: {type(e).__name__}", flush=True)
        if outs is not None:
            for k, gi in enumerate(idxs):
                if gi in emitted: continue
                o = outs[k]
                # [借鉴 08-26 生产实现 mapanything_infer_ply.py]
                # 🔑 **不用 pts3d**。pts3d 是「块内 view 0」坐标系(model.py:714),
                #    分块时各块各有原点,拼不到一起。
                #    生产脚本的做法是:只从模型取**深度**,几何用**我们自己的**
                #    内参+位姿重建 ⇒ 世界系问题根本不存在,只剩一个全局深度尺度。
                depth = o["depth_z"][0].squeeze(-1) * CHUNK_SCALE
                K_ = views[k]["intrinsics"][0]
                P_ = views[k]["camera_poses"][0]
                wxyz, valid = depthmap_to_world_frame(depth, K_, P_)
                mk = o["mask"][0].squeeze(-1).bool() & valid.bool()
                mk &= torch.isfinite(wxyz).all(dim=-1)
                xyz = wxyz[mk].detach().float().cpu().numpy()
                col = o["img_no_norm"][0][mk].detach().cpu().numpy()
                if col.dtype != np.uint8:
                    if float(col.max(initial=0)) <= 1.0: col = col * 255.0
                    col = np.clip(col, 0, 255).astype(np.uint8)
                xyz_all.append(xyz); rgb_all.append(col)
                npts += int(xyz.shape[0])
                emitted.add(gi)
        row = {"chunk": ci, "views": idxs, "scale": round(float(CHUNK_SCALE),5), "new_views": new, "seconds": round(dt, 3),
               "peak_gib": round(peak / 2**30, 3), "delta_gib": round((peak - base) / 2**30, 3),
               "points": npts, "error": err}
        rows.append(row)
        print(f"[块{ci:3d}] 视图{idxs[0]:3d}-{idxs[-1]:3d} (新{len(new):2d})  "
              f"{dt:6.2f}s  峰值 {peak/2**30:5.2f} GiB  {err or '✓'}", flush=True)
        if cache_enc is not None:
            # 只保留后续块还会用到的视图 ⇒ 显存开销 = overlap × 单视图特征
            future = set()
            for later in chunks[ci + 1:ci + 2]:
                future |= set(later)
            cache_enc.evict_except(future)
        del views, outs
        if err: break

    total = time.time() - wall0
    ok = [r for r in rows if not r["error"]]
    if cache_enc is not None:
        print(f"  编码缓存: 命中 {cache_enc.hits} / 未命中 {cache_enc.misses}  "
              f"⇒ 省下 {cache_enc.hits}/{cache_enc.hits+cache_enc.misses} 次视图编码")
    summary = {
        "model": a.model, "device": dev, "chunk": a.chunk, "overlap": a.overlap,
        "n_views": n_total, "metric_poses": a.metric_poses,
        "n_chunks": len(chunks), "total_seconds": round(total, 2),
        "seconds_per_view": round(total / max(1, len(emitted)), 3),
        "peak_gib_max": round(max([r["peak_gib"] for r in ok], default=0), 3),
        "mps_recommended_max_gib": round(torch.mps.recommended_max_memory() / 2**30, 2),
        "chunks": rows,
    }
    summary["total_points"] = int(sum(r["points"] for r in ok))
    if xyz_all:
        XYZ = np.concatenate(xyz_all, 0); RGB = np.concatenate(rgb_all, 0)
        ply_path = outdir / f"cloud_k{a.chunk}_ov{a.overlap}.ply"
        n = write_ply(ply_path, XYZ, RGB)
        summary_pts = n
        print(f"  点云已写出 {ply_path.name}  {n/1e6:.2f} M 点  "
              f"({ply_path.stat().st_size/2**20:.0f} MB)")
    else:
        summary_pts = 0
    (outdir / f"chunk{a.chunk}_ov{a.overlap}.json").write_text(json.dumps(summary, indent=2))
    print(f"\n=== K={a.chunk} 重叠={a.overlap} ===")
    print(f"  {len(emitted)} 视图 / {len(chunks)} 块  总 {total:.1f}s  "
          f"每视图 {total/max(1,len(emitted)):.2f}s  峰值上限 {summary['peak_gib_max']:.2f} GiB")


if __name__ == "__main__":
    main()
