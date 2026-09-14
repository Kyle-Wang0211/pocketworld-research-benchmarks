import numpy as np, glob, os
d = np.load(sorted(glob.glob("/root/da3_full/exports/npz/*.npz"))[0], allow_pickle=True)
print("npz keys:", list(d.keys())[:14])
for k in d.keys():
    a = d[k]
    if hasattr(a,"shape") and a.ndim>=2 and a.shape[0]==132:
        print(f"  {k}: {a.shape} {a.dtype}")
