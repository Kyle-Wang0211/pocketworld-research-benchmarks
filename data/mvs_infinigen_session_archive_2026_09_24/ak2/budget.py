import numpy as np
w=[];h=[];bad=0
for l in open("/root/ak2_sizes.txt"):
    p=l.split()
    if len(p)!=4: continue
    ww,hh=int(p[2]),int(p[3])
    if ww==0 or hh==0: bad+=1; continue
    w.append(ww); h.append(hh)
w=np.array(w,float); h=np.array(h,float)
print("视频数 %d (HEAD 失败 %d)"%(len(w),bad))
print("wide.zip          总 %.2f TiB  中位 %.0f MB  p90 %.0f MB  max %.0f MB"%(w.sum()/2**40,np.median(w)/2**20,np.percentile(w,90)/2**20,w.max()/2**20))
print("highres_depth.zip 总 %.2f TiB  中位 %.0f MB  p90 %.0f MB"%(h.sum()/2**40,np.median(h)/2**20,np.percentile(h,90)/2**20))
print("合计下载          %.2f TiB ; 单视频解压峰值(中位) %.0f MB, p99 %.0f MB"%((w.sum()+h.sum())/2**40,(np.median(w)+np.median(h))/2**20*1.15,(np.percentile(w,99)+np.percentile(h,99))/2**20*1.15))
per=262758706/787.0
fr=h/per
print("推断 highres 帧数: 总 %.1f 万  中位/视频 %.0f  p10 %.0f p90 %.0f"%(fr.sum()/1e4,np.median(fr),np.percentile(fr,10),np.percentile(fr,90)))
for kfr in (0.44,0.60,0.70):
    print("   若 关键帧/帧 = %.2f  -> 关键帧 %.1f 万, 产物 %.2f TiB (1.78 MB/帧)"%(kfr,fr.sum()*kfr/1e4,fr.sum()*kfr*1.78/2**20))
