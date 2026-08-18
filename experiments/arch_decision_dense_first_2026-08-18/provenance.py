import numpy as np
from PIL import Image
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall"
BASE="/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
p=BASE+"/dense_P16k.ply"
with open(p,"rb") as f:
    hdr=b""
    while True:
        l=f.readline(); hdr+=l
        if l.strip()==b"end_header": break
    n=int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1]); off=len(hdr)
M=np.memmap(p,dtype=DT,mode="r",offset=off,shape=(n,))

# pair.txt ref 顺序
L=open(BASE+"/mvs_P16k/pair.txt").read().split("\n")
nref=int(L[0]); refs=[int(L[1+2*i]) for i in range(nref)]
print("refs head:",refs[:6],"n=",nref)

# 块长 = final mask 真像素数
lens=[]
for r in refs:
    mk=np.array(Image.open(f"{BASE}/out_P16k/mask/{r:08d}_final.png"))
    lens.append(int((mk>0).sum()))
lens=np.array(lens); print("sum lens",lens.sum(),"ply n",n, "match:",lens.sum()==n)
offs=np.r_[0,np.cumsum(lens)]

# 验证块0颜色 vs 图像像素(行主序)
r0=refs[0]
mk=np.array(Image.open(f"{BASE}/out_P16k/mask/{r0:08d}_final.png"))>0
img=np.array(Image.open(f"{BASE}/out_P16k/images/{r0:08d}.jpg").convert("RGB")) if __import__('os').path.exists(f"{BASE}/out_P16k/images/{r0:08d}.jpg") else None
if img is None:
    img=np.array(Image.open(f"{BASE}/in_P16k/images/frame_{r0:06d}.jpg").convert("RGB").resize((768,576)))
blk=np.array(M[offs[0]:offs[1]])
prgb=np.stack([blk["r"],blk["g"],blk["b"]],1).astype(int)
irgb=img[mk].astype(int)
diff=np.abs(prgb-irgb).mean()
print("行主序颜色平均差:",round(float(diff),2))
np.save(S+"/offs.npy",offs); np.save(S+"/refs.npy",np.array(refs))
