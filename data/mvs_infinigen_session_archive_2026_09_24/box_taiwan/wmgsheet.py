import glob, os, random, cv2, numpy as np
scenes=sorted(glob.glob("/root/wmg_probe/*/frames"))
rng=random.Random(20260924); pick=rng.sample(scenes,4)
rows=[]
for s in pick:
    fs=sorted(glob.glob(s+"/Image/camera_0/Image_*_0_0048_0.png"), key=lambda f:int(os.path.basename(f).split("_")[1]))
    sel=[fs[i] for i in (0,5,10,15)]
    tiles=[cv2.resize(cv2.imread(f),(384,216),interpolation=cv2.INTER_AREA) for f in sel]
    row=np.hstack(tiles); lab=np.full((26,row.shape[1],3),255,np.uint8)
    cv2.putText(lab,os.path.basename(os.path.dirname(s))+"  cams 0/5/10/15 (left camera)",(8,19),cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,0,0),1,cv2.LINE_AA)
    rows.append(np.vstack([lab,row]))
img=np.vstack(rows); head=np.full((38,img.shape[1],3),255,np.uint8)
cv2.putText(head,"WMGStereo indoor (Princeton Infinigen team, BSD-3) - 4 random rooms",(8,27),cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,0,0),2,cv2.LINE_AA)
cv2.imwrite("/root/wmg_sheet.jpg",np.vstack([head,img]),[cv2.IMWRITE_JPEG_QUALITY,88]); print("ok", [os.path.basename(os.path.dirname(s)) for s in pick])
