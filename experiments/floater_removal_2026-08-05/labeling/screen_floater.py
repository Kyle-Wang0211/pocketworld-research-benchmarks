#!/usr/bin/env python3
"""浮点桶(ncc_median < 0.15,共 50 点)人工手判用强化条带图。

每点一行,近景(3cm patch,现口径)与远景(12cm patch = 4 倍视野)并排:
  - 周期结构错相位:近景 NCC 低,但远景视野放大后整体布局仍对应 => 远景 NCC 明显抬升
  - 真浮点:远景是完全不同的东西 => 远景 NCC 依然低
输出 screen_floater_{00,01,02}.png + screen_floater_far.npz
"""
import os
import numpy as np
from PIL import Image, ImageDraw
import holdout_ncc as H

HERE = H.HERE
CUT = 0.15
FAR_M = 0.12                 # 远景物理边长 12cm = 近景 4 倍
FAR_PX_MIN, FAR_PX_MAX = H.PX_MIN * 4, H.PX_MAX * 4   # [96, 384]
S_FAR_EXT = 128              # 远景提取 128x128 -> 2x2 均值 -> 64x64 做 NCC
S_FAR_NCC = 64
TN, TF, GAP, LW, SEP, TXT = 80, 96, 6, 132, 26, 26
PER_SHEET = 17


def main():
    cams = H.read_cams(f"{H.MODEL}/cameras.bin")
    imgs = H.read_imgs(f"{H.MODEL}/images.bin")
    xyz, tracks = H.read_pts(f"{H.MODEL}/points3D.bin")
    idx = np.load(f"{HERE}/sample_idx.npy")
    d = np.load(f"{HERE}/holdout_ncc.npz", allow_pickle=True)
    med, mx = d["ncc_median"], d["ncc_max"]
    ncc_near_all, ntr, dep = d["ncc_all"], d["n_track"], d["ref_depth"]

    sel = np.where(np.isfinite(med) & (med < CUT))[0]
    sel = sel[np.argsort(med[sel])]
    print(f"浮点桶: {len(sel)} 点 (ncc_median < {CUT}), "
          f"范围 {med[sel[0]]:+.3f} .. {med[sel[-1]]:+.3f}")

    path_of = {}
    for iid, im in imgs.items():
        k = int(im["name"].split("_")[1].split(".")[0])
        path_of[iid] = f"{H.PHOTOS}/{H.ORDER[k]}"
    all_ids = np.array(sorted(imgs))

    # ---- 几何:复用主脚本同一套选视图逻辑 ----
    reqs = {}
    info = {}
    for slot in sel:
        pi = idx[slot]
        P = xyz[pi]
        T = list(tracks[pi])
        Ct = np.stack([imgs[i]["C"] for i in T])
        D = Ct - P
        Dn = D / np.linalg.norm(D, axis=1, keepdims=True)
        cm = Dn @ Dn.T
        np.fill_diagonal(cm, 1.0)
        ref = T[int(np.argmax(np.degrees(np.arccos(np.clip(cm, -1, 1))).max(axis=1)))]
        ur, vr, zr = H.project(imgs[ref], cams[imgs[ref]["cid"]], P)
        fxr = cams[imgs[ref]["cid"]][0][0]
        near_r = float(np.clip(H.PATCH_M * fxr / zr, H.PX_MIN, H.PX_MAX))
        far_r = float(np.clip(FAR_M * fxr / zr, FAR_PX_MIN, FAR_PX_MAX))
        reqs.setdefault(int(ref), []).append((slot, "refN", 0, ur, vr, near_r))
        reqs.setdefault(int(ref), []).append((slot, "refF", 0, ur, vr, far_r))
        dref = imgs[ref]["C"] - P
        dref = dref / np.linalg.norm(dref)
        Tset = set(int(t) for t in T)
        cand = []
        for iid in all_ids:
            if int(iid) in Tset:
                continue
            im = imgs[iid]
            dist = float(np.linalg.norm(im["C"] - P))
            if not (H.DIST_MIN <= dist <= H.DIST_MAX):
                continue
            u, v, z = H.project(im, cams[im["cid"]], P)
            if u is None:
                continue
            W, Hh = cams[im["cid"]][1], cams[im["cid"]][2]
            if not (H.MARGIN_PX <= u <= W - H.MARGIN_PX and H.MARGIN_PX <= v <= Hh - H.MARGIN_PX):
                continue
            dh = im["C"] - P
            dh = dh / np.linalg.norm(dh)
            ang = np.degrees(np.arccos(np.clip(float(dref @ dh), -1, 1)))
            if H.ANG_MIN <= ang <= H.ANG_MAX:
                cand.append((ang, int(iid), u, v, z))
        cand.sort()
        cand = cand[:H.N_HOLDOUT]
        info[slot] = dict(pi=int(pi), ref=int(ref), n_track=len(T), depth=float(zr),
                          ang=[c[0] for c in cand], hold=[c[1] for c in cand])
        for k, (ang, iid, u, v, z) in enumerate(cand):
            fx = cams[imgs[iid]["cid"]][0][0]
            reqs.setdefault(iid, []).append(
                (slot, "hN", k, u, v, float(np.clip(H.PATCH_M * fx / z, H.PX_MIN, H.PX_MAX))))
            reqs.setdefault(iid, []).append(
                (slot, "hF", k, u, v, float(np.clip(FAR_M * fx / z, FAR_PX_MIN, FAR_PX_MAX))))

    # ---- 提取 ----
    NS = len(idx)
    RN = np.full((NS, H.S_EXT, H.S_EXT), np.nan, np.float32)
    RF = np.full((NS, S_FAR_EXT, S_FAR_EXT), np.nan, np.float32)
    HN = np.full((NS, H.N_HOLDOUT, H.S_EXT, H.S_EXT), np.nan, np.float32)
    HF = np.full((NS, H.N_HOLDOUT, S_FAR_EXT, S_FAR_EXT), np.nan, np.float32)
    for n, iid in enumerate(sorted(reqs)):
        gray = np.asarray(Image.open(path_of[iid]).convert("L"), dtype=np.float32)
        for (slot, kind, k, u, v, sp) in reqs[iid]:
            S = H.S_EXT if kind in ("refN", "hN") else S_FAR_EXT
            p = H.bilinear_patch(gray, u, v, sp, S)
            if p is None:
                continue
            if kind == "refN":
                RN[slot] = p
            elif kind == "refF":
                RF[slot] = p
            elif kind == "hN":
                HN[slot, k] = p
            else:
                HF[slot, k] = p
        if n % 30 == 0:
            print(f"  img {n}/{len(reqs)}", flush=True)

    def norm(p, S):
        q = p.reshape(S, p.shape[0] // S, S, p.shape[0] // S).mean(axis=(1, 3))
        q = q - q.mean()
        s = q.std()
        return None if s < 1e-3 else q / s

    far_all = np.full((NS, H.N_HOLDOUT), np.nan)
    far_med = np.full(NS, np.nan)
    far_max = np.full(NS, np.nan)
    n_far_missing = 0
    for slot in sel:
        if not np.isfinite(RF[slot]).all():
            n_far_missing += 1
            continue
        a = norm(RF[slot], S_FAR_NCC)
        if a is None:
            continue
        vals = []
        for k in range(H.N_HOLDOUT):
            b = HF[slot, k]
            if not np.isfinite(b).all():
                continue
            b = norm(b, S_FAR_NCC)
            if b is None:
                continue
            c = float((a * b).mean())
            far_all[slot, k] = c
            vals.append(c)
        if len(vals) >= 2:
            far_med[slot] = float(np.median(vals))
            far_max[slot] = max(vals)

    np.savez(f"{HERE}/screen_floater_far.npz",
             slot=sel, point_idx=idx[sel], ncc_median_near=med[sel], ncc_max_near=mx[sel],
             ncc_median_far=far_med[sel], ncc_max_far=far_max[sel],
             ncc_all_far=far_all[sel], n_track=ntr[sel], ref_depth=dep[sel])

    # ---- 渲染 ----
    def tile(p, size):
        lo, hi = np.percentile(p, [2, 98])
        q = np.clip((p - lo) / max(hi - lo, 1e-6), 0, 1) * 255
        return Image.fromarray(q.astype(np.uint8)).resize((size, size), Image.NEAREST).convert("RGB")

    NB = H.N_HOLDOUT + 1
    Wpx = LW + NB * (TN + GAP) + SEP + NB * (TF + GAP) + GAP
    for sh in range((len(sel) + PER_SHEET - 1) // PER_SHEET):
        rows = sel[sh * PER_SHEET:(sh + 1) * PER_SHEET]
        Hpx = len(rows) * (TF + TXT) + 34
        canvas = Image.new("RGB", (Wpx, Hpx), (255, 255, 255))
        dr = ImageDraw.Draw(canvas)
        dr.text((6, 5), f"FLOATER SCREEN sheet {sh}  |  ncc_median < {CUT}, ascending  "
                        f"|  {len(sel)} pts total", fill=(0, 0, 0))
        x0n = LW
        x0f = LW + NB * (TN + GAP) + SEP
        dr.text((x0n, 19), "NEAR 3cm  (ref | holdout x4)", fill=(0, 0, 160))
        dr.text((x0f, 19), "FAR 12cm = 4x FOV  (ref | holdout x4)", fill=(0, 120, 0))
        dr.line([(x0f - SEP // 2, 32), (x0f - SEP // 2, Hpx)], fill=(180, 180, 180))
        for ri, slot in enumerate(rows):
            oy = 34 + ri * (TF + TXT)
            it = info[slot]
            dr.text((4, oy + 2), f"#{slot} pt{it['pi']}", fill=(0, 0, 0))
            dr.text((4, oy + 16), f"nearMed {med[slot]:+.2f}", fill=(0, 0, 160))
            dr.text((4, oy + 30), f"nearMax {mx[slot]:+.2f}", fill=(0, 0, 160))
            fm = far_med[slot]
            dr.text((4, oy + 46), "farMed  " + ("--" if not np.isfinite(fm) else f"{fm:+.2f}"),
                    fill=(0, 120, 0))
            fx_ = far_max[slot]
            dr.text((4, oy + 60), "farMax  " + ("--" if not np.isfinite(fx_) else f"{fx_:+.2f}"),
                    fill=(0, 120, 0))
            dr.text((4, oy + 76), f"trk{it['n_track']}  d{it['depth']:.2f}m", fill=(110, 110, 110))
            for ci in range(NB):
                # 近景
                pn = RN[slot] if ci == 0 else HN[slot, ci - 1]
                ox = x0n + ci * (TN + GAP)
                oyn = oy + (TF - TN) // 2
                if np.isfinite(pn).all():
                    canvas.paste(tile(pn, TN), (ox, oyn))
                else:
                    dr.rectangle([ox, oyn, ox + TN - 1, oyn + TN - 1], outline=(200, 200, 200))
                if ci == 0:
                    dr.rectangle([ox, oyn, ox + TN - 1, oyn + TN - 1], outline=(220, 30, 30))
                    dr.text((ox + 2, oy + TF + 4), "REF", fill=(180, 0, 0))
                else:
                    c = ncc_near_all[slot, ci - 1]
                    dr.text((ox + 2, oy + TF + 4),
                            ("--" if not np.isfinite(c) else f"{c:+.2f}") +
                            f" {it['ang'][ci-1]:.0f}d" if ci - 1 < len(it["ang"]) else "--",
                            fill=(0, 0, 160))
                # 远景
                pf = RF[slot] if ci == 0 else HF[slot, ci - 1]
                ox = x0f + ci * (TF + GAP)
                if np.isfinite(pf).all():
                    canvas.paste(tile(pf, TF), (ox, oy))
                else:
                    dr.rectangle([ox, oy, ox + TF - 1, oy + TF - 1], outline=(200, 200, 200))
                # 远景中心画出近景对应的范围(1/4 边长)
                q = TF // 8
                dr.rectangle([ox + TF // 2 - q, oy + TF // 2 - q,
                              ox + TF // 2 + q, oy + TF // 2 + q], outline=(255, 200, 0))
                if ci == 0:
                    dr.rectangle([ox, oy, ox + TF - 1, oy + TF - 1], outline=(220, 30, 30))
                    dr.text((ox + 2, oy + TF + 4), "REF", fill=(180, 0, 0))
                else:
                    c = far_all[slot, ci - 1]
                    dr.text((ox + 2, oy + TF + 4),
                            "--" if not np.isfinite(c) else f"{c:+.2f}", fill=(0, 120, 0))
        canvas.save(f"{HERE}/screen_floater_{sh:02d}.png")
        print("wrote", f"screen_floater_{sh:02d}.png", f"({len(rows)} rows)")

    # ---- 量化报告 ----
    n_, f_ = med[sel], far_med[sel]
    ok = np.isfinite(f_)
    print(f"\n远景 patch 越界丢失: {n_far_missing} / {len(sel)}; 有效远景 NCC: {ok.sum()}")
    print(f"\n=== 50 点浮点桶:近景 vs 远景 NCC ===")
    for nm, v in [("near median", n_), ("far  median", f_[ok]),
                  ("near max", mx[sel]), ("far  max", far_max[sel][np.isfinite(far_max[sel])])]:
        p = np.percentile(v, [5, 25, 50, 75, 95])
        print(f"  {nm:12s} n={len(v):3d} p5={p[0]:+.3f} p25={p[1]:+.3f} p50={p[2]:+.3f} "
              f"p75={p[3]:+.3f} p95={p[4]:+.3f}")
    lift = f_[ok] - n_[ok]
    print(f"\n  远景抬升(far-near): p25={np.percentile(lift,25):+.3f} "
          f"p50={np.percentile(lift,50):+.3f} p75={np.percentile(lift,75):+.3f}")
    for t in [0.2, 0.3, 0.4, 0.5]:
        print(f"  far_med >= {t:.1f}: {int((f_[ok]>=t).sum()):2d} / {int(ok.sum())} "
              f"({100*(f_[ok]>=t).mean():.0f}%)  <- 疑似周期结构错相位/真实结构")
    print("\n  逐点表(按 near_med 升序):")
    print("   slot  pt      near_med near_max  far_med far_max  trk  depth  lift")
    for slot in sel:
        f1 = far_med[slot]; f2 = far_max[slot]
        print(f"  #{slot:4d} {info[slot]['pi']:7d}  {med[slot]:+.3f}  {mx[slot]:+.3f}  "
              f"{'  --  ' if not np.isfinite(f1) else f'{f1:+.3f}'} "
              f"{'  --  ' if not np.isfinite(f2) else f'{f2:+.3f}'}  "
              f"{info[slot]['n_track']:3d} {info[slot]['depth']:5.2f}m  "
              f"{'  -- ' if not np.isfinite(f1) else f'{f1-med[slot]:+.3f}'}")


if __name__ == "__main__":
    main()
