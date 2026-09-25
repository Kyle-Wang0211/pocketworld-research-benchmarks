import os,sys
src,dst=sys.argv[1],sys.argv[2]
os.makedirs(dst+'/cam0',exist_ok=True)
for a,b in [(src+'/cam0/data',dst+'/cam0/data'),(src+'/imu0',dst+'/imu0')]:
    if not os.path.lexists(b): os.symlink(os.path.realpath(a),b)
lines=open(src+'/cam0/data.csv','rb').read().split(b'\r\n')
hdr,rows=lines[0],[l for l in lines[1:] if l.strip()]
out=[hdr]; last=None; kept=0
for l in rows:
    t=int(l.split(b',')[0])*1e-9
    if last is not None and t-last < 1.0/30: continue
    last=t; out.append(l); kept+=1
open(dst+'/cam0/data.csv','wb').write(b'\r\n'.join(out)+b'\r\n')
print(dst,'kept',kept,'of',len(rows))
