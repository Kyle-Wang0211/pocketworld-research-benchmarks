import sys, numpy as np, json, os
R = os.path.expanduser('~/Developer/viobench-recordings/')
runs = sys.argv[1:] or ['run-6e2d4b99-896b-4372-ae47-ac0b4679cf18','run-5966aec0-cbf1-4abc-af0e-c1fc559da44c','run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa']
for run in runs:
    d = np.genfromtxt(R+run+'/imu.csv', delimiter=',', skip_header=1)
    t = d[:,0]*1e-9; w = d[:,1:4]; a = d[:,4:7]
    dt = np.diff(t)
    cam = np.genfromtxt(R+run+'/camera_index.csv', delimiter=',', skip_header=1)[:,0]*1e-9
    print(f'== {run[:12]}  N={len(t)}  span={t[-1]-t[0]:.2f}s  rate={1/np.median(dt):.2f}Hz')
    print(f'   dt ms: min {dt.min()*1e3:.3f} p1 {np.percentile(dt,1)*1e3:.3f} med {np.median(dt)*1e3:.3f} p99 {np.percentile(dt,99)*1e3:.3f} max {dt.max()*1e3:.3f}  gaps>15ms {np.sum(dt>0.015)}  gaps>25ms {np.sum(dt>0.025)} nonmono {np.sum(dt<=0)}')
    # duplicate accel (sample-and-hold)
    same_a = np.all(np.diff(a,axis=0)==0,axis=1); same_w = np.all(np.diff(w,axis=0)==0,axis=1)
    print(f'   consecutive identical accel rows {same_a.sum()} ({100*same_a.mean():.2f}%)  identical gyro rows {same_w.sum()}')
    # camera coverage
    print(f'   cam N={len(cam)} cam dt med {np.median(np.diff(cam))*1e3:.3f}ms  imu starts {1e3*(t[0]-cam[0]):+.1f}ms after cam0, ends {1e3*(t[-1]-cam[-1]):+.1f}ms after last cam')
    an = np.linalg.norm(a,axis=1); wn = np.linalg.norm(w,axis=1)
    # static windows: 0.5 s windows, gyro norm max < 0.03, accel std < 0.03
    win = int(round(0.5/np.median(dt)))
    st = []
    for i in range(0, len(t)-win, win//2):
        if wn[i:i+win].max() < 0.05 and an[i:i+win].std() < 0.05:
            st.append((t[i]-t[0], an[i:i+win].mean(), an[i:i+win].std(), wn[i:i+win].mean()))
    print(f'   |a| overall: mean {an.mean():.4f} median {np.median(an):.4f}   static 0.5s windows: {len(st)}')
    if st:
        m = np.array([s[1] for s in st])
        print(f'   static |a| mean {m.mean():.4f}  min {m.min():.4f} max {m.max():.4f}  (vs 9.80665 std, Beijing 9.8015)  rel err {(m.mean()/9.8015-1)*100:+.3f}%')
        for s in st[:6]: print('     t=%.2fs |a|=%.4f sd=%.4f |w|=%.4f'%s)
    # accel-gyro lag: df/dt = -w x f  (pure rotation, f=specific force body)
    # smooth with 5-sample moving average
    def sm(x,k=5):
        ker=np.ones(k)/k
        return np.stack([np.convolve(x[:,j],ker,mode='same') for j in range(3)],1)
    tu = np.arange(t[0]+0.2, t[-1]-0.2, 0.002)
    wi = np.stack([np.interp(tu,t,w[:,j]) for j in range(3)],1)
    best=[]
    for lag_ms in np.arange(-40,41,1):
        ai = np.stack([np.interp(tu+lag_ms*1e-3,t,a[:,j]) for j in range(3)],1)
        dadt = np.gradient(ai,axis=0)/0.002
        pred = -np.cross(wi, ai)
        # low pass both (0.1s box) to suppress translational accel derivative noise
        k=25
        r = sm(dadt,k)-sm(pred,k)
        best.append((lag_ms, np.sqrt(np.mean(r**2)), np.corrcoef(sm(dadt,k).ravel(), sm(pred,k).ravel())[0,1]))
    best=np.array(best); i=np.argmin(best[:,1])
    print(f'   accel lag vs gyro (accel sampled at t+lag best fits rotation kinematics): best lag {best[i,0]:+.0f} ms  rms {best[i,1]:.3f}  corr {best[i,2]:.3f};  rms at 0 ms {best[40,1]:.3f}')
    print('    lag curve:', ' '.join(f'{int(b[0])}:{b[1]:.3f}' for b in best[::5]))
