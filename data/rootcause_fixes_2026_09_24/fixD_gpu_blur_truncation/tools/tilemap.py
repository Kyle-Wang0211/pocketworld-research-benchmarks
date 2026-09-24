import numpy as np
def tilemap(phone_xy, ref_xy, T=128, W=4032, H=3024, thr=3):
    ny, nx = (H + T - 1)//T, (W + T - 1)//T
    hp,_,_=np.histogram2d(phone_xy[:,1],phone_xy[:,0],bins=[ny,nx],range=[[0,ny*T],[0,nx*T]])
    hr,_,_=np.histogram2d(ref_xy[:,1],ref_xy[:,0],bins=[ny,nx],range=[[0,ny*T],[0,nx*T]])
    lines=[]
    for i in range(ny):
        row=''
        for j in range(nx):
            if hr[i,j]>=thr and hp[i,j]==0: row+='.'      # ref has kps, phone none  -> dead
            elif hp[i,j]>=3*max(hr[i,j],1) and hp[i,j]>=10: row+='+'  # phone >>3x ref -> excess
            elif hp[i,j]>0: row+='#'
            else: row+=' '
        lines.append(f'{i*T:4d} {row}')
    dead=int(((hr>=thr)&(hp==0)).sum()); live=int((hr>=thr).sum())
    return '\n'.join(lines), dead, live
