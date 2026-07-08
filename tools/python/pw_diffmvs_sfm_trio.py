"""Controlled 3-way dense run: same CasDiffMVS pipeline, three SfM pose sources.

For each of three COLMAP binary models (base / p4354 / ftol) of the SAME 414-frame
capture, run the exact casdiffmvs + geomcons(g3 p0.3) recipe with poses+intrinsics+
depth-ranges read from THAT model (pycolmap). Everything else is held fixed:
  - identical reference subset: every 4th frame of the sorted intersection of
    frames registered in ALL THREE models (413 -> 104 refs), spatial-manifest order
  - identical source-view selection LOGIC (covis MVSNet score, fallback nearest
    with metric min-baseline 6cm), identical fusion params (NVIEW=5, NEIGH=8,
    GEO_PIX=1.0, GEO_DEP=0.01, geo>=3, conf>0.3, NORMAL_COS=0.5, BOUND_REL=0.03)
  - identical images (896x512), device (MPS), cleanup (voxel 5mm + stat outlier)
    -- cleanup and export are done AFTER robust-umeyama alignment into the ARKit
    metric frame, so thresholds are physically identical across models.
  - baseline gates (0.06 / 0.04 m) are converted into each model's own units via
    its umeyama scale so they are metrically identical too.

Usage: KMP_DUPLICATE_LIB_OK=TRUE python3.11 pw_diffmvs_sfm_trio.py TAG [REF_LIMIT]
  TAG in {base, p4354, ftol};  REF_LIMIT (int) = only first N refs (smoke test).
"""
from __future__ import annotations
import os, sys, json, time
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
from pathlib import Path
import numpy as np
import cv2
import open3d as o3d
import torch
import pw_diffmvs_common as C
import pw_diffmvs_run as R
# NOTE: pycolmap is NOT imported here -- it cannot share a process with torch on
# this Mac (duplicate libomp -> SIGSEGV). Run pw_diffmvs_sfm_trio_dump.py first.

sys.path.insert(0, str(Path(__file__).resolve().parent / "diffmvs"))
from filter import check_geometric_consistency  # noqa: E402
import inspect as _inspect  # noqa: E402
# [#7 2026-07-08] free-space reuse of reproject_with_depth's xyz_src[2] needs a
# patched filter.py (return_ref_depth_src kwarg). diffmvs/ is gitignored, so a fresh
# clone has vanilla filter.py -> detect support and gracefully fall back to recompute.
_CGC_HAS_REFDEPTH = ("return_ref_depth_src"
                     in _inspect.signature(check_geometric_consistency).parameters)

SCRATCH = Path("/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/"
               "7fc69efe-e09c-4359-8afb-04378874d3a1/scratchpad")
sys.path.insert(0, str(SCRATCH))
import geom_metrics as g  # noqa: E402  (arkit_centers_and_R + umeyama, proven)

MODELS = {
    "base":  SCRATCH / "jfix/recon_gc",
    "p4354": Path("/private/tmp/knife4354/C4354/0"),
    "ftol":  Path("/private/tmp/knifeFTOL/FT2b/0"),
    "f0b":   Path("/private/tmp/knifeFTOL/F0b/0"),   # 现行认证配置(归因A)
    "ft0":   Path("/private/tmp/knifeFT0/FT0/0"),    # 内部ftol1e-4+收尾满BA(归因B)
    "r3":    Path("/private/tmp/knifeR3/R3/0"),      # FT2快配置+rounds=3(归因C)
    "lapa":  Path("/private/tmp/knifeLAPcert/LAPa/0"),  # 新认证+DENSE_SCHUR/LAPACK收尾
    "r3b":   Path("/private/tmp/knifeR3cert/R3b/0"),    # 新认证复跑 rounds3+ftol
    "g1":    Path("/private/tmp/knifeG12/G1/0"),     # 冠军组合+收尾ftol1e-7深收敛
    "g2":    Path("/private/tmp/knifeG12/G2/0"),     # G1+内部ftol1e-5金级
    "piter": Path("/private/tmp/knifePITER/PITER/0"),  # 冠军组合+内部换回金时代ITER+SJ
    "r4":    Path("/private/tmp/knifeR3cert/R4/0"),  # rounds=4
    "r5":    Path("/private/tmp/knifeR3cert/R5/0"),  # rounds=5
    "lapatight": Path("/private/tmp/lapa_tight"),    # LAPa后置紧过滤(151k稀疏点)
    "ss":    Path("/private/tmp/knifeSS/SS/0"),      # 冠军配方+CHOLMOD/SuiteSparse收尾(金指纹)
    "grav":  Path("/private/tmp/knifeGRAV/GRAV/0"),  # 冠军配方+ARKit重力RA+flip修复
    "ann":   Path("/private/tmp/knifeNIGHT/ANN/0"),  # 冠军配方+逐轮loss退火2→1→0.5
    "champrot5": Path("/private/tmp/knifeTH/CHAMP_ROT5/0"),  # 阈值标定保守:旋转过滤10°→5°
    "combora3":  Path("/private/tmp/knifeTH/COMBO_RA3/0"),   # 阈值标定激进:旋转5°+track角度门×0.66
    "fingold":   Path("/private/tmp/knifeFIN/FIN_GOLD/0"),   # 金收尾复刻:金B0+CHOLMOD/SuiteSparse+ftol0+3x100
    "finlapdeep":Path("/private/tmp/knifeFIN/FIN_LAPDEEP/0"),# 金B0+DENSE_SCHUR/LAPACK+ftol0+3x100(隔离深度)
    "baseredense": SCRATCH / "jfix/recon_gc",               # 对照1:今日管线重稠密化EXACT金稀疏recon_gc(应≈mvs_base)
    "baseredense2": SCRATCH / "jfix/recon_gc",              # 元判决:金同一稀疏 recon_gc 今日第2次独立稠密(MPS推理+融合抽样非确定性)
    "baseredense3": SCRATCH / "jfix/recon_gc",              # 元判决:金同一稀疏 recon_gc 今日第3次独立稠密(MPS推理+融合抽样非确定性)
    # ---- 稠密融合严格度扫描(唯一变量=融合门;复用金/冠军 p1cache 跳过 MPS 重推理)----
    "strictgoldp5":    SCRATCH / "jfix/recon_gc",          # 金 recon_gc + PHOTO0.5(其余同金)
    "strictgoldg4p4":  SCRATCH / "jfix/recon_gc",          # 金 recon_gc + PHOTO0.4 + GEO_MASK4
    "strictchampp5":   Path("/private/tmp/knifeLAPcert/LAPa/0"),   # 冠军 lapa + PHOTO0.5
    "strictchampg4p4": Path("/private/tmp/knifeLAPcert/LAPa/0"),   # 冠军 lapa + PHOTO0.4 + GEO_MASK4
    # ---- 光度门甜点扫描(冠军 lapa,复用冻结 p1cache,GEO_MASK=3 保覆盖)----
    "champp55": Path("/private/tmp/knifeLAPcert/LAPa/0"),          # 冠军 lapa + PHOTO0.55
    "champp6":  Path("/private/tmp/knifeLAPcert/LAPa/0"),          # 冠军 lapa + PHOTO0.6
    "champp7":  Path("/private/tmp/knifeLAPcert/LAPa/0"),          # 冠军 lapa + PHOTO0.7
    # ---- CasDiffMVS 破局:冠军 lapa 稀疏,修复喂废的稠密网络(分辨率 + blend ckpt)----
    # 全部强制 MPS 重推理(独立 p1cache),融合门 = 生产同款 g3 p0.5(o 档已验证更优)
    "blend":       Path("/private/tmp/knifeLAPcert/LAPa/0"),  # 896x512 + casdiffmvs_blend(隔离 ckpt)
    "res15":       Path("/private/tmp/knifeLAPcert/LAPa/0"),  # 1344x768(1.5x)+ DTU(隔离分辨率)
    "res15blend":  Path("/private/tmp/knifeLAPcert/LAPa/0"),  # 1.5x + blend(合击 ship 候选)
    "res2blend":   Path("/private/tmp/knifeLAPcert/LAPa/0"),  # 1792x1024(2x)+ blend(激进档)
    # blend-family 融合门标定(复用冻结 cache,只扫 PHOTO):
    "blendp10": Path("/private/tmp/knifeLAPcert/LAPa/0"), "blendp15": Path("/private/tmp/knifeLAPcert/LAPa/0"),
    "blendp20": Path("/private/tmp/knifeLAPcert/LAPa/0"), "blendp25": Path("/private/tmp/knifeLAPcert/LAPa/0"),
    "blendp30": Path("/private/tmp/knifeLAPcert/LAPa/0"),
    "r15bp15":  Path("/private/tmp/knifeLAPcert/LAPa/0"), "r15bp20":  Path("/private/tmp/knifeLAPcert/LAPa/0"),
    "r2bp15":   Path("/private/tmp/knifeLAPcert/LAPa/0"), "r2bp20":   Path("/private/tmp/knifeLAPcert/LAPa/0"),
    # ---- REF_STRIDE=1 全量覆盖版(每帧算深度图,像 RealityScan)[2026-07-06]----
    # 唯一变量 = trio_refs.json refs 从 stride4(104)改 stride1(413);其余全同 STRICT o/gold。
    # 效率:7full 建 lapa stride1 cache,ofull 复用同一 cache 只换 PHOTO 融合(零重推理)。
    "1full": SCRATCH / "jfix/recon_gc",                    # 金 recon_gc + PHOTO0.3(金原配)
    "7full": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # 冠军 lapa + PHOTO0.3(建 stride1 cache)
    "ofull": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # 冠军 lapa + PHOTO0.5(复用 7full cache)
    # ---- 边框/浮渣清理正交扫描(冠军 ofull=lapa stride1 PHOTO0.5,复用 7full 冻结 cache)----
    # 唯一变量 = pass2 清理旋钮(BOUND_REL / NORMAL_COS / 光度颜色一致性 / 边缘腐蚀);
    # 零 MPS 重推理(全走 CACHE_SRC 复用 7full stride1 cache)。[2026-07-06]
    # A. BOUND_REL 边缘梯度门扫描:
    "ob02":  Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + BOUND_REL 0.03->0.02
    "ob015": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + BOUND_REL 0.03->0.015
    "ob01":  Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + BOUND_REL 0.03->0.01
    # A. NORMAL_COS 法向门扫描:
    "on07":  Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + NORMAL_COS 0.5->0.7
    "on08":  Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + NORMAL_COS 0.5->0.8
    # B. 光度(颜色)一致性(Gipuma/Merrell 风格,反投影取 src 颜色 vs ref 颜色):
    "opc10": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + color-consistency τ=0.10 (0-1) N>=1
    "opc06": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + color-consistency τ=0.06 N>=1
    "opc04": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + color-consistency τ=0.04 N>=2
    # C. 组合"o 清理版":最优边缘门 + 最优法向门 + 光度一致性 + 1px 腐蚀:
    "oclean": Path("/private/tmp/knifeLAPcert/LAPa/0"),    # 组合清理版(候选 ship 配方)
    "olite":  Path("/private/tmp/knifeLAPcert/LAPa/0"),    # 轻组合:只 BOUND_REL0.015 + PHOTO_COLOR0.06(不叠 NORMAL/erode)
    # ---- free-space 看穿票去飞点(Merrell ICCV07,正交于边缘位置)[2026-07-06]----
    "ofs2":  Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + FREESPACE_N=2(被2视图看穿则删)
    "ofs3":  Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + FREESPACE_N=3
    "ofs4":  Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + FREESPACE_N=4(最保守)
    "ofsx":  Path("/private/tmp/knifeLAPcert/LAPa/0"),     # olite + FREESPACE_N=2(边缘门0.015+颜色0.06+看穿)ship候选
    # ---- 重投影残差门(被 threshold 后丢弃的残差值)+ 法向已进输出 [2026-07-07]----
    "oq004": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + REPROJ_ERR_MAX=0.004(隔离残差门)
    "oq006": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofull + REPROJ_ERR_MAX=0.006
    "ofsxq": Path("/private/tmp/knifeLAPcert/LAPa/0"),     # ofsx + 残差门:边缘+颜色+看穿+残差 全信号 ship 终选
}
# CasDiffMVS 破局矩阵:每档 = (源模型, 渲染分辨率 W,H, checkpoint 域, 融合门)
# 分辨率必须被 32 整除(级联 1/8 下采样 + base=32 对齐,见 datasets/mvs.py:104-115)。
# K 从 dump(baked @896x512)按 (W/896, H/512) 重缩放;图像从原生 4224x2376 直接 resize
# 到目标分辨率(远低于原生,无上采样)。融合门用 g3 p0.5(与冠军 o 档 strictchampp5 同)。
BREAK = {
    "blend":      {"src": "lapa", "W": 896,  "H": 512,  "CKPT": "blend", "PHOTO": 0.5, "GEO_MASK": 3},
    "res15":      {"src": "lapa", "W": 1344, "H": 768,  "CKPT": "dtu",   "PHOTO": 0.5, "GEO_MASK": 3},
    "res15blend": {"src": "lapa", "W": 1344, "H": 768,  "CKPT": "blend", "PHOTO": 0.5, "GEO_MASK": 3},
    "res2blend":  {"src": "lapa", "W": 1792, "H": 1024, "CKPT": "blend", "PHOTO": 0.5, "GEO_MASK": 3},
}
# 严格度扫描的每档融合门(源自复用 base/lapa 的 p1cache,推理冻结;仅 pass2 变)
STRICT = {
    "strictgoldp5":    {"src": "base", "PHOTO": 0.5, "GEO_MASK": 3},
    "strictgoldg4p4":  {"src": "base", "PHOTO": 0.4, "GEO_MASK": 4},
    "strictchampp5":   {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3},
    "strictchampg4p4": {"src": "lapa", "PHOTO": 0.4, "GEO_MASK": 4},
    "champp55":        {"src": "lapa", "PHOTO": 0.55, "GEO_MASK": 3},
    "champp6":         {"src": "lapa", "PHOTO": 0.6,  "GEO_MASK": 3},
    "champp7":         {"src": "lapa", "PHOTO": 0.7,  "GEO_MASK": 3},
    # ---- blend-checkpoint 融合门标定(blend conf 尺度 != DTU;p0.5 砍光点)----
    # 复用 blend/res15blend/res2blend 的冻结 p1cache(raw depth+conf),只扫 PHOTO,零重推理。
    # src 只用于取 K/w2c 模型 dump(全 lapa 稀疏);cache 由 CACHE_SRC 指定(见下)。
    # blend@896 门扫:
    "blendp10": {"src": "lapa", "PHOTO": 0.10, "GEO_MASK": 3},
    "blendp15": {"src": "lapa", "PHOTO": 0.15, "GEO_MASK": 3},
    "blendp20": {"src": "lapa", "PHOTO": 0.20, "GEO_MASK": 3},
    "blendp25": {"src": "lapa", "PHOTO": 0.25, "GEO_MASK": 3},
    "blendp30": {"src": "lapa", "PHOTO": 0.30, "GEO_MASK": 3},
    # res15blend@1344 + 正确 blend 门(标定后填最优;先扫同档):
    "r15bp15":  {"src": "lapa", "PHOTO": 0.15, "GEO_MASK": 3},
    "r15bp20":  {"src": "lapa", "PHOTO": 0.20, "GEO_MASK": 3},
    # res2blend@1792 + 正确 blend 门:
    "r2bp15":   {"src": "lapa", "PHOTO": 0.15, "GEO_MASK": 3},
    "r2bp20":   {"src": "lapa", "PHOTO": 0.20, "GEO_MASK": 3},
    # ---- REF_STRIDE=1 全量覆盖(413 refs via trio_refs.json)----
    # 896x512 DTU GEO_MASK3;1full/7full 各自 FRESH MPS stride1 推理(own cache);
    # ofull 走 CACHE_SRC 复用 7full 冻结 cache 只换 PHOTO0.5。
    "1full": {"src": "base", "PHOTO": 0.3, "GEO_MASK": 3},
    "7full": {"src": "lapa", "PHOTO": 0.3, "GEO_MASK": 3},
    "ofull": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3},
    "ofsonly": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "FREESPACE_N": 2},  # o + 只加看穿票飞点门(杀空中碎片不砍覆盖)
    # ---- 清理正交扫描(全部 = ofull 基线 lapa/PHOTO0.5/g3 + 一个清理旋钮变量)----
    # 可选清理键(缺省=沿用 ofull 现行值,保 o 复现):
    #   BOUND_REL(默认 0.03)/ NORMAL_COS(默认 0.5)/
    #   PHOTO_COLOR(默认 None=关) = 反投影 src 颜色 vs ref 颜色 |Δ|<τ 的阈值(0-1 RGB L1/3)/
    #   PHOTO_COLOR_N(默认 1) = 需要多少个 src 视图颜色一致 /
    #   ERODE_PX(默认 0=关) = final mask 形态学腐蚀像素半径。
    "ob02":  {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "BOUND_REL": 0.02},
    "ob015": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "BOUND_REL": 0.015},
    "ob01":  {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "BOUND_REL": 0.01},
    "on07":  {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "NORMAL_COS": 0.7},
    "on08":  {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "NORMAL_COS": 0.8},
    "opc10": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "PHOTO_COLOR": 0.10, "PHOTO_COLOR_N": 1},
    "opc06": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "PHOTO_COLOR": 0.06, "PHOTO_COLOR_N": 1},
    "opc04": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "PHOTO_COLOR": 0.04, "PHOTO_COLOR_N": 2},
    # 组合清理版(最优边缘门+法向门+光度一致性+1px 腐蚀;下方三值待 A/B 判读后回填最优)
    "oclean": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3,
               "BOUND_REL": 0.015, "NORMAL_COS": 0.7,
               "PHOTO_COLOR": 0.06, "PHOTO_COLOR_N": 1, "ERODE_PX": 1},
    # 轻组合清理版(比 oclean 少叠 NORMAL 收紧 + erode):只两个外科门,保满覆盖
    # NORMAL_COS 保持默认 0.5,ERODE_PX 保持默认 0(不写=不叠)
    "olite":   {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3,
                "BOUND_REL": 0.015, "PHOTO_COLOR": 0.06, "PHOTO_COLOR_N": 1},
    # free-space 看穿票去飞点(正交于边缘门):删被 >= N 个 src 视图看穿的悬空点
    "ofs2": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "FREESPACE_N": 2},
    "ofs3": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "FREESPACE_N": 3},
    "ofs4": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "FREESPACE_N": 4},
    # ship 候选:olite 两个外科门 + 看穿票(边缘0.015 + 颜色0.06 + free-space N=2)
    "ofsx": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3,
             "BOUND_REL": 0.015, "PHOTO_COLOR": 0.06, "PHOTO_COLOR_N": 1, "FREESPACE_N": 2},
    # 重投影残差门(隔离 + 全信号组合)
    "oq004": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "REPROJ_ERR_MAX": 0.004},
    "oq006": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3, "REPROJ_ERR_MAX": 0.006},
    "ofsxq": {"src": "lapa", "PHOTO": 0.5, "GEO_MASK": 3,
              "BOUND_REL": 0.015, "PHOTO_COLOR": 0.06, "PHOTO_COLOR_N": 1,
              "FREESPACE_N": 2, "REPROJ_ERR_MAX": 0.005},
}
# gate-sweep 复用哪个 BREAK 的冻结 cache + 该 cache 的渲染分辨率(用于 K 重缩放,
# 因 pass2 反投影 K 必须与推理分辨率一致)。res15blend=1344x768,res2blend=1792x1024。
CACHE_SRC = {
    "blendp10": ("blend", 896, 512),   "blendp15": ("blend", 896, 512),
    "blendp20": ("blend", 896, 512),   "blendp25": ("blend", 896, 512),
    "blendp30": ("blend", 896, 512),
    "r15bp15":  ("res15blend", 1344, 768),  "r15bp20": ("res15blend", 1344, 768),
    "r2bp15":   ("res2blend", 1792, 1024),  "r2bp20":  ("res2blend", 1792, 1024),
    # ofull 复用 7full 的 stride1 冻结 cache(896x512,冠军 lapa 深度图),只换 PHOTO0.5
    "ofull":    ("7full", 896, 512),
    # 清理正交扫描全部复用 7full stride1 冻结 cache(零 MPS 重推理),只改 pass2 清理旋钮
    "ob02":  ("7full", 896, 512), "ob015": ("7full", 896, 512), "ob01": ("7full", 896, 512),
    "on07":  ("7full", 896, 512), "on08":  ("7full", 896, 512),
    "opc10": ("7full", 896, 512), "opc06": ("7full", 896, 512), "opc04": ("7full", 896, 512),
    "oclean": ("7full", 896, 512),
    "olite": ("7full", 896, 512),
    "ofs2": ("7full", 896, 512), "ofs3": ("7full", 896, 512), "ofs4": ("7full", 896, 512),
    "ofsx": ("7full", 896, 512),
    "oq004": ("7full", 896, 512), "oq006": ("7full", 896, 512), "ofsxq": ("7full", 896, 512),
}
VIEWER_PLY = {"base": "mvs_base.ply", "p4354": "mvs_4354.ply", "ftol": "mvs_ftol.ply",
              "f0b": "mvs_f0b.ply", "ft0": "mvs_ft0.ply", "r3": "mvs_r3.ply",
              "lapa": "mvs_lapa.ply", "r3b": "mvs_r3b.ply",
              "g1": "mvs_g1.ply", "g2": "mvs_g2.ply", "piter": "mvs_piter.ply",
              "r4": "mvs_r4.ply", "r5": "mvs_r5.ply", "lapatight": "mvs_lapatight.ply",
              "ss": "mvs_ss.ply", "grav": "mvs_grav.ply", "ann": "mvs_ann.ply",
              "champrot5": "mvs_champrot5.ply", "combora3": "mvs_combora3.ply",
              "fingold": "mvs_fingold.ply", "finlapdeep": "mvs_finlapdeep.ply",
              "baseredense": "mvs_baseredense.ply",
              "baseredense2": "mvs_baseredense2.ply",
              "baseredense3": "mvs_baseredense3.ply",
              "strictgoldp5": "mvs_strictgoldp5.ply",
              "strictgoldg4p4": "mvs_strictgoldg4p4.ply",
              "strictchampp5": "mvs_strictchampp5.ply",
              "strictchampg4p4": "mvs_strictchampg4p4.ply",
              "champp55": "mvs_champp55.ply",
              "champp6": "mvs_champp6.ply",
              "champp7": "mvs_champp7.ply",
              "blend": "mvs_blend.ply",
              "res15": "mvs_res15.ply",
              "res15blend": "mvs_res15blend.ply",
              "res2blend": "mvs_res2blend.ply",
              "blendp10": "mvs_blendp10.ply", "blendp15": "mvs_blendp15.ply",
              "blendp20": "mvs_blendp20.ply", "blendp30": "mvs_blendp30.ply",
              "r15bp15": "mvs_r15bp15.ply", "r15bp20": "mvs_r15bp20.ply",
              "r2bp15": "mvs_r2bp15.ply", "r2bp20": "mvs_r2bp20.ply",
              "1full": "mvs_1full.ply", "7full": "mvs_7full.ply",
              "ofull": "mvs_ofull.ply",
              "ob02": "mvs_ob02.ply", "ob015": "mvs_ob015.ply", "ob01": "mvs_ob01.ply",
              "on07": "mvs_on07.ply", "on08": "mvs_on08.ply",
              "opc10": "mvs_opc10.ply", "opc06": "mvs_opc06.ply", "opc04": "mvs_opc04.ply",
              "oclean": "mvs_oclean.ply", "olite": "mvs_olite.ply",
              "ofs2": "mvs_ofs2.ply", "ofs3": "mvs_ofs3.ply", "ofs4": "mvs_ofs4.ply",
              "ofsx": "mvs_ofsx.ply",
              "oq004": "mvs_oq004.ply", "oq006": "mvs_oq006.ply", "ofsxq": "mvs_ofsxq.ply"}
OUTDIR = Path(os.path.expanduser("~/Desktop/tiled_414_viewer"))
OUT = R.OUT
FULL_W, FULL_H = 4224, 2376
PROC_W, PROC_H = R.PROC_W, R.PROC_H            # 896 x 512
METHOD = "casdiffmvs"
NVIEW, NEIGH = 5, 8
GEO_MASK, PHOTO, GEO_PIX, GEO_DEP = 3, 0.5, 1.0, 0.01   # [CERTIFIED 2026-07-06] PHOTO 0.3->0.5 (o): +3-5% eyeball vs 0.3, full coverage, free; PHOTO>=0.5 is plateau
NORMAL_COS, BOUND_REL = 0.5, 0.03
MIN_BASE_SRC_M, MIN_BASE_FUSE_M = 0.06, 0.04   # metres (converted to model units)
# [PRODUCTION DEFAULT = "o", certified 2026-07-07] 冠军 lapa SfM + REF_STRIDE=1 全覆盖
# (每帧算深度图,覆盖=稀疏全量,像 RealityScan) + PHOTO=0.5 融合门。清理(free-space/
# 残差/边缘门)对点云交付有益但对 TSDF 网格是净损(TSDF 自身体素平均去噪),故默认关。
# 研究期对照实验可显式传更大 stride 提速。
REF_STRIDE = 1
REFS_JSON = OUT / "trio_refs.json"


def name2mi_map():
    man, _, _ = R._load_meta()
    return {Path(f["jpegPath"]).name: i for i, f in enumerate(man)}


def load_model(tag: str):
    """Read the torch-free dump produced by pw_diffmvs_sfm_trio_dump.py."""
    z = np.load(OUT / f"trio_model_{tag}.npz", allow_pickle=False)
    names = z["names"].tolist()
    K_of = {n: z["K"][i] for i, n in enumerate(names)}
    w2c_of = {n: z["w2c"][i] for i, n in enumerate(names)}
    center_of = {n: z["centers"][i] for i, n in enumerate(names)}
    off = z["obs_off"]; idx = z["obs_idx"]
    obs = {n: idx[off[i]:off[i + 1]] for i, n in enumerate(names)}
    pts = z["pts"]                                 # (P,3): obs are indices into pts
    return names, K_of, w2c_of, center_of, obs, pts


def robust_align(center_of, ark):
    """Trimmed umeyama model camera centers -> ARKit centers (align_export_ab logic)."""
    common = sorted(set(center_of) & set(ark))
    src = np.array([center_of[n] for n in common])
    dst = np.array([ark[n][0] for n in common])
    keep = np.ones(len(src), bool)
    for _ in range(8):
        s, Rm, t = g.umeyama(src[keep], dst[keep])
        res = np.linalg.norm((s * (Rm @ src.T).T + t) - dst, axis=1)
        thr = np.median(res[keep]) * 3 + 1e-9
        nk = res < thr
        if nk.sum() == keep.sum() or nk.sum() < 50:
            keep = nk; break
        keep = nk
    s, Rm, t = g.umeyama(src[keep], dst[keep])
    res = np.linalg.norm((s * (Rm @ src.T).T + t) - dst, axis=1)
    print(f"align->ARKit: common={len(common)} inliers={int(keep.sum())} "
          f"scale={s:.4f} med_resid={np.median(res)*1000:.1f}mm", flush=True)
    return s, Rm, t


def build_refs():
    """Fixed ref subset shared by all three runs (written by the dump script)."""
    assert REFS_JSON.exists(), "run pw_diffmvs_sfm_trio_dump.py first"
    d = json.load(open(REFS_JSON))
    return d["pool"], d["refs"]


def covis_select(n, pool, center_of, obs_set, obs, pts_arr, k):
    """MVSNet triangulation-angle view score on the model's own sparse points
    (verbatim logic from pw_diffmvs_sfm.py)."""
    ref = obs.get(n)
    if ref is None or len(ref) < 8:
        return None
    ref_set = obs_set[n]; c_ref = center_of[n]; t0, s1, s2 = 5.0, 1.0, 10.0
    scored = []
    for m in pool:
        if m == n:
            continue
        shared = ref_set & obs_set[m]
        if len(shared) < 5:
            continue
        P = pts_arr[np.fromiter(shared, np.int64, len(shared))]
        v1 = P - c_ref; v2 = P - center_of[m]
        v1 /= np.linalg.norm(v1, axis=1, keepdims=True) + 1e-9
        v2 /= np.linalg.norm(v2, axis=1, keepdims=True) + 1e-9
        ang = np.degrees(np.arccos(np.clip((v1 * v2).sum(1), -1, 1)))
        sc = np.where(ang <= t0, np.exp(-(ang - t0) ** 2 / (2 * s1 ** 2)),
                      np.exp(-(ang - t0) ** 2 / (2 * s2 ** 2)))
        scored.append((float(sc.sum()), m))
    if len(scored) < k:
        return None
    scored.sort(reverse=True)
    return [m for _, m in scored[:k]]


def world_normals(depth, K, w2c):
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu - K[0, 2]) / K[0, 0] * depth
    y = (vv - K[1, 2]) / K[1, 1] * depth
    P = np.stack([x, y, depth], -1)
    du = np.zeros_like(P); dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]; dv[1:-1] = P[2:] - P[:-2]
    nrm = np.cross(du, dv); ln = np.linalg.norm(nrm, axis=-1, keepdims=True)
    nrm = np.divide(nrm, ln, out=np.zeros_like(nrm), where=ln > 1e-9)
    nrm[(np.sum(nrm * P, -1) > 0)] *= -1
    nw = nrm.reshape(-1, 3) @ w2c[:3, :3]
    return nw.reshape(H, W, 3).astype(np.float32)


def boundary_keep(depth, rel=BOUND_REL):
    gx = np.zeros_like(depth); gy = np.zeros_like(depth)
    gx[:, 1:-1] = np.abs(depth[:, 2:] - depth[:, :-2])
    gy[1:-1] = np.abs(depth[2:] - depth[:-2])
    grad = np.maximum(gx, gy)
    return (grad / np.maximum(depth, 1e-6) < rel) & (depth > 0)


def ref_depth_in_src(d_ref, K_ref, ext_ref, ext_src):
    """z-coord of each ref pixel's 3D point in the src camera frame (how far the
    ref point is FROM the src camera). Same xyz_src[2] that reproject_with_depth
    computes internally but discards. Used for free-space (seen-through) test:
    a ref point is a flying pixel iff src sees a farther surface behind it, i.e.
    sampled_depth_src > ref_depth_in_src + tau -> src's ray passes THROUGH it.
    This cue is orthogonal to edge-location (gradient/normal/color) gates."""
    H, W = d_ref.shape
    xr, yr = np.meshgrid(np.arange(W), np.arange(H))
    xr = xr.reshape(-1); yr = yr.reshape(-1)
    xyz_ref = np.matmul(np.linalg.inv(K_ref),
                        np.vstack((xr, yr, np.ones_like(xr))) * d_ref.reshape(-1))
    xyz_src = np.matmul(np.matmul(ext_src, np.linalg.inv(ext_ref)),
                        np.vstack((xyz_ref, np.ones_like(xr))))[:3]
    return xyz_src[2].reshape(H, W).astype(np.float32)


def write_ply(path, xyz, rgb, normals=None):
    n = len(xyz)
    has_n = normals is not None
    nprops = ("property float nx\nproperty float ny\nproperty float nz\n" if has_n else "")
    hdr = (f"ply\nformat binary_little_endian 1.0\nelement vertex {n}\n"
           "property float x\nproperty float y\nproperty float z\n"
           f"{nprops}"
           "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    fields = [('x', '<f4'), ('y', '<f4'), ('z', '<f4')]
    if has_n: fields += [('nx', '<f4'), ('ny', '<f4'), ('nz', '<f4')]
    fields += [('r', 'u1'), ('g', 'u1'), ('b', 'u1')]
    rec = np.zeros(n, dtype=fields)
    rec['x'], rec['y'], rec['z'] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    if has_n: rec['nx'], rec['ny'], rec['nz'] = normals[:, 0], normals[:, 1], normals[:, 2]
    rec['r'], rec['g'], rec['b'] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    with open(path, 'wb') as f:
        f.write(hdr.encode()); f.write(rec.tobytes())
    print(f"wrote {path}  {n:,} pts  {os.path.getsize(path)/1e6:.1f}MB "
          f"{'(+normals)' if has_n else ''}", flush=True)


# ------------------------------------------------------------------------------
# pass-2 fusion worker  (each ref is fully independent: only reads the shared
# depth/conf/K/w2c/drange dicts + the ref's own depth map; concatenation order of
# the returned per-ref points does NOT change the output point SET, only its row
# order -- voxel/SOR/PLY are order-agnostic).  Refactored so one ref = one call so
# the outer `for n in refs` loop can be farmed to a multiprocessing.Pool.
# ------------------------------------------------------------------------------
# _FUSE_CTX holds every read-only input the per-ref body needs.  In the serial
# path (default) main() sets it directly; in the parallel path the Pool `fork`
# initializer inherits it via copy-on-write (macOS spawn fallback repopulates it,
# see _fuse_pool_init).  Keeping it a plain module global means the huge depth/conf
# dicts are shared, never pickled per task.
_FUSE_CTX: dict = {}


def _getnrm_ctx(m):
    ctx = _FUSE_CTX
    nc = ctx.get("normals")                       # per-frame cache (byte-identical)
    if nc is not None and m in nc:
        return nc[m]
    return world_normals(ctx["depth"][m], ctx["K_of"][m].astype(np.float64),
                         ctx["w2c_of"][m].astype(np.float64))


def _nearest_ctx(n, k, cand, min_base):
    ctx = _FUSE_CTX; center_of = ctx["center_of"]
    c0 = center_of[n]
    d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in cand if m != n)
    return [m for dist, m in d if dist >= min_base][:k]


def _fuse_one_ref(n):
    """Compute this ref's fused points/colours/normals. Verbatim body of the old
    `for n in refs` loop -- must stay bit-identical so serial and parallel agree."""
    ctx = _FUSE_CTX
    depth = ctx["depth"]; conf = ctx["conf"]; drng = ctx["drng"]
    K_of = ctx["K_of"]; w2c_of = ctx["w2c_of"]; refs = ctx["refs"]
    name2mi = ctx["name2mi"]; NEIGH = ctx["NEIGH"]; min_base_fuse = ctx["min_base_fuse"]
    GEO_PIX = ctx["GEO_PIX"]; GEO_DEP = ctx["GEO_DEP"]; NORMAL_COS = ctx["NORMAL_COS"]
    GEO_MASK = ctx["GEO_MASK"]; PHOTO = ctx["PHOTO"]; BOUND_REL = ctx["BOUND_REL"]
    photo_color = ctx["photo_color"]; photo_color_n = ctx["photo_color_n"]
    erode_kernel = ctx["erode_kernel"]; freespace_n = ctx["freespace_n"]
    freespace_tau = ctx["freespace_tau"]; reproj_err_max = ctx["reproj_err_max"]

    d_ref = depth[n]; K_ref = K_of[n].astype(np.float64)
    ext_ref = w2c_of[n].astype(np.float64)
    dmin, dmax = drng[n]; n_ref = _getnrm_ctx(n)
    ref_rgb01 = R.load_image(name2mi[n])                 # HxWx3 float [0,1]
    geo_sum = np.zeros_like(d_ref, np.int32); depth_acc = d_ref.copy()
    color_agree_sum = np.zeros_like(d_ref, np.int32)
    freespace_sum = np.zeros_like(d_ref, np.int32)
    rerr_acc = np.zeros_like(d_ref, np.float32)
    d_ref_in_nb = None
    # [2026-07-08] free-space only: reuse the ref-depth-in-src map that
    # check_geometric_consistency's reproject_with_depth already computes internally
    # (xyz_src[2]) instead of re-deriving the identical matmul chain via
    # ref_depth_in_src(). Gated on want_freespace so the ofull default path calls CGC
    # with the flag off -> byte-for-byte the original 4-tuple, zero extra work.
    want_freespace = freespace_n is not None
    _reuse_refdepth = want_freespace and _CGC_HAS_REFDEPTH
    for nb in _nearest_ctx(n, NEIGH, refs, min_base_fuse):
        if _reuse_refdepth:
            mask, depth_reproj, x2d, y2d, *rest = check_geometric_consistency(
                d_ref, K_ref, ext_ref, depth[nb], K_of[nb].astype(np.float64),
                w2c_of[nb].astype(np.float64), dmax, dmin, GEO_PIX, GEO_DEP,
                return_ref_depth_src=True)
        else:
            mask, depth_reproj, x2d, y2d = check_geometric_consistency(
                d_ref, K_ref, ext_ref, depth[nb], K_of[nb].astype(np.float64),
                w2c_of[nb].astype(np.float64), dmax, dmin, GEO_PIX, GEO_DEP)
            rest = None
        nb_n = cv2.remap(_getnrm_ctx(nb), x2d, y2d, interpolation=cv2.INTER_LINEAR)
        mask = mask & (np.sum(n_ref * nb_n, axis=2) > NORMAL_COS)
        geo_sum += mask.astype(np.int32); depth_acc += depth_reproj * mask
        if reproj_err_max is not None:
            rerr_acc += (np.abs(depth_reproj - d_ref) / np.maximum(d_ref, 1e-6)) * mask
        if photo_color is not None:
            nb_rgb01 = cv2.remap(R.load_image(name2mi[nb]), x2d, y2d,
                                 interpolation=cv2.INTER_LINEAR)   # src RGB @ reproj
            col_diff = np.abs(nb_rgb01 - ref_rgb01).mean(axis=2)   # mean-channel L1, 0-1
            color_ok = mask & (col_diff < photo_color)
            color_agree_sum += color_ok.astype(np.int32)
        if freespace_n is not None:
            samp_src = cv2.remap(depth[nb], x2d, y2d, interpolation=cv2.INTER_LINEAR)
            # rest[0] == old ref_depth_in_src(d_ref, K_ref, ext_ref, w2c_of[nb]): identical
            # matmul chain (xyz_src[2]) reused from CGC when filter.py supports it; vanilla
            # filter.py (fresh clone) -> recompute (byte-identical fallback).
            d_ref_in_nb = rest[0] if rest else ref_depth_in_src(
                d_ref, K_ref, ext_ref, w2c_of[nb].astype(np.float64))
            seen_through = (samp_src > 0) & (d_ref > 0) & \
                (samp_src - d_ref_in_nb > freespace_tau * np.maximum(d_ref_in_nb, 1e-6))
            freespace_sum += seen_through.astype(np.int32)
    img = (ref_rgb01 * 255).astype(np.uint8)
    final = (geo_sum >= GEO_MASK) & (conf[n].astype(np.float32) > PHOTO) \
        & boundary_keep(d_ref, rel=BOUND_REL)
    if photo_color is not None:
        final = final & (color_agree_sum >= photo_color_n)
    if freespace_n is not None:
        final = final & (freespace_sum < freespace_n)
    if reproj_err_max is not None:
        rerr_mean = rerr_acc / np.maximum(geo_sum, 1)
        final = final & (rerr_mean < reproj_err_max)
    if erode_kernel is not None:
        final = cv2.erode(final.astype(np.uint8), erode_kernel).astype(bool)
    kept = float(final.mean())
    d_avg = depth_acc / (geo_sum + 1)
    H, W = d_ref.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu - K_ref[0, 2]) / K_ref[0, 0] * d_avg
    y = (vv - K_ref[1, 2]) / K_ref[1, 1] * d_avg
    cam = np.stack([x, y, d_avg], -1)[final]
    Rr, t = ext_ref[:3, :3], ext_ref[:3, 3]
    pts = ((Rr.T @ (cam.T - t[:, None])).T).astype(np.float32)
    cols = img[final]
    nrms = n_ref[final].astype(np.float32)
    # dm = masked metric depth (0 where not kept). This is byte-identical to what
    # pw_tsdf_trio.compute_final_mask recomputes from scratch — cache it so the
    # TSDF stage can skip the entire geometric-consistency pass. [2026-07-08]
    dm = np.where(final, d_avg, 0.0).astype(np.float32)
    return pts, cols, nrms, kept, dm


def _fuse_pool_init(ctx):
    """Pool worker initializer. Under the (default) fork context ctx is already
    inherited via copy-on-write and this simply re-affirms the global; under a
    spawn fallback the parent pickles ctx and hands it here so the worker has the
    full depth/conf/K/w2c cache. Either way we pin every BLAS/OpenCV thread pool
    to 1 so N worker processes don't oversubscribe the P cores (that both slows
    things down and is the classic macOS libomp fork hang)."""
    global _FUSE_CTX
    if ctx is not None:
        _FUSE_CTX = ctx
    try:
        cv2.setNumThreads(1)
    except Exception:
        pass


def main():
    global PHOTO, GEO_MASK, PROC_W, PROC_H, NORMAL_COS, BOUND_REL
    tag = sys.argv[1]
    ref_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    assert tag in MODELS, f"tag must be one of {list(MODELS)}"
    break_cfg = None
    # --- 清理旋钮(缺省=沿用现行 ofull 值,保 o 复现)---
    photo_color = None      # 光度颜色一致性阈值(0-1 RGB L1/3);None=关(现行行为)
    photo_color_n = 1       # 需要多少 src 视图颜色一致
    erode_px = 0            # final mask 腐蚀像素半径;0=关(现行行为)
    freespace_n = None      # free-space 看穿票阈值;None=关(现行行为)
    freespace_tau = 0.02    # free-space 相对深度容差
    reproj_err_max = None   # 每点跨支持视图的平均相对深度残差上限;None=关(现行行为)
    if tag in STRICT:
        PHOTO = STRICT[tag]["PHOTO"]
        GEO_MASK = STRICT[tag]["GEO_MASK"]
        # 可选清理键:缺省则保持模块默认(BOUND_REL=0.03, NORMAL_COS=0.5)
        BOUND_REL = STRICT[tag].get("BOUND_REL", BOUND_REL)
        NORMAL_COS = STRICT[tag].get("NORMAL_COS", NORMAL_COS)
        photo_color = STRICT[tag].get("PHOTO_COLOR", None)
        photo_color_n = STRICT[tag].get("PHOTO_COLOR_N", 1)
        erode_px = STRICT[tag].get("ERODE_PX", 0)
        # free-space violation (Merrell ICCV07 / OpenMVS AdjustConfidence 风格):
        # 删被 >= FREESPACE_N 个 src 视图"看穿"的悬空飞点(正交于边缘位置)。缺省关。
        freespace_n = STRICT[tag].get("FREESPACE_N", None)
        freespace_tau = STRICT[tag].get("FREESPACE_TAU", 0.02)   # 相对深度容差(略> GEO_DEP)
        reproj_err_max = STRICT[tag].get("REPROJ_ERR_MAX", None) # 平均相对深度残差门(< GEO_DEP=0.01)
        print(f"[{tag}] STRICT fusion sweep: src={STRICT[tag]['src']} "
              f"PHOTO={PHOTO} GEO_MASK={GEO_MASK} BOUND_REL={BOUND_REL} "
              f"NORMAL_COS={NORMAL_COS} PHOTO_COLOR={photo_color} "
              f"PHOTO_COLOR_N={photo_color_n} ERODE_PX={erode_px} "
              f"FREESPACE_N={freespace_n} FREESPACE_TAU={freespace_tau} "
              f"(reusing frozen p1cache; NO MPS re-inference)", flush=True)
    cache_src_tag = None
    if tag in CACHE_SRC:
        # blend-family gate sweep: reuse a BREAK run's frozen cache (raw depth+conf),
        # only PHOTO varies. Must set the SAME render resolution so pass2 backprojection
        # K matches the cached inference resolution.
        cache_src_tag, cw, ch = CACHE_SRC[tag]
        PROC_W, PROC_H = cw, ch
        R.PROC_W, R.PROC_H = cw, ch
        print(f"[{tag}] GATE-SWEEP: reuse cache of '{cache_src_tag}' @ {cw}x{ch}, "
              f"PHOTO={PHOTO} GEO_MASK={GEO_MASK} (NO MPS re-inference)", flush=True)
    if tag in BREAK:
        break_cfg = BREAK[tag]
        PHOTO = break_cfg["PHOTO"]
        GEO_MASK = break_cfg["GEO_MASK"]
        W, H = break_cfg["W"], break_cfg["H"]
        assert W % 32 == 0 and H % 32 == 0, f"res must be /32-aligned, got {W}x{H}"
        # 覆盖渲染分辨率:R.load_image 用 R.PROC_W/PROC_H 全局 resize 原生 jpeg;
        # 同步 patch 使图像 + 后续 K 缩放一致。
        PROC_W, PROC_H = W, H
        R.PROC_W, R.PROC_H = W, H
        # checkpoint 域(dtu/blend)通过 env 传给 C.build_model
        os.environ["AETHER_CKPT"] = break_cfg["CKPT"]
        print(f"[{tag}] BREAK: src={break_cfg['src']} res={W}x{H} "
              f"ckpt={break_cfg['CKPT']} method={METHOD} PHOTO={PHOTO} "
              f"GEO_MASK={GEO_MASK} (FRESH MPS inference, own p1cache)", flush=True)
    name2mi = name2mi_map()
    pool, refs = build_refs()
    if ref_limit:
        refs = refs[:ref_limit]
    ark = g.arkit_centers_and_R()

    # BREAK/STRICT/CACHE_SRC tags reuse a base model's dump (their own npz is never dumped).
    model_tag = break_cfg["src"] if break_cfg else (STRICT[tag]["src"] if tag in STRICT else tag)
    mnames, K_of, w2c_of, center_of, obs, pts_arr = load_model(model_tag)
    if PROC_W != 896 or PROC_H != 512:
        # dump K is baked @896x512; rescale to the render resolution (fx,cx by W/896,
        # fy,cy by H/512). w2c is resolution-independent. Applies to BREAK res runs AND
        # gate-sweep tags reusing a hi-res cache (res15blend/res2blend @ 1344/1792).
        sx, sy = PROC_W / 896.0, PROC_H / 512.0
        Ks = np.diag([sx, sy, 1.0]).astype(np.float32)
        K_of = {n: (Ks @ K) for n, K in K_of.items()}
        print(f"[{tag}] K rescaled from 896x512 dump by (sx={sx:.4f}, sy={sy:.4f}) "
              f"-> {PROC_W}x{PROC_H}", flush=True)
    missing = [n for n in pool if n not in K_of]
    if missing:  # model did not register some pool frames -> drop them (DECLARE in report)
        print(f"[{tag}] WARNING: {len(missing)} pool frame(s) not in model, dropped: "
              f"{missing} (refs affected: {[n for n in missing if n in refs]})", flush=True)
        pool = [n for n in pool if n in K_of]
        refs = [n for n in refs if n in K_of]
    print(f"[{tag}] model {MODELS[tag]}: {len(mnames)} imgs {len(pts_arr)} sparse pts; "
          f"pool={len(pool)} refs={len(refs)}", flush=True)
    s_al, R_al, t_al = robust_align(center_of, ark)
    min_base_src = MIN_BASE_SRC_M / s_al
    min_base_fuse = MIN_BASE_FUSE_M / s_al
    obs_set = {n: set(v.tolist()) for n, v in obs.items() if n in set(pool)}
    for n in pool:
        obs_set.setdefault(n, set())

    def drange(n):
        ids = obs.get(n)
        X = pts_arr[ids] if ids is not None and len(ids) else np.empty((0, 3))
        if len(X) < 8:
            return 0.3 / s_al, 4.0 / s_al
        W = w2c_of[n].astype(np.float64)
        z = (W[:3, :3] @ X.T + W[:3, 3:4]).T[:, 2]; z = z[z > 0.05 / s_al]
        if len(z) < 8:
            return 0.3 / s_al, 4.0 / s_al
        lo, hi = np.percentile(z, 2), np.percentile(z, 99.5)
        return float(max(0.1 / s_al, lo * 0.70)), float(hi * 1.5)

    def nearest(n, k, cand, min_base):
        c0 = center_of[n]
        d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in cand if m != n)
        return [m for dist, m in d if dist >= min_base][:k]

    # ---- pass 1: casdiffmvs depth+conf for each ref (poses/K/drange from this model) ----
    # BREAK tags MUST re-run MPS inference at the new res/ckpt -> own cache path so a
    # stale/frozen cache is never loaded and the champion 'lapa' cache is never poisoned.
    # Gate-sweep tags read the SOURCE BREAK cache directly (frozen inference, no re-run).
    p1cache = OUT / (f"p1cache_trio_{cache_src_tag}.npz" if cache_src_tag
                     else f"p1cache_trio_{tag}.npz")
    depth, conf, drng = {}, {}, {}
    t_inf = 0.0
    mps_peak_mb = 0.0; dt_list = []
    if p1cache.exists():
        z = np.load(p1cache, allow_pickle=True)
        fr = z["frames"].tolist(); zd, zc, zr = z["depth"], z["conf"], z["drange"]
        for i, n in enumerate(fr):
            depth[n] = zd[i].astype(np.float32); conf[n] = zc[i]; drng[n] = tuple(zr[i])
        refs = [n for n in refs if n in depth]
        print(f"loaded {p1cache.name} ({len(refs)} refs)", flush=True)
    else:
        dev = C.pick_device("mps")
        model, _ = C.build_model(METHOD, dev)
        _mps = dev.type == "mps"
        def _mps_mb():
            try:
                return torch.mps.driver_allocated_memory() / 1e6
            except Exception:
                return 0.0
        if _mps and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
        # [AETHER 2026-07-08] FeatureNet cross-ref cache: byte-identical, cuts ~78% of
        # FeatureNet calls — BUT measured only ~2% host-MPS wall (FeatureNet is ~2.6% of
        # inference, not the 14% estimate; cost-volume+diffusion is the 97% bottleneck)
        # AND costs ~2.6GB MPS. Default OFF; opt-in via AETHER_FEATCACHE=1 (e.g. a future
        # device CoreML/ANE build where the FeatureNet fraction differs). Cap: AETHER_FEATCACHE_N.
        _feat_cache = {} if os.environ.get("AETHER_FEATCACHE") else None
        _fc_cap = int(os.environ.get("AETHER_FEATCACHE_N", "0"))
        t0 = time.time()
        for i, n in enumerate(refs):
            src = covis_select(n, pool, center_of, obs_set, obs, pts_arr, NVIEW - 1) \
                or nearest(n, NVIEW - 1, pool, min_base_src)
            view = [n] + src
            imgs = [R.load_image(name2mi[m]).transpose(2, 0, 1) for m in view]
            Ks = np.stack([K_of[m] for m in view])
            w2cs = np.stack([w2c_of[m] for m in view])
            dmin, dmax = drange(n); drng[n] = (dmin, dmax)
            proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(dmin, dmax)
            d, c, dt = C.run_inference(model, imgs, proj, dv, dev,
                                       view_names=view, feat_cache=_feat_cache)
            if _feat_cache is not None and _fc_cap and len(_feat_cache) > _fc_cap:
                for _k in list(_feat_cache.keys())[:len(_feat_cache) - _fc_cap]:
                    if _k not in view:                       # never evict current view
                        del _feat_cache[_k]
            t_inf += dt; dt_list.append(dt)
            if _mps:
                mps_peak_mb = max(mps_peak_mb, _mps_mb())
            depth[n] = d.astype(np.float32); conf[n] = c.astype(np.float16)
            if i % 20 == 0 or ref_limit:
                dd = d[d > 0]
                print(f"  [{tag}] {i}/{len(refs)} {n} src={src} drange=[{dmin:.2f},{dmax:.2f}] "
                      f"depth[med={np.median(dd):.2f} p5={np.percentile(dd,5):.2f} "
                      f"p95={np.percentile(dd,95):.2f}] conf%>{PHOTO}="
                      f"{100*(c>PHOTO).mean():.0f} {dt:.2f}s "
                      f"mps_peak={mps_peak_mb:.0f}MB", flush=True)
        med_dt = float(np.median(dt_list)) if dt_list else 0.0
        print(f"[{tag}] pass1 done wall={time.time()-t0:.1f}s infer_sum={t_inf:.1f}s "
              f"MPS_PEAK={mps_peak_mb:.0f}MB INFER_MED={med_dt:.3f}s/frame "
              f"INFER_MEAN={t_inf/max(1,len(dt_list)):.3f}s/frame N={len(dt_list)} "
              f"res={PROC_W}x{PROC_H} ckpt={os.environ.get('AETHER_CKPT','dtu')}", flush=True)
        if not ref_limit:  # never poison the full-run cache with a smoke subset
            np.savez_compressed(p1cache,
                                depth=np.stack([depth[n].astype(np.float16) for n in refs]),
                                conf=np.stack([conf[n] for n in refs]),
                                drange=np.array([drng[n] for n in refs], np.float32),
                                frames=np.array(refs))

    # ---- pass 2: geomcons fusion g3 p0.3 among the ref set (identical recipe) ----
    # 光度颜色一致性(可选):Gipuma/Merrell 风格。ref 像素反投影到 src(x2d,y2d)取 src RGB,
    # 与 ref RGB 比较 |Δ|<τ(0-1 空间 L1/3 平均通道差);仅在几何 mask 命中处计数,累加得
    # color_agree_sum,要求 >= photo_color_n。占用已算好的 remap 坐标,近乎零成本。
    #
    # 每个 ref 完全独立(只读 depth/conf/K/w2c/drng + 该 ref 自身深度图),故外层
    # `for n in refs` 天然可并行。AETHER_FUSE_WORKERS>1 走 multiprocessing.Pool;
    # 默认 1 = 串行,与历史逐位一致(仅 concat 顺序可变,点集/统计不变)。
    t0 = time.time()
    erode_kernel = None
    if erode_px and erode_px > 0:
        k = 2 * int(erode_px) + 1
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    # [2026-07-08] normals cache: world_normals is a pure fn of (depth,K,w2c) — all
    # frozen — yet a frame's normals were recomputed once as its own ref + once per
    # ref that picks it as a NEIGH neighbor (~9x). Precompute once per ref frame here,
    # COW-shared read-only to the fork workers. Byte-identical; pure numpy (cross-platform).
    _norm_cache = None if os.environ.get("AETHER_NO_NORMCACHE") else {
        m: world_normals(depth[m], K_of[m].astype(np.float64),
                         w2c_of[m].astype(np.float64)) for m in refs}
    _FUSE_CTX.clear()
    _FUSE_CTX.update(dict(
        depth=depth, conf=conf, drng=drng, K_of=K_of, w2c_of=w2c_of,
        center_of=center_of, refs=refs, name2mi=name2mi, normals=_norm_cache,
        NEIGH=NEIGH, min_base_fuse=min_base_fuse, GEO_PIX=GEO_PIX, GEO_DEP=GEO_DEP,
        NORMAL_COS=NORMAL_COS, GEO_MASK=GEO_MASK, PHOTO=PHOTO, BOUND_REL=BOUND_REL,
        photo_color=photo_color, photo_color_n=photo_color_n, erode_kernel=erode_kernel,
        freespace_n=freespace_n, freespace_tau=freespace_tau, reproj_err_max=reproj_err_max,
    ))
    # [2026-07-07] 默认翻并行:pass2 融合每 ref 完全独立,imap 保序 -> 逐位一致
    # (已认证 bit-identical + 3.1x);默认吃满 6-8 核甜点,AETHER_FUSE_WORKERS=1 可
    # 强制回串行(调试/对拍)。内层还会再 cap 到 min(., cpu-2, refs)。
    _fuse_default = str(min(8, max(1, (os.cpu_count() or 4) - 2)))
    n_workers = int(os.environ.get("AETHER_FUSE_WORKERS", _fuse_default))
    if n_workers <= 1:
        results = [_fuse_one_ref(n) for n in refs]           # 串行(env=1 显式回退)
    else:
        import multiprocessing as _mp
        # cpu-2 与 ref 数为安全上限。实测融合是内存带宽瓶颈:~6 workers 已打满内存总线
        # (6w 68.7s ≈ 10w 70.2s),再加核几乎不提速,故 6-8 是效率甜点(串行 214s→~69s ≈3.1x)。
        n_workers = min(n_workers, max(1, (os.cpu_count() or 2) - 2), len(refs))
        # fork 让子进程零拷贝继承已加载的 depth/conf/... 全量 cache(COW);spawn 兜底
        # 时由 initializer 收 pickle 后的 ctx。子进程内 BLAS/cv2 线程都锁 1,避免
        # N 进程 × M 线程超订(既慢又是 macOS libomp fork 挂起的经典诱因)。
        try:
            _ctx = _mp.get_context("fork"); _init_arg = None      # COW 继承,无需传
        except ValueError:                                        # 平台无 fork -> spawn
            _ctx = _mp.get_context("spawn"); _init_arg = dict(_FUSE_CTX)
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        cv2.setNumThreads(1)
        print(f"[{tag}] fuse: parallel {n_workers} workers "
              f"({_ctx.get_start_method()}) over {len(refs)} refs", flush=True)
        with _ctx.Pool(processes=n_workers, initializer=_fuse_pool_init,
                       initargs=(_init_arg,)) as _pool:
            # chunksize>1 摊薄任务派发开销;结果按 refs 顺序回收(imap 保序,与串行
            # 完全同序 -> 逐位一致,不只是集合一致)。
            results = list(_pool.imap(_fuse_one_ref, refs,
                                      chunksize=max(1, len(refs) // (n_workers * 4))))
        cv2.setNumThreads(0)   # 恢复主进程默认线程数(供后续 o3d/cv2 用)
    pts = [r[0] for r in results]; cols = [r[1] for r in results]
    nrms = [r[2] for r in results]; kept = [r[3] for r in results]
    # dm-cache: pw_tsdf_trio.compute_final_mask recomputes this exact masked depth
    # from scratch — write it (byte-identical) so the TSDF stage can skip the whole
    # geometric-consistency pass. Keyed by tag + a gate-signature guard. [2026-07-08]
    _dm_sig = (f"g{GEO_MASK}_p{PHOTO}_bnd{BOUND_REL}_nrm{NORMAL_COS}_pc{photo_color}_"
               f"pcn{photo_color_n}_fs{freespace_n}_fst{freespace_tau}_"
               f"re{reproj_err_max}_er{erode_px}")
    _dmc = OUT / f"dmcache_trio_{tag}.npz"
    np.savez(_dmc, frames=np.array([str(n) for n in refs]),
             dm=np.stack([r[4] for r in results]).astype(np.float32), sig=_dm_sig)
    print(f"[{tag}] wrote dm-cache {_dmc.name} ({len(refs)} refs, sig={_dm_sig})", flush=True)
    P = np.concatenate(pts); Cc = np.concatenate(cols); Nn = np.concatenate(nrms)
    print(f"[{tag}] fused g{GEO_MASK} p{PHOTO} bnd{BOUND_REL} nrm{NORMAL_COS} "
          f"pc{photo_color}(N>={photo_color_n}) er{erode_px}: {len(P):,} raw pts "
          f"kept/frame={np.mean(kept)*100:.1f}% fuse={time.time()-t0:.1f}s "
          f"workers={n_workers}", flush=True)

    # ---- align into ARKit metric frame, THEN metric cleanup (identical across models) ----
    Pa = (s_al * (R_al @ P.astype(np.float64).T).T + t_al)
    Na = (R_al @ Nn.astype(np.float64).T).T   # 法向只旋转(不平移不缩放)进 ARKit 系
    Na /= np.maximum(np.linalg.norm(Na, axis=1, keepdims=True), 1e-9)
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(Pa)
    pc.colors = o3d.utility.Vector3dVector(Cc.astype(np.float64) / 255.0)
    pc.normals = o3d.utility.Vector3dVector(Na)   # 法向进输出(voxel/SOR 会一并保留平均)
    pc = pc.voxel_down_sample(0.005)
    pc, _ = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    print(f"[{tag}] after voxel5mm+outlier: {len(pc.points):,}", flush=True)

    fp = OUT / f"fused_trio_{tag}.ply"
    o3d.io.write_point_cloud(str(fp), pc)
    print(f"wrote {fp}", flush=True)
    if not ref_limit:
        OUTDIR.mkdir(exist_ok=True)
        xyz = np.asarray(pc.points, np.float64).astype(np.float32)
        rgb = np.clip(np.asarray(pc.colors) * 255 + 0.5, 0, 255).astype(np.uint8)
        nrm = np.asarray(pc.normals, np.float32) if pc.has_normals() else None
        write_ply(OUTDIR / VIEWER_PLY[tag], xyz, rgb, normals=nrm)


if __name__ == "__main__":
    main()
