import sys; sys.path.insert(0,'ana'); from rep import *
ds='/Users/kaidongwang/Developer/euroc/V1_01_easy_gt/mav0'; ref=S4+'/cfg/v101_gt.tum'
run(ds, S4+'/cfg/euroc_slam.yaml', S4+'/cfg/dev_euroc.yaml', 'v101_base', ref=ref)
