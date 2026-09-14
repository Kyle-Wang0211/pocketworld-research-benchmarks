import os, numpy as np, cv2
GA="/root/regionmerge/gated_mvsa"; OUT="/root/single_frame"
def write_ply(path,V,C):
    with open(path,"wb") as f:
        f.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"%len(V)).encode())
        r=np.zeros(len(V),dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        r["x"],r["y"],r["z"]=V[:,0],V[:,1],V[:,2]; r["r"],r["g"],r["b"]=C[:,0],C[:,1],C[:,2]; r.tofile(f)
for i in (131,121,125):
    p=f"{GA}/depth/{i:08d}.npy"
    if not os.path.exists(p): print("缺", p); continue
    d=np.load(p); z=np.load(f"{GA}/cam/{i:08d}.npz"); K,E=z["K"],z["E"]
    col=cv2.imread(f"{GA}/color/{i:08d}.png")[:,:,::-1]
    keep=d>0; h,w=d.shape; x,y=np.meshgrid(np.arange(w),np.arange(h))
    x,y,dd=x[keep],y[keep],d[keep]
    xyz=np.linalg.inv(K)@(np.vstack((x,y,np.ones_like(x)))*dd)
    V=(np.linalg.inv(E)@np.vstack((xyz,np.ones_like(x))))[:3].T.astype(np.float32)
    write_ply(f"{OUT}/f{i:03d}_mvsahero.ply",V,col[keep].astype(np.uint8))
    print(f"  帧 {i}: MVSAnywhere {keep.sum():,} 点 / {d.size:,} ({keep.mean()*100:.1f}%)")
