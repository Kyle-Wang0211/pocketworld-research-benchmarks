import os,glob,numpy as np,cv2
V="/root/res_probe/raw/Training/41048190"
def ts(p):
    b=os.path.basename(p); return float(b.split("_")[1].split(".png")[0])
for a in ("highres_depth","lowres_depth","vga_wide"):
    fs=sorted(glob.glob(os.path.join(V,a,"*.png")))
    im=cv2.imread(fs[0],cv2.IMREAD_UNCHANGED)
    t=[ts(p) for p in fs]
    dt=np.diff(sorted(t))
    print("%-15s n=%-6d shape=%-16s dtype=%-8s median dt=%.4fs (=%.1f fps)"%(a,len(fs),im.shape,im.dtype,np.median(dt),1/np.median(dt)))
# pose coverage for highres timestamps against lowres_wide.traj
traj=[float(l.split()[0]) for l in open(os.path.join(V,"lowres_wide.traj")) if l.strip()]
traj=np.array(sorted(traj))
hd=np.array(sorted(ts(p) for p in glob.glob(os.path.join(V,"highres_depth","*.png"))))
vg=np.array(sorted(ts(p) for p in glob.glob(os.path.join(V,"vga_wide","*.png"))))
for name,arr in (("highres_depth",hd),("vga_wide",vg)):
    k=np.searchsorted(traj,arr); k=np.clip(k,1,len(traj)-1)
    d=np.minimum(np.abs(traj[k]-arr),np.abs(traj[k-1]-arr))
    print("%-15s vs traj: median |dt| %.5fs  p95 %.5fs  frac within 0.005s = %.3f"%(name,np.median(d),np.percentile(d,95),(d<0.005).mean()))
# intrinsics available at highres timestamps?
ic=set(os.path.basename(p).split("_")[1].replace(".pincam","") for p in glob.glob(os.path.join(V,"vga_wide_intrinsics","*.pincam")))
hs=set("%.3f"%t for t in hd)
print("highres ts with an exact vga_wide_intrinsics file: %d / %d"%(len(hs&ic),len(hs)))
# how do the two depths compare where both exist?
com=sorted(set("%.3f"%t for t in hd)&set("%.3f"%t for t in np.array(sorted(ts(p) for p in glob.glob(os.path.join(V,"lowres_depth","*.png"))))))
print("timestamps with BOTH highres_depth and lowres_depth:",len(com))
if com:
    import random
    for s in random.Random(0).sample(com,min(3,len(com))):
        H=cv2.imread(os.path.join(V,"highres_depth","41048190_%s.png"%s),cv2.IMREAD_UNCHANGED).astype(np.float32)/1000.
        L=cv2.imread(os.path.join(V,"lowres_depth","41048190_%s.png"%s),cv2.IMREAD_UNCHANGED).astype(np.float32)/1000.
        Lu=cv2.resize(L,(H.shape[1],H.shape[0]),interpolation=cv2.INTER_NEAREST)
        m=(H>0)&(Lu>0)
        print("  ts %s  highres %s valid %.1f%% | lowres %s valid %.1f%% | median |H-Lup| on overlap %.4f m  (overlap %.1f%%)"%(
            s,H.shape,100*(H>0).mean(),L.shape,100*(L>0).mean(),float(np.median(np.abs(H[m]-Lu[m]))),100*m.mean()))
