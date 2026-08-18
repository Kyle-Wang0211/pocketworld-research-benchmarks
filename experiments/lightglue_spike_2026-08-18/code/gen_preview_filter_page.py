#!/usr/bin/env python3
"""预览显示过滤三窗页:现状 / τ=5cm / τ=3cm(墙区视角)。

复用 build_local_page.py 的 ply: 读取、量化与 TEMPLATE;三朵云都是 237,914 点
(default_rng(20260818) choice,与 ds_dense_238k 同口径)。
⚠️ 这是**预览显示层**过滤:只改预览抽稀云显示哪些点;交付全量云一个点不动。
过滤依据 = 全帧 Delaunay 稀疏锚点平面先验残差 r=|d_MVS−d_prior|(共面性门a,
无先验覆盖的像素不杀),τ 两档 3/5cm。统计见 preview_filter_stats_20260818.json。
"""
import json, sys
from pathlib import Path
import numpy as np

HERE = Path("/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike")
BASE = Path("/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818")
WALL = Path("/Users/kaidongwang/Documents/progecttwo/_artifacts/wall_forensics_20260818")
sys.argv = ["build_local_page.py", "--set", "preview"]   # 只为通过模块级 argparse
sys.path.insert(0, str(HERE))
import build_local_page as blp

ST = json.load(open(HERE / "preview_filter_stats_20260818.json"))
pc = ST["prior_cov"] * 100

def pct(x): return f"{x*100:.1f}%"

PLAN = [
    ("现状(未过滤)", "ds_dense_238k",
     f"30.64M 全量随机抽到 237,914 — 偏移层原样可见",
     dict(pts="237,914", obs="0%", tl="0%", cov="1.000×", rp="不过滤")),
    ("τ=5cm 过滤", "ds_prevfilt_t5",
     f"先验残差>5cm 判杀 — 全局杀 {pct(ST['tau5']['kill_global'])},偏移带杀 {pct(ST['tau5']['kill_band'])},法医偏移层召回 {pct(ST['tau5']['kill_blob_provenance'])}",
     dict(pts="237,914", obs=pct(ST['tau5']['kill_global']), tl=pct(ST['tau5']['kill_band']),
          cov=f"{ST['coverage_voxels']['0.05']['tau5_ratio']:.4f}×", rp="τ=5cm")),
    ("τ=3cm 过滤", "ds_prevfilt_t3",
     f"先验残差>3cm 判杀 — 全局杀 {pct(ST['tau3']['kill_global'])},偏移带杀 {pct(ST['tau3']['kill_band'])},法医偏移层召回 {pct(ST['tau3']['kill_blob_provenance'])}",
     dict(pts="237,914", obs=pct(ST['tau3']['kill_global']), tl=pct(ST['tau3']['kill_band']),
          cov=f"{ST['coverage_voxels']['0.05']['tau3_ratio']:.4f}×", rp="τ=3cm")),
]

# ---- 显示层刚体旋转:进墙系(X=沿墙 u_,Y=重力上 v_,Z=墙法向 r+DW)----
# 只转显示,PLY 落盘件仍是原 gauge;刚体变换不改任何距离。
fl = np.load(WALL / "floor.npy"); up = fl[:3]
nw = np.array([0.46, -0.679, -0.572]); nw /= np.linalg.norm(nw)
u_ = np.cross(up, nw); u_ /= np.linalg.norm(u_); v_ = np.cross(nw, u_)
DW = 4.734
def to_wall_frame(X):
    return np.stack([X @ u_, X @ v_, X @ nw + DW], 1)

keep = []
for label, key, sub, _s in PLAN:
    xyz, rgb = blp.load_ply(HERE / f"{key}.ply")
    keep.append((label, to_wall_frame(xyz), rgb))

lo = np.min([x.min(0) for _, x, _ in keep], axis=0)
span = np.maximum(np.max([x.max(0) for _, x, _ in keep], axis=0) - lo, 1e-6)
print(f"量化步长 {(span / 65535 * 1000).round(3).tolist()} mm/轴(gauge)")

clouds = []
for (label, key, sub, _s), (nm, x, c) in zip(PLAN, keep):
    q = np.round((x - lo) / span * 65535).clip(0, 65535).astype("<u2")
    import base64
    clouds.append(dict(name=nm, sub=sub, n=len(x),
                       xyz=base64.b64encode(q.tobytes()).decode(),
                       rgb=base64.b64encode(np.ascontiguousarray(c).tobytes()).decode()))

# ---- 墙区视角:墙系里墙盒中心=(pu=-2, pv=0, r=0),真实拍摄距离 ~4.5 gauge ----
# 观墙相机(fr78-125)在墙系 Z∈[1.3,6.6],均值 4.5;初始视角取略斜(az=0.5)让偏移层可辨
az, el, dist = -0.5, 0.05, 9.5
print(f"墙区视角(墙系): az={az} el={el} dist={dist}")

view = dict(cx=-2.0, cy=0.0, cz=0.0,
            radius=2.5, lo=lo.astype(float).tolist(), span=span.astype(float).tolist())

STATS = {label: s for label, _k, _sub, s in PLAN}
html = (blp.TEMPLATE
        .replace("__DATA__", json.dumps(clouds))
        .replace("__VIEW__", json.dumps(view))
        .replace("__NCOL__", "3")
        .replace("__STATS__", json.dumps(STATS))
        .replace("<title>覆盖对比 — 四臂并排</title>",
                 "<title>预览显示过滤 — 现状 vs τ5 vs τ3</title>")
        .replace("覆盖对比 — b28(132 帧,同一场拍摄,全部在同一张 5090 上产出)",
                 "预览显示过滤 — 现状 / τ=5cm / τ=3cm(墙区视角,三窗相机同步)")
        .replace("拖拽旋转 · 滚轮缩放 · 右键平移 —— 四窗相机同步。已用相机光心统一 gauge(相似变换保形)。坐标按亚毫米量化以压体积,点一个没少。",
                 "⚠️ 这是<b>预览显示层</b>过滤:只决定预览抽稀云显示哪些点,<b>交付全量云一个点不动</b>。"
                 "三窗各 237,914 点(与 ds_dense_238k 同抽稀口径)。过滤依据=全帧稀疏锚点 Delaunay 平面先验残差,"
                 f"先验覆盖 {pc:.1f}%,无先验处不杀。拖拽旋转 · 滚轮缩放 · 右键平移。")
        .replace("const cam={az:0.6,el:0.35,dist:VIEW.radius*2.4,tx:VIEW.cx,ty:VIEW.cy,tz:VIEW.cz};",
                 f"const cam={{az:{az:.4f},el:{el:.4f},dist:{dist*0.85:.3f},tx:VIEW.cx,ty:VIEW.cy,tz:VIEW.cz}};")
        .replace("<tr><td>观测</td>", "<tr><td>全局杀点</td>")
        .replace("<tr><td>轨迹均值</td>", "<tr><td>偏移带杀点</td>")
        .replace("<tr><td>覆盖(0.2m 体素)</td>", "<tr><td>覆盖0.05m格(全量云)</td>")
        .replace("<tr><td>重投影 px</td>", "<tr><td>口径</td>"))
OUT = HERE / "compare_preview_filter.html"
OUT.write_text(html)
print(f"已写出 {OUT}  {OUT.stat().st_size/1e6:.1f} MB")
