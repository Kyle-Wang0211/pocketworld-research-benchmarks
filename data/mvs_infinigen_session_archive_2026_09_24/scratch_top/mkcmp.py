import glob, os, re, random, cv2, numpy as np
def complete(d):
    return len(glob.glob(d+"/frames/Image/*/Image_*.png"))>=30 and len(glob.glob(d+"/frames/Depth/*/Depth_*.npy"))>=30
full=[d for r in ["ig7_official","ig7_official_b","ig7_official_c","ig7_official_d"] for d in sorted(glob.glob(f"/root/{r}/*")) if complete(d)]
fast=[d for d in sorted(glob.glob("/root/ig7_official_e/*")) if complete(d)]
print("完整配方完整房间", len(full), "| fast_solve 完整房间", len(fast))
def nobj(d):
    # coarse 日志里每个求解阶段 "Finished solving ..., added N objects" 的总和
    tot=0
    for f in glob.glob(d+"/logs/*_0_log.err"):
        try: s=open(f,errors="ignore").read()
        except: continue
        if "task_uniqname coarse" not in s and "[solve_" not in s: continue
        tot+=sum(int(x) for x in re.findall(r"added (\d+) objects", s))
    return tot
print("家具件数(全部完整房间) 完整配方:", sorted(nobj(d) for d in full))
print("家具件数(全部完整房间) fast_solve:", sorted(nobj(d) for d in fast))
rng=random.Random(20260924)
pick_full=rng.sample(full, 4); pick_fast=rng.sample(fast, 4)
CAMS=[0,8,16,24]
def sheet(rooms, out, title):
    rows=[]
    for d in rooms:
        tiles=[]
        for k in CAMS:
            f=glob.glob(f"{d}/frames/Image/*/Image_{k}_0_*.png")[0]
            im=cv2.resize(cv2.imread(f),(384,288),interpolation=cv2.INTER_AREA)
            tiles.append(im)
        row=np.hstack(tiles)
        lab=np.full((28,row.shape[1],3),255,np.uint8)
        cv2.putText(lab,f"{os.path.basename(d)}  furniture objects={nobj(d)}",(8,20),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,0,0),1,cv2.LINE_AA)
        rows.append(np.vstack([lab,row]))
    img=np.vstack(rows)
    head=np.full((40,img.shape[1],3),255,np.uint8)
    cv2.putText(head,title,(8,28),cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,0,0),2,cv2.LINE_AA)
    cv2.imwrite(out,np.vstack([head,img]),[cv2.IMWRITE_JPEG_QUALITY,88])
    print(out, [os.path.basename(d) for d in rooms])
sheet(pick_full,"/root/cmp_full.jpg","FULL recipe (official, 300/200/50 solver steps) - 4 random rooms x cams 0/8/16/24")
sheet(pick_fast,"/root/cmp_fast.jpg","fast_solve (100/40/5 solver steps) - 4 random rooms x cams 0/8/16/24")
