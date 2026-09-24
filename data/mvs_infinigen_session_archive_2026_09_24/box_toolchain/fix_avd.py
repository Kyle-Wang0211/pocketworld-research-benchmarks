p="/root/av_ep0_avd/chain_ep0.sh"; s=open(p).read()
old=[l for l in s.splitlines() if "aliceVision_depthMapEstimation" in l][0]
# every flag below = the Meshroom v2023.3.0 DepthMap node default, leaf params included (sgmScale is 2, not -1)
new=('step 4_depth $B/aliceVision_depthMapEstimation --input $SFM --imagesFolder $ROOT/prep --output $ROOT/depth '
     '--downscale 2 --minViewAngle 2.0 --maxViewAngle 70.0 --tileBufferWidth 1024 --tileBufferHeight 1024 --tilePadding 64 '
     '--autoAdjustSmallImage 1 --chooseTCamsPerTile 1 --maxTCams 10 '
     '--sgmScale 2 --sgmStepXY 2 --sgmStepZ -1 --sgmMaxTCamsPerTile 4 --sgmWSH 4 --sgmUseSfmSeeds 1 '
     '--sgmSeedsRangeInflate 0.2 --sgmDepthThicknessInflate 0.0 --sgmMaxSimilarity 1.0 --sgmGammaC 5.5 --sgmGammaP 8.0 '
     '--sgmP1 10.0 --sgmP2Weighting 100.0 --sgmMaxDepths 1500 --sgmFilteringAxes YX --sgmDepthListPerTile 1 '
     '--sgmUseConsistentScale 0 --sgmUseCustomPatchPattern 0 '
     '--refineEnabled 1 --refineScale 1 --refineStepXY 1 --refineMaxTCamsPerTile 4 --refineSubsampling 10 '
     '--refineHalfNbDepths 15 --refineWSH 3 --refineSigma 15.0 --refineGammaC 15.5 --refineGammaP 8.0 '
     '--refineInterpolateMiddleDepth 0 --refineUseConsistentScale 0 --refineUseCustomPatchPattern 0 '
     '--colorOptimizationEnabled 1 --colorOptimizationNbIterations 100 --nbGPUs 0 --verboseLevel info')
s=s.replace(old,new); open(p,"w").write(s); print("patched depthMapEstimation line")
