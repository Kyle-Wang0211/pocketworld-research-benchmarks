import re
src="/root/av_ep0/chain_ep0.sh"; dst="/root/av_ep0_hi/chain_ep0.sh"
s=open(src).read().replace("ROOT=/root/av_ep0;","ROOT=/root/av_ep0_hi;")
# arm B = Meshroom DepthMap downscale=1 / RealityScan "High detail": images NOT scaled down
reps=[('log "1_infer: start 2016x1504"; bash $ROOT/infer_native.sh $CKPT $ROOT/out_native 2016 1504',
       'log "1_infer: start 4032x3008 (downscale 1 = RealityScan High detail)"; bash $ROOT/infer_native.sh $CKPT $ROOT/out_native 4032 3008'),
      ('if [ $rc -eq 0 ]; then echo 2 > $ROOT/ds.txt','if [ $rc -eq 0 ]; then echo 1 > $ROOT/ds.txt'),
      ('log "1_infer: CUDA OOM at 2016x1504 -> fallback 1344x992 (downscale 3)"',
       'log "1_infer: CUDA OOM at 4032x3008 -> fallback 2016x1504 (downscale 2)"'),
      ('step 0_native $PY $ROOT/mk_native_ep0.py $ROOT/mvs_native 2976','step 0_native $PY $ROOT/mk_native_ep0.py $ROOT/mvs_native 3008'),
      ('bash $ROOT/infer_native.sh $CKPT $ROOT/out_native 1344 992 > $ROOT/1_infer_fallback.log 2>&1; rc=$?; echo 3 > $ROOT/ds.txt',
       'bash $ROOT/infer_native.sh $CKPT $ROOT/out_native 2016 1504 > $ROOT/1_infer_fallback.log 2>&1; rc=$?; echo 2 > $ROOT/ds.txt')]
for a,b in reps:
    assert a in s, a[:60]
    s=s.replace(a,b)
open(dst,"w").write(s)
print("wrote",dst)
for l in s.splitlines():
    if "1_infer" in l or "ds.txt" in l: print("  ",l.strip()[:130])
