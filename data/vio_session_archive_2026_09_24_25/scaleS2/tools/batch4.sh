#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
S=$SP/scaleS2; C=$S/cfg; A=$S/tools/arm.sh; M=$S/tools/arm_M.sh
until [ -f $SP/xr_shared/euroc1920_4ad6e500/README.S2 ]; do sleep 20; done
R=$HOME/Developer/viobench-recordings; REF=$R/run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa/arkit_poses.tum
H=$SP/xr_shared/euroc1920_4ad6e500; L=$SP/xr_shared/euroc640_4ad6e500
$A 4ad6_R1920_B0 gen $C/slam_B.yaml $C/dev_B1920_4ad6_td8.yaml $H $REF
$A 4ad6_R1920_noise4.5 gen $C/slam_B.yaml $C/dev_B1920_4ad6_td8_noise4.5.yaml $H $REF
$A 4ad6_R1920_kpdist75 gen $C/slam_B__kpdist75.yaml $C/dev_B1920_4ad6_td8.yaml $H $REF
$A 4ad6_R1920_parallax30 gen $C/slam_B__parallax30.yaml $C/dev_B1920_4ad6_td8.yaml $H $REF
$A 4ad6_R1920_px3yaml+noise gen $C/slam_B__px3yaml.yaml $C/dev_B1920_4ad6_td8_noise4.5.yaml $H $REF
$A 4ad6_R1920_px3code gen_px3 $C/slam_B.yaml $C/dev_B1920_4ad6_td8.yaml $H $REF
$A 4ad6_R1920_px3code+lk gen_px3lk $C/slam_B.yaml $C/dev_B1920_4ad6_td8.yaml $H $REF
$A 4ad6_R1920_px3all gen_px3lk $C/slam_B__px3yaml.yaml $C/dev_B1920_4ad6_td8_noise4.5.yaml $H $REF
$A 4ad6_R1920_IOS ios $C/slam_B.yaml $C/dev_B1920_4ad6_td8.yaml $H $REF
$A 4ad6_R640_noise0.056 gen $C/slam_B.yaml $C/dev_B640_4ad6_td8_noise0.0556.yaml $L $REF
$M 4ad6_R1920_M_B0 $C/slam_B.yaml $C/dev_B1920_4ad6_td8.yaml $H $REF
echo BATCH4_DONE
