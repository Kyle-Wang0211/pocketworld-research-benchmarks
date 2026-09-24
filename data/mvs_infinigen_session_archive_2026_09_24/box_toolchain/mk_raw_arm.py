src="/root/av_ep0_hi/chain_ep0.sh"; dst="/root/av_ep0_raw/chain_ep0.sh"
s=open(src).read().replace("ROOT=/root/av_ep0_hi;","ROOT=/root/av_ep0_raw;")
# arm C: no CasDiffMVS pre-mask -- DepthMapFilter is the official chain's only depth filter
a='step 4_depth $PY $ROOT/write_av_depthmaps_ds.py $ROOT/out_native $SFM $ROOT/depth $DS'
b='step 4_depth $PY $ROOT/write_av_depthmaps_ds.py $ROOT/out_native $SFM $ROOT/depth $DS 0'
assert a in s; s=s.replace(a,b)
# the filter now has to do all the work, so a low survival rate is expected here, not a red flag
s=s.replace('step 5b_filtgate $PY $ROOT/filt_gate.py $ROOT/depth $ROOT/filt 0.30',
            'step 5b_filtgate $PY $ROOT/filt_gate.py $ROOT/depth $ROOT/filt 0.10')
s=s.replace('log "1_infer: start 4032x3008 (downscale 1 = RealityScan High detail)"; bash $ROOT/infer_native.sh $CKPT $ROOT/out_native 4032 3008',
            'log "1_infer: reusing arm B depth (2016x1504)"; true')
open(dst,"w").write(s); print("wrote",dst)
