import os, sys
os.environ.setdefault("VAR_GATE","0"); os.environ.setdefault("TEX_GATE","0")
sys.path.insert(0,"/root/diffmvs"); os.chdir("/root/diffmvs")
from filter import filter_depth
OUT,PAIR,PLY,MT,PX,DT = sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),float(sys.argv[5]),float(sys.argv[6])
print("[f3] mask>=%d  pixel<%.4f  depth<%.6f" % (MT,PX,DT), flush=True)
filter_depth(PAIR,OUT,PLY,MT,PX,DT,[0.3,0.5,0.5],"casdiffmvs","general")
