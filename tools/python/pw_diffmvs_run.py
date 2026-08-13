"""Run DiffMVS on PocketWorld real capture (npz windows + ARKit poses).

Pure MVS: feeds (image, K, w2c) only — DA3 depth/conf in the npz are DISCARDED.
Per reference frame: picks N-1 nearest source frames within its window, derives a
metric depth range from the SfM anchors, runs DiffMVS, and writes:
  <out>/win<w>_ref<r>/  ref.png  depth.npy  conf.npy  conf_overlay.png  depth_color.png  points.npz

Usage: pw_diffmvs_run.py [WIN] [REF_LOCAL] [N_VIEW] [DEVICE] [METHOD]
"""
from __future__ import annotations
import sys, json, functools
from pathlib import Path
import numpy as np
import cv2
import pw_diffmvs_common as C

ROOT = Path(__file__).resolve().parents[2]
CAP = ROOT / "data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict"
OBASE = ROOT / "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/external_pose_k_vs_res_2026_06_10"
EXPAC = ROOT / "data/expAC_rewindow_span_2026_06_13"
ANCH = ROOT / "data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz"
OUT = ROOT / "tools/python/diffmvs_out"
# [2026-07-31] 处理分辨率可配置:PW_PROC=WxH(须 32 的倍数)。默认仍是 896x512,
# 与 'o' 认证配置逐字一致 —— 不设环境变量时行为完全不变。
# 源 JPEG 原生 4224x2376(10.04Mpx),所以往上走是真的多拿信息,不是插值。
# ⚠️ 宽高比:npz/原图都是 16:9。896x512=1.75(K 补偿了那 8 行),1792x1024 同为 1.75
# 且每边正好 2x —— 单变量。若换成 4:3 会纵向拉伸 28%,那是另一个变量,别混进来。
import os as _os
_proc = _os.environ.get("PW_PROC", "896x512").lower().split("x")
PROC_W, PROC_H = int(_proc[0]), int(_proc[1])
assert PROC_W % 32 == 0 and PROC_H % 32 == 0, f"{PROC_W}x{PROC_H} 不是 32 的倍数"
NPZ_H, NPZ_W = 504, 896

_man = None; _wdef = None; _anch = None
def _load_meta():
    global _man, _wdef, _anch
    if _man is None:
        _man = json.load(open(OBASE / "k414_spatial_order_manifest.json"))["frames"]
        rows = [json.loads(l) for l in open(EXPAC / "expAC_results.jsonl")]
        _wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
        A = np.load(ANCH)
        _anch = dict(pts=A["pts"], obs_frame=A["obs_frame"], obs_aidx=A["obs_aidx"])
    return _man, _wdef, _anch


@functools.lru_cache(maxsize=512)
def _decode_image(manifest_idx: int) -> np.ndarray:
    """Deterministic JPEG decode -> (PROC_H,PROC_W,3) float32 [0,1] RGB. Cached:
    the same frame is decoded ~5x across the pipeline (pass1 ref+sources, fusion
    ref+neighbors, TSDF); imread+cvtColor+INTER_AREA resize is the cost. maxsize=512
    covers all 414 frames so each is decoded exactly once (eviction only re-decodes,
    never changes result). The cached array is PRIVATE and never handed out — callers
    receive a copy via load_image so nothing can mutate the cache in place."""
    man, _, _ = _load_meta()
    p = CAP / man[manifest_idx]["jpegPath"]
    bgr = cv2.imread(str(p))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    # PW_CROP_W:在 **896x512 基准口径**下要保留的宽度(像素)。用于把 16:9 的原图
    # 中心裁成目标宽高比后再等比缩放 —— 内容零拉伸,代价是损失水平视野。
    # 不设则行为与历史逐字相同(整幅直接 resize)。
    _cw = int(_os.environ.get("PW_CROP_W", "0"))
    if _cw and _cw < 896:
        fx0, fx1 = (896 - _cw) / 2.0 / 896.0, (896 + _cw) / 2.0 / 896.0
        W0 = rgb.shape[1]
        rgb = rgb[:, int(round(fx0 * W0)):int(round(fx1 * W0))]
    rgb = cv2.resize(rgb, (PROC_W, PROC_H), interpolation=cv2.INTER_AREA)
    return (rgb.astype(np.float32) / 255.0)


def load_image(manifest_idx: int) -> np.ndarray:
    # Return a fresh copy every call (byte-identical to the old decode-every-time
    # behaviour), so any downstream in-place write can never corrupt the cache.
    return _decode_image(manifest_idx).copy()


def scaled_K(K_npz: np.ndarray) -> np.ndarray:
    """npz 的 K 是 896x504 口径。**两个轴都要缩**。
    原来只缩 Y 行是因为当时 PROC_W 恰好 == NPZ_W == 896(X 系数正好是 1.0),
    一改宽度就会漏掉 X 标定 —— FULLRES 报告 A2 第 5 条点名过这个坑。"""
    K = K_npz.astype(np.float32).copy()
    K[0, :] *= PROC_W / NPZ_W
    K[1, :] *= PROC_H / NPZ_H
    return K


def cam_center(w2c: np.ndarray) -> np.ndarray:
    return -w2c[:3, :3].T @ w2c[:3, 3]


def metric_depth_range(ref_manifest_idx: int, w2c_ref: np.ndarray):
    _, _, anch = _load_meta()
    sel = anch["obs_frame"] == ref_manifest_idx
    if sel.sum() < 8:
        return 0.3, 4.0
    aw = anch["pts"][anch["obs_aidx"][sel]]
    z = (w2c_ref[:3, :3] @ aw.T + w2c_ref[:3, 3:4]).T[:, 2]
    z = z[z > 0.05]
    # widen far margin: p98*1.25 left ~5-9% of pixels clipped at dmax (far-wall
    # ballooning/streaks). Use p99.5 and *1.5 for headroom on far geometry.
    lo, hi = np.percentile(z, 2), np.percentile(z, 99.5)
    return float(max(0.1, lo * 0.70)), float(hi * 1.5)


def select_views(K, w2c, fidx, ref_local: int, n_view: int, min_base: float = 0.06):
    """ref + nearest sources that have ENOUGH baseline (parallax). Pure-nearest
    picks near-colocated frames (~1cm) -> zero parallax -> garbage depth on near
    objects; require baseline >= min_base m so triangulation is well-conditioned."""
    centers = np.array([cam_center(w2c[j]) for j in range(len(fidx))])
    d = np.linalg.norm(centers - centers[ref_local], axis=1)
    cand = [j for j in np.argsort(d) if j != ref_local and d[j] >= min_base]
    if len(cand) < n_view - 1:                  # fall back if window too tight
        cand = [j for j in np.argsort(d) if j != ref_local]
    return [ref_local] + cand[:n_view - 1]


def run_one(win: int, ref_local: int, n_view: int = 3, device_pref: str = "cpu",
            method: str = "diffmvs", model=None, dev=None):
    man, wdef, _ = _load_meta()
    z = np.load(EXPAC / "windows" / f"win_{win:02d}.npz")
    K_all, w2c_all = z["K"], z["w2c"]
    fidx = wdef[win]["frame_idx"]
    view_local = select_views(K_all, w2c_all, fidx, ref_local, n_view)
    ref_mi = fidx[view_local[0]]

    imgs, Ks, w2cs = [], [], []
    for j in view_local:
        imgs.append(load_image(fidx[j]).transpose(2, 0, 1))
        Ks.append(scaled_K(K_all[j]))
        w2cs.append(w2c_all[j].astype(np.float32))
    Ks = np.stack(Ks); w2cs = np.stack(w2cs)

    dmin, dmax = metric_depth_range(ref_mi, w2cs[0])
    proj = C.make_proj_matrices(Ks, w2cs)
    dv = C.depth_values_tensor(dmin, dmax)

    if model is None:
        dev = C.pick_device(device_pref)
        model, _ = C.build_model(method, dev)
    depth, conf, dt = C.run_inference(model, imgs, proj, dv, dev)

    od = OUT / f"win{win:02d}_ref{ref_local}_{method}"
    od.mkdir(parents=True, exist_ok=True)
    ref_rgb = (imgs[0].transpose(1, 2, 0) * 255).astype(np.uint8)
    cv2.imwrite(str(od / "ref.png"), cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2BGR))
    np.save(od / "depth.npy", depth); np.save(od / "conf.npy", conf)

    # confidence overlay (turbo) blended on ref
    cmap = cv2.applyColorMap((np.clip(conf, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    over = cv2.addWeighted(cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2BGR), 0.45, cmap, 0.55, 0)
    cv2.imwrite(str(od / "conf_overlay.png"), over)
    # depth colormap (inverse for nicer contrast)
    dn = depth.copy(); m = dn > 0
    if m.any():
        dn = (dn - dn[m].min()) / (dn[m].max() - dn[m].min() + 1e-9)
    cv2.imwrite(str(od / "depth_color.png"),
                cv2.applyColorMap((dn * 255).astype(np.uint8), cv2.COLORMAP_MAGMA))

    # backproject ref depth -> world points (+rgb) for fusion later
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    Kr = Ks[0]
    x = (uu - Kr[0, 2]) / Kr[0, 0] * depth
    y = (vv - Kr[1, 2]) / Kr[1, 1] * depth
    cam = np.stack([x, y, depth], -1).reshape(-1, 3)
    R, t = w2cs[0][:3, :3], w2cs[0][:3, 3]
    world = (R.T @ (cam.T - t[:, None])).T
    rgb_flat = ref_rgb.reshape(-1, 3)
    np.savez_compressed(od / "points.npz", xyz=world.astype(np.float32),
                        rgb=rgb_flat.astype(np.uint8),
                        conf=conf.reshape(-1).astype(np.float32),
                        depth=depth.reshape(-1).astype(np.float32))

    print(f"[win{win:02d} ref{ref_local} {method}] views(local)={view_local} ref_mi={ref_mi} "
          f"drange=[{dmin:.2f},{dmax:.2f}] dt={dt:.2f}s "
          f"conf[med={np.median(conf):.3f} %>0.5={100*(conf>0.5).mean():.1f}] -> {od.name}")
    return dict(od=od, dt=dt, depth=depth, conf=conf, ref_rgb=ref_rgb, K=Ks[0], w2c=w2cs[0])


if __name__ == "__main__":
    win = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    ref = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    nv = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    devp = sys.argv[4] if len(sys.argv) > 4 else "cpu"
    meth = sys.argv[5] if len(sys.argv) > 5 else "diffmvs"
    run_one(win, ref, nv, devp, meth)
