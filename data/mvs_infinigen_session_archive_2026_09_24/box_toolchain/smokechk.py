import re, numpy as np, glob, os, sys
log=sys.argv[1] if len(sys.argv)>1 else "/root/ak2_smoke.log"
pat=re.compile(r"ak_(\d+)\[(\w+)\]: 帧 (\d+) \| 有位姿 (\d+) \| 关键帧 (\d+) \(间距中位 ([\d.]+).*插值 ([\d.]+) / 最近邻 ([\d.]+) / 写反 ([\d.]+) m \| 原生有效率 ([\d.]+) -> 768x576 ([\d.]+)")
res=re.compile(r"\[res\] (\d+) (\w+) dl=(\d+)s conv=(\d+)s raw=(\d+)MB out=(\d+)MB frames=(\d+) free=(\d+)GB")
rows=[];rs=[]
for l in open(log):
    m=pat.search(l)
    if m: rows.append(m.groups())
    m=res.search(l)
    if m: rs.append(m.groups())
# 普查预测
pred={}
for f in glob.glob("/root/ak2_hr/*.hts"):
    v=os.path.basename(f)[:-4]; ls=open(f).read().split("\n")
    if ls and ls[0].startswith("#"): pred[v]=len([x for x in ls[1:] if x.strip()])
a=np.array([[int(r[2]),int(r[3]),int(r[4]),float(r[5]),float(r[6]),float(r[7]),float(r[8]),float(r[9]),float(r[10])] for r in rows])
print("转出 %d 个场景 (日志里 SKIP %d)"%(len(rows), sum(1 for l in open(log) if "SKIP" in l)))
print("  帧数 vs 普查预测: 一致 %d / %d"%(sum(1 for r in rows if pred.get(r[0])==int(r[2])), len(rows)))
print("  有位姿占比      : 中位 %.4f  min %.4f"%(np.median(a[:,1]/a[:,0]), (a[:,1]/a[:,0]).min()))
print("  关键帧/帧       : 中位 %.3f"%np.median(a[:,2]/a[:,0]))
print("  关键帧间距      : 中位 %.4f (设计 0.10)"%np.median(a[:,3]))
print("  跨视|dz| 插值   : 中位 %.4f  p90 %.4f"%(np.median(a[:,4]),np.percentile(a[:,4],90)))
print("  跨视|dz| 最近邻 : 中位 %.4f   写反: 中位 %.4f"%(np.median(a[:,5]),np.median(a[:,6])))
print("  插值 < 最近邻 的视频: %d / %d ; 插值 < 写反: %d / %d"%(
    int((a[:,4]<a[:,5]).sum()),len(a),int((a[:,4]<a[:,6]).sum()),len(a)))
print("  原生有效率      : 中位 %.4f  p10 %.4f  min %.4f  max %.4f"%(np.median(a[:,7]),np.percentile(a[:,7],10),a[:,7].min(),a[:,7].max()))
print("  768x576 有效率  : 中位 %.4f  min %.4f"%(np.median(a[:,8]),a[:,8].min()))
b=np.array([[int(x[2]),int(x[3]),int(x[4]),int(x[5]),int(x[6])] for x in rs],float)
mbf=b[:,3][b[:,4]>0]/b[:,4][b[:,4]>0]
print("资源: dl 中位 %.0fs  conv 中位 %.0fs | raw 峰值 中位 %.0f MB max %.0f MB | MB/帧 中位 %.3f (试点 1.78)"%(
    np.median(b[:,0]),np.median(b[:,1]),np.median(b[:,2]),b[:,2].max(),np.median(mbf)))
print("  总下载 %.1f GB / 总产物 %.1f GB / 总帧 %d"%(b[:,2].sum()/1024,b[:,3].sum()/1024,int(b[:,4].sum())))
