import sys, time
sys.dont_write_bytecode=True
import accel_diag as A
for sc in ['13f5']:
    t,R,P,imu=A.load(sc)
    t0=time.time()
    for d in (0.0,0.016):
        o=A.solve(sc,t,R,P,imu,d)
        print(sc,'d=%.0fms'%(d*1e3),'k-1 %+.2f%%'%((o['k']-1)*100),'rms %.4f'%o['rms'],o.get('b_a'),'%.1fs'%(time.time()-t0),flush=True)
