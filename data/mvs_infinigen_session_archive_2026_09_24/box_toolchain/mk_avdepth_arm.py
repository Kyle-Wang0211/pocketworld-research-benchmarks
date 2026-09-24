src="/root/av_ep0_raw/chain_ep0.sh"; dst="/root/av_ep0_avd/chain_ep0.sh"
s=open(src).read().replace("ROOT=/root/av_ep0_raw;","ROOT=/root/av_ep0_avd;")
# arm E = the FULL official dense chain: AliceVision's own DepthMap node replaces our CasDiffMVS depth entirely.
# Every flag = the Meshroom v2023.3.0 DepthMap node default (downscale 2, maxTCams 10, sgm*/refine* as shipped).
old = 'step 4_depth $PY $ROOT/write_av_depthmaps_ds.py $ROOT/out_native $SFM $ROOT/depth $DS 0'
new = ('step 4_depth $B/aliceVision_depthMapEstimation --input $SFM --imagesFolder $ROOT/prep --output $ROOT/depth '
       '--downscale 2 --minViewAngle 2.0 --maxViewAngle 70.0 --tileBufferWidth 1024 --tileBufferHeight 1024 --tilePadding 64 '
       '--autoAdjustSmallImage 1 --chooseTCamsPerTile 1 --maxTCams 10 --sgmScale -1 --sgmStepXY 2 --sgmStepZ -1 '
       '--sgmMaxTCamsPerTile 4 --sgmWSH 4 --sgmUseSfmSeeds 1 --sgmSeedsRangeInflate 0.2 --sgmDepthThicknessInflate 0.0 '
       '--sgmMaxSimilarity 1.0 --sgmGammaC 5.5 --sgmGammaP 8.0 --sgmP1 10.0 --sgmP2Weighting 100.0 --sgmMaxDepths 1500 '
       '--sgmFilteringAxes YX --sgmDepthListPerTile 1 --sgmUseConsistentScale 0 --refineScale 1 --refineStepXY 1 '
       '--refineMaxTCamsPerTile 4 --refineSubsampling 10 --refineHalfNbDepths 15 --refineWSH 3 --refineSigma 15.0 '
       '--refineGammaC 15.5 --refineGammaP 8.0 --refineInterpolateMiddleDepth 0 --refineUseConsistentScale 0 '
       '--colorOptimizationNbIterations 100 --refineUseCustomPatchPattern 0 --nbGPUs 0 --verboseLevel info')
assert old in s; s=s.replace(old,new)
s=s.replace('log "1_infer: reusing arm B depth (2016x1504)"; true','log "1_infer: not needed (AliceVision computes its own depth)"; true')
open(dst,"w").write(s); print("wrote",dst)
