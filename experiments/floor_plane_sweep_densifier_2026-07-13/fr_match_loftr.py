"""Step 2: Kornia LoFTR indoor (VALIDATED matcher, NOT the broken HF eff-loftr) on MPS.
Match each floor pair at reduced 640x360 (peak << 4.7GB@1024), scale keypoints back
to the 1024x576 WORK frame that K belongs to. Memory-hygienic: per-pair guard +
empty_cache, no accumulation. Saves raw matches; geometry filtering is a later CPU step.
ENV: FR_LIMIT=N to probe first N pairs."""
import os, sys, json, time
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import numpy as np, torch, cv2
import kornia.feature as KF
from fr_common import (FR, MATCH_W, MATCH_H, WORK_W, WORK_H, avail_gb, imgpath)

CONF = 0.2
GUARD_GB = 1.5            # require >= this avail before EACH pair, else pause+report
SX = WORK_W / MATCH_W    # 1.6 : match-coord -> work-coord (aspect preserved)
SY = WORK_H / MATCH_H

def load_gray_np(fid):
    g = cv2.imread(imgpath(fid), cv2.IMREAD_GRAYSCALE)
    if g.shape[1] != MATCH_W or g.shape[0] != MATCH_H:
        g = cv2.resize(g, (MATCH_W, MATCH_H), interpolation=cv2.INTER_AREA)
    return g

PAIRS_JSON = os.environ.get("FR_PAIRS", FR + "/fr_pairs.json")
NPZ_OUT    = os.environ.get("FR_NPZ",   FR + "/fr_matches.npz")
META_OUT   = os.environ.get("FR_META",  FR + "/fr_matches_meta.json")

def main():
    pairs = json.load(open(PAIRS_JSON))["pairs"]
    limit = int(os.environ.get("FR_LIMIT", "0"))
    if limit: pairs = pairs[:limit]
    ag0 = avail_gb(); print(f"[match] avail BEFORE {ag0:.2f}GB, {len(pairs)} pairs", flush=True)
    if ag0 < GUARD_GB: print(f"ABORT: <{GUARD_GB}GB avail"); sys.exit(3)
    if not torch.backends.mps.is_available(): print("ABORT: no MPS"); sys.exit(4)
    dev = "mps"
    matcher = KF.LoFTR(pretrained="indoor").eval().to(dev)
    print(f"[match] LoFTR indoor on {dev}, torch={torch.__version__}", flush=True)

    # cache grayscale (match res) for involved frames on CPU (uint8, tiny)
    fids = sorted({p["i"] for p in pairs} | {p["j"] for p in pairs})
    cache = {f: load_gray_np(f) for f in fids}
    print(f"[match] cached {len(fids)} frames @ {MATCH_W}x{MATCH_H}", flush=True)

    store = {}; meta = []
    peak_mb = 0.0; t_start = time.time(); done = 0; paused = None
    for pi, p in enumerate(pairs):
        i, j = p["i"], p["j"]
        ag = avail_gb()
        if ag < GUARD_GB:
            torch.mps.empty_cache(); ag = avail_gb()
            if ag < GUARD_GB:
                paused = {"at_pair": pi, "avail_gb": round(ag, 2)}
                print(f"[match] PAUSE at pair {pi} (avail {ag:.2f}GB < {GUARD_GB}); saving partial", flush=True)
                break
        t0 = torch.from_numpy(cache[i])[None, None].float().to(dev) / 255.0
        t1 = torch.from_numpy(cache[j])[None, None].float().to(dev) / 255.0
        with torch.no_grad():
            corr = matcher({"image0": t0, "image1": t1})
        p0 = corr["keypoints0"].cpu().numpy().astype(np.float32)
        p1 = corr["keypoints1"].cpu().numpy().astype(np.float32)
        conf = corr["confidence"].cpu().numpy().astype(np.float32)
        keep = conf >= CONF
        p0, p1, conf = p0[keep], p1[keep], conf[keep]
        # scale match-coords -> work-coords
        p0 = p0 * np.array([SX, SY], np.float32)
        p1 = p1 * np.array([SX, SY], np.float32)
        key = f"{i}_{j}"
        store[key + "_p0"] = p0; store[key + "_p1"] = p1; store[key + "_conf"] = conf
        meta.append({"i": i, "j": j, "n": int(len(p0))})
        peak_mb = max(peak_mb, torch.mps.driver_allocated_memory() / 1e6)
        del t0, t1, corr; torch.mps.empty_cache()
        done += 1
        if done % 25 == 0 or pi == len(pairs) - 1:
            print(f"[match] {done}/{len(pairs)} pairs, last {key} n={len(p0)}, "
                  f"peak_mps={peak_mb:.0f}MB, avail={avail_gb():.2f}GB", flush=True)
    dt = time.time() - t_start
    np.savez(NPZ_OUT, **store)
    counts = [m["n"] for m in meta]
    summary = {"n_pairs_matched": len(meta), "match_res": [MATCH_W, MATCH_H],
               "conf_thresh": CONF, "matches_min": int(min(counts)) if counts else 0,
               "matches_med": int(np.median(counts)) if counts else 0,
               "matches_max": int(max(counts)) if counts else 0,
               "matches_total": int(sum(counts)),
               "peak_mps_mb": round(peak_mb, 0), "wall_s": round(dt, 1),
               "paused": paused, "pairs": meta}
    json.dump(summary, open(META_OUT, "w"), indent=1)
    print(f"[match] DONE {len(meta)} pairs in {dt:.1f}s, total matches {sum(counts)}, "
          f"peak_mps {peak_mb:.0f}MB, avail {avail_gb():.2f}GB", flush=True)
    print("MATCH_DONE" if paused is None else "MATCH_PARTIAL", flush=True)

if __name__ == "__main__":
    main()
