"""Dump the three COLMAP models into torch-free npz files for pw_diffmvs_sfm_trio.py.

pycolmap and torch cannot share a process on this Mac (duplicate libomp ->
pthread_mutex_init SIGSEGV), so this runs standalone: pycolmap + numpy ONLY.
Writes per model: diffmvs_out/trio_model_<tag>.npz with
  names(N), K(N,3,3)@896x512, w2c(N,4,4), centers(N,3),
  obs_idx(concat int64 indices into pts), obs_off(N+1), pts(P,3)
plus diffmvs_out/trio_refs.json (fixed shared pool + every-4th ref subset).
"""
import os, sys, json
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
from pathlib import Path
import numpy as np
import pycolmap

SCRATCH = Path("/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/"
               "7fc69efe-e09c-4359-8afb-04378874d3a1/scratchpad")
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
    "baseredense2": SCRATCH / "jfix/recon_gc",              # 元判决:金同一稀疏 recon_gc 今日第2次独立稠密
    "baseredense3": SCRATCH / "jfix/recon_gc",              # 元判决:金同一稀疏 recon_gc 今日第3次独立稠密
}
ONLY = set(sys.argv[1:])   # dump only these tags if given; refs json then untouched
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tools/python/diffmvs_out"
MAN = (ROOT / "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/"
       "external_pose_k_vs_res_2026_06_10/k414_spatial_order_manifest.json")
FULL_W, FULL_H, PROC_W, PROC_H = 4224, 2376, 896, 512
REF_STRIDE = 4

man = json.load(open(MAN))["frames"]
name2mi = {Path(f["jpegPath"]).name: i for i, f in enumerate(man)}

regsets = {}
for tag, mdir in MODELS.items():
    if ONLY and tag not in ONLY:
        continue
    rec = pycolmap.Reconstruction(str(mdir))
    names, Ks, w2cs, centers = [], [], [], []
    sx, sy = PROC_W / FULL_W, PROC_H / FULL_H
    iid2row = {}
    for im in rec.images.values():
        cam = rec.cameras[im.camera_id]
        f, cx, cy = float(cam.params[0]), float(cam.params[1]), float(cam.params[2])
        K = np.array([[f * sx, 0, cx * sx], [0, f * sy, cy * sy], [0, 0, 1]], np.float32)
        cfw = im.cam_from_world() if callable(im.cam_from_world) else im.cam_from_world
        rot = cfw.rotation() if callable(cfw.rotation) else cfw.rotation
        Rw2c = np.asarray(rot.matrix(), np.float64)
        t = np.asarray(cfw.translation() if callable(cfw.translation) else cfw.translation,
                       np.float64)
        W = np.eye(4, dtype=np.float32); W[:3, :3] = Rw2c; W[:3, 3] = t
        iid2row[im.image_id] = len(names)
        names.append(im.name); Ks.append(K); w2cs.append(W)
        centers.append(-Rw2c.T @ t)
    pts, obs_lists = [], [[] for _ in names]
    for pt_i, (pid, pt) in enumerate(rec.points3D.items()):
        pts.append(np.asarray(pt.xyz))
        for el in pt.track.elements:
            row = iid2row.get(el.image_id)
            if row is not None:
                obs_lists[row].append(pt_i)
    obs_off = np.zeros(len(names) + 1, np.int64)
    for i, l in enumerate(obs_lists):
        obs_off[i + 1] = obs_off[i] + len(l)
    obs_idx = np.concatenate([np.array(sorted(set(l)), np.int64) if l else
                              np.empty(0, np.int64) for l in obs_lists])
    # sorted(set()) may shrink counts vs raw lists -> rebuild offsets from dedup
    obs_off = np.zeros(len(names) + 1, np.int64)
    dedup = [np.array(sorted(set(l)), np.int64) for l in obs_lists]
    for i, l in enumerate(dedup):
        obs_off[i + 1] = obs_off[i] + len(l)
    obs_idx = np.concatenate(dedup) if dedup else np.empty(0, np.int64)
    np.savez_compressed(OUT / f"trio_model_{tag}.npz",
                        names=np.array(names), K=np.stack(Ks), w2c=np.stack(w2cs),
                        centers=np.stack(centers), obs_idx=obs_idx, obs_off=obs_off,
                        pts=np.stack(pts))
    regsets[tag] = set(names)
    print(f"[{tag}] dumped {len(names)} imgs {len(pts)} pts -> trio_model_{tag}.npz",
          flush=True)

if ONLY:
    # incremental dump: NEVER touch the fixed ref subset; instead verify the new
    # model(s) cover the existing pool (runner would KeyError on missing frames)
    d = json.loads((OUT / "trio_refs.json").read_text())
    for tag, names in regsets.items():
        missing = [n for n in d["pool"] if n not in names]
        print(f"[{tag}] pool coverage: {len(d['pool'])-len(missing)}/{len(d['pool'])}"
              + (f" MISSING={missing}" if missing else " OK"), flush=True)
else:
    inter = set.intersection(*regsets.values()) & set(name2mi)
    pool = sorted(inter, key=lambda n: name2mi[n])
    refs = pool[::REF_STRIDE]
    (OUT / "trio_refs.json").write_text(json.dumps({"pool": pool, "refs": refs}))
    print(f"trio_refs.json: pool={len(pool)} refs={len(refs)}", flush=True)
