import cv2, numpy as np
R="/root/ig2fly/out/30377061_0_traj"
rows=[]
for t in range(4):
    tiles=[cv2.resize(cv2.imread(f"{R}{t}/CameraLeft/{f:04d}.png"),(384,216),interpolation=cv2.INTER_AREA) for f in (0,8,16,23)]
    row=np.hstack(tiles); lab=np.full((26,row.shape[1],3),255,np.uint8)
    cv2.putText(lab,f"traj{t}  frames 0/8/16/23 (left camera)",(8,19),cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,0,0),1,cv2.LINE_AA)
    rows.append(np.vstack([lab,row]))
img=np.vstack(rows); head=np.full((38,img.shape[1],3),255,np.uint8)
cv2.putText(head,"infinigen2-flying-indoors (official, BSD-3) - scene 30377061_0, 4 trajectories",(8,27),cv2.FONT_HERSHEY_SIMPLEX,0.75,(0,0,0),2,cv2.LINE_AA)
cv2.imwrite("/root/ig2_sheet.jpg",np.vstack([head,img]),[cv2.IMWRITE_JPEG_QUALITY,88]); print("ok")
