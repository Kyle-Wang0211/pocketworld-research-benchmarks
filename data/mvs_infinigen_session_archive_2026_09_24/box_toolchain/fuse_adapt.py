import os, sys, importlib.util
os.environ.setdefault("VAR_GATE","0"); os.environ.setdefault("TEX_GATE","0")
sys.path.insert(0,"/root/diffmvs"); os.chdir("/root/diffmvs")
spec = importlib.util.spec_from_file_location("fa","/root/filter_adapt.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
OUT,PAIR,PLY,MT,PX,DT = sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),float(sys.argv[5]),float(sys.argv[6])
print("[adapt] mask>=%d px<%.4f depth<%.6f (dthres/ 存在则逐像素)"%(MT,PX,DT), flush=True)
m.filter_depth(PAIR,OUT,PLY,MT,PX,DT,[0.3,0.5,0.5],"casdiffmvs","general")
