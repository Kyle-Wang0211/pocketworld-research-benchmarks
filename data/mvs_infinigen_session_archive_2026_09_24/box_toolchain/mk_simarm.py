#!/usr/bin/env python3
"""Build a meshing input folder that differs from /root/av_ep0_off/filt ONLY in the simMap values.
  mk_simarm.py <outdir> <mode>      mode: nc | s1
    nc = identity (negative control: byte-equivalent sim values, new files, new folder)
    s1 = sim' = 2*sim + 1 on valid pixels only  (CasDiffMVS conf -> the documented [-1,+1] range)
depthMap.exr and nmodMap.png are hardlinked unchanged. simMap metadata is copied verbatim."""
import sys, os, glob, numpy as np, OpenEXR
SRC = "/root/av_ep0_off/filt"; OUT = sys.argv[1]; MODE = sys.argv[2]
os.makedirs(OUT, exist_ok=True)
n = 0; nchanged = 0; totvalid = 0; npos = 0
for dp in sorted(glob.glob(SRC + "/*_depthMap.exr")):
    vid = os.path.basename(dp).split("_")[0]
    for suf in ("_depthMap.exr", "_nmodMap.png"):
        src = "%s/%s%s" % (SRC, vid, suf); dst = "%s/%s%s" % (OUT, vid, suf)
        if not os.path.exists(dst): os.link(src, dst)
    d = np.asarray(OpenEXR.File(dp).channels()["Y"].pixels, dtype=np.float32)
    f = OpenEXR.File("%s/%s_simMap.exr" % (SRC, vid))
    s = np.asarray(f.channels()["Y"].pixels)          # float16 as written by AliceVision
    hdr = {k: v for k, v in f.header().items() if isinstance(k, str) and k.startswith("AliceVision")}
    hdr["compression"] = OpenEXR.ZIP_COMPRESSION
    v = d > 0
    s2 = s.astype(np.float32).copy()
    if MODE == "s1":
        s2[v] = 2.0 * s2[v] + 1.0
    elif MODE == "s3":
        s2[v] = 4.0 * s2[v] + 3.0
    elif MODE != "nc":
        raise SystemExit("bad mode")
    s2 = s2.astype(np.float16)
    nchanged += int((s2 != s).sum()); totvalid += int(v.sum()); npos += int((s2[v] >= 0.0).sum())
    OpenEXR.File(hdr, {"Y": s2}).write("%s/%s_simMap.exr" % (OUT, vid))
    n += 1
print("mode=%s views=%d  px changed=%d  valid px=%d  valid&sim>=0 after=%d (%.2f%%)"
      % (MODE, n, nchanged, totvalid, npos, 100.0 * npos / max(totvalid, 1)))
