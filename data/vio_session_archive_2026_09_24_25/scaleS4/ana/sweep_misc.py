import sys; sys.path.insert(0,'ana'); from rep import *
import numpy as np
R=REC; base_ds=R+'_euroc_6e2d4b99_640'; ref=R+'run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum'
base=S4+'/cfg/dev640_k0_td8.yaml'; slam=R+'_paper_cmp/slam_paper.yaml'
what=sys.argv[1]
def qmul(a,b):  # xyzw
    ax,ay,az,aw=a; bx,by,bz,bw=b
    return [aw*bx+ax*bw+ay*bz-az*by, aw*by-ax*bz+ay*bw+az*bx, aw*bz+ax*by-ay*bx+az*bw, aw*bw-ax*bx-ay*by-az*bz]
if what=='rbc':
    q0=[-0.7071068, 0.7071068, 0, 0]
    for deg in (1,3):
        for ax in range(3):
            for sg in (-1,1):
                th=np.radians(sg*deg); dq=[0,0,0,np.cos(th/2)]; dq[ax]=np.sin(th/2)
                q=qmul(q0,dq)   # perturb in camera frame
                n=f'rbc_{"xyz"[ax]}{sg*deg:+d}'
                d=make_dev(base, S4+f'/cfg/{n}.yaml', q_bc=q)
                run(base_ds, slam, d, '6e2d_640_'+n, ref=ref)
elif what=='alag':
    src=base_ds+'/imu0/data.csv'
    lines=open(src,'rb').read().split(b'\r\n'); head=lines[0]; rows=[l for l in lines[1:] if l.strip()]
    D=np.array([[float(x) for x in l.split(b',')] for l in rows])
    t=D[:,0]
    for tau in (0,-10,-5,5,10,15):
        dd=S4+f'/ds/alag{tau:+d}'
        os.makedirs(dd+'/imu0',exist_ok=True)
        if not os.path.exists(dd+'/cam0'): os.symlink(base_ds+'/cam0', dd+'/cam0')
        A=np.stack([np.interp(t+tau*1e6, t, D[:,j]) for j in (4,5,6)],1)  # a_new(t)=a_rec(t+tau)
        with open(dd+'/imu0/data.csv','wb') as f:
            f.write(head+b'\r\n')
            for i in range(len(t)):
                f.write(f'{int(t[i])},{float(D[i,1])!r},{float(D[i,2])!r},{float(D[i,3])!r},{float(A[i,0])!r},{float(A[i,1])!r},{float(A[i,2])!r}\r\n'.encode())
        run(dd, slam, base, f'6e2d_640_alag{tau:+d}', ref=ref)
elif what=='k1':
    fx,fy,cx,cy=1347.7943115234375,1347.7943115234375,957.4692993164062,718.9641723632812
    for k1 in (-0.05,-0.02,0.02,0.05):
        d=make_dev(base, S4+f'/cfg/k1_{k1:+g}.yaml', distortion=[k1,0,0,0], distortion_flag=1)
        run(base_ds, slam, d, f'6e2d_640_k1{k1:+g}', ref=ref)
    d=make_dev(base, S4+f'/cfg/k1_0flag.yaml', distortion=[0,0,0,0], distortion_flag=1)
    run(base_ds, slam, d, f'6e2d_640_k1_0flag', ref=ref)
