import numpy as np, os, random
def read_pfm(p):
    with open(p,"rb") as f:
        t=f.readline().rstrip(); d=f.readline()
        while d.strip().startswith(b"#"): d=f.readline()
        w,h=map(int,d.split()); s=float(f.readline().rstrip()); e="<" if s<0 else ">"
        return np.flipud(np.frombuffer(f.read(w*h*4),dtype=e+"f").reshape((h,w))).copy()
R="/root/monotrain"
gs=[d for d in os.listdir(R) if d.startswith("gso_")]
rng=random.Random(4); fr=[]
for s in rng.sample(gs,30):
    dd=os.path.join(R,s,"rendered_depth_maps"); fs=sorted(os.listdir(dd))
    for f in [fs[0],fs[len(fs)//2]]:
        a=read_pfm(os.path.join(dd,f)); fr.append(float((a>0).mean()))
fr=np.array(fr)
print("GSO foreground (depth>0) fraction over %d frames: median %.4f  p10 %.4f  p90 %.4f"%(len(fr),np.median(fr),np.percentile(fr,10),np.percentile(fr,90)))
print("=> object occupies ~%.0f x %.0f effective px of the 768x576 frame"%( (np.median(fr)*768*576)**0.5*(768/576)**0.5, (np.median(fr)*768*576)**0.5*(576/768)**0.5))
